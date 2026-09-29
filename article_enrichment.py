"""Complete identified journal articles using Europe PMC/JATS and the NLM catalog."""

import copy
import re
import threading
import time
from urllib.parse import urlencode

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from reference_validation import normalized, title_similarity, verify_work_identity
from publication_places import normalize_place
from sources import LookupFailure, _get, _json, _stamp, normalize_pages


EPMC = 'https://www.ebi.ac.uk/europepmc/webservices/rest'
_nlm_lock = threading.Lock()
_nlm_last_request = 0.0


def _xml(response):
    if response is None:
        return None
    try:
        return ET.fromstring(response.content)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise LookupFailure('XML bibliografico invalido ou inseguro.') from exc


def _text(node, path):
    value = node.find(path) if node is not None else None
    return ' '.join(''.join(value.itertext()).split()) if value is not None else ''


def _period(value):
    """Only explicit calendar months/ranges; never infer a period from issue number."""
    names = ('january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december')
    lookup = {spelling: index for index, name in enumerate(names, 1) for spelling in (name, name[:3])}
    pieces = re.split(r'\s*[-/\u2013]\s*', value.strip())
    numbers = []
    for piece in pieces:
        name = piece.lower().rstrip('.')
        if name.isdigit() and 1 <= int(name) <= 12:
            numbers.append(int(name))
        elif name in lookup:
            numbers.append(lookup[name])
        else:
            return {}
    if not 1 <= len(numbers) <= 2:
        return {}
    return {'start_month': numbers[0], **({'end_month': numbers[1]} if len(numbers) == 2 else {})}


def _core_metadata(record, source_url):
    info = record.get('journalInfo', {})
    journal = info.get('journal', {})
    authors = []
    for author in record.get('authorList', {}).get('author', []):
        if author.get('lastName'):
            authors.append({'family': author['lastName'], 'given': author.get('firstName', '')})
        elif author.get('collectiveName'):
            authors.append({'family': author['collectiveName'], 'given': '', 'is_corporate': True})
    meta = {'item_type': 'journalArticle', 'doi': record.get('doi', ''),
            'title': record.get('title', '').rstrip('.'), 'authors': authors,
            'year': str(info.get('yearOfPublication') or record.get('pubYear') or ''),
            'volume': str(info.get('volume') or ''), 'issue': str(info.get('issue') or ''),
            'page': normalize_pages(record.get('pageInfo')), 'language': record.get('language', ''),
            '_nlmid': journal.get('nlmid', ''),
            '_issns': [s for s in (journal.get('issn'), journal.get('essn')) if s],
            '_pmcid': record.get('pmcid', '')}
    # The catalog's month can be truncated; a JATS issue period takes precedence.
    month = info.get('monthOfPublication')
    if str(month).isdigit() and 1 <= int(month) <= 12:
        meta['start_month'] = int(month)
    return _stamp(meta, 'Europe PMC (PubMed)', source_url)


def _jats_metadata(root, source_url, expected_title=''):
    article = root.find('./front/article-meta') if root is not None else None
    journal = root.find('./front/journal-meta') if root is not None else None
    if article is None:
        return {}
    language = root.get('{http://www.w3.org/XML/1998/namespace}lang', '')
    titles = [(_text(article, './title-group/article-title'), language)]
    titles.extend((_text(group, 'trans-title'), group.get('{http://www.w3.org/XML/1998/namespace}lang', ''))
                  for group in article.findall('./title-group/trans-title-group'))
    title, language = max(titles, key=lambda pair: title_similarity(expected_title, pair[0])) if expected_title else titles[0]
    authors = []
    for group in article.findall('contrib-group'):
        for contributor in group.findall('contrib'):
            role = contributor.get('contrib-type') or group.get('content-type')
            if role != 'author':
                continue
            name = contributor.find('name')
            if name is not None and _text(name, 'surname'):
                authors.append({'family': _text(name, 'surname'), 'given': _text(name, 'given-names')})
            elif _text(contributor, 'collab'):
                authors.append({'family': _text(contributor, 'collab'), 'given': '', 'is_corporate': True})
    dates = article.findall('pub-date')
    issue_dates = [d for d in dates if d.get('pub-type') in {'ppub', 'epub-ppub'}
                   or d.get('publication-format') == 'print' or d.get('date-type') == 'collection']
    publication = next(iter(issue_dates or dates), None)
    meta = {'item_type': 'journalArticle',
            'doi': _text(article, 'article-id[@pub-id-type="doi"]'),
            'title': title, 'authors': authors,
            'journal': _text(journal, './journal-title-group/journal-title'),
            'volume': _text(article, 'volume'), 'issue': _text(article, 'issue'),
            'year': _text(publication, 'year'), 'language': language,
            'city': _text(journal, './publisher/publisher-loc')}
    first, last = _text(article, 'fpage'), _text(article, 'lpage')
    meta['page'] = _text(article, 'elocation-id') or (first + '-' + last if first and last and first != last else first)
    period = _text(publication, 'season') or _text(publication, 'month')
    meta.update(_period(period))
    if period and not meta.get('start_month'):
        meta['month_str'] = period
    meta['_issue_period'] = bool(issue_dates and period)
    return _stamp(meta, 'PMC (XML do artigo)', source_url)


def _catalog_location(root, nlmid, issns, year, source_url):
    if root is None:
        return {}
    record = root.find('NLMCatalogRecord')
    if record is None or _text(record, 'NlmUniqueID') != nlmid:
        return {}
    catalog_issns = {_text(record, f'ISSN[@IssnType="{kind}"]') for kind in ('Print', 'Electronic')}
    if not set(issns).intersection(catalog_issns):
        return {}
    publication = record.find('PublicationInfo')
    first = _text(publication, 'PublicationFirstYear')
    last = _text(publication, 'PublicationEndYear')
    if not str(year).isdigit() or not first.isdigit() or int(year) < int(first):
        return {}
    if last.isdigit() and int(year) > int(last):
        return {}
    imprints = publication.findall('Imprint[@FunctionType="Publication"]')
    # Multiple imprints can describe historical moves. Do not pick today's address.
    if len(imprints) != 1:
        return {}
    place = _text(imprints[0], 'Place').rstrip(' :;,.')
    if not place or place.lower() in {'[s.l.]', '[s. l.]', '[place of publication not identified]'}:
        return {}
    return _stamp({'city': '[' + place.strip('[]') + ']', '_catalog_inference': True},
                  'NLM Catalog', source_url)


def _same_work(base, extra):
    return (bool(extra.get('doi')) and base.get('doi', '').casefold() == extra['doi'].casefold()
            and verify_work_identity({'title': base.get('title'), 'authors': base.get('authors', [])}, extra))


def _author_names(authors):
    return [normalized(a.get('given', '') + ' ' + a.get('family', '')) for a in authors]


def _comparable(field, value):
    if field == 'city':
        return normalize_place(value).comparison_key
    if field == 'language':
        return {'eng': 'en', 'por': 'pt', 'spa': 'es', 'fra': 'fr', 'fre': 'fr',
                'deu': 'de', 'ger': 'de', 'ita': 'it'}.get(str(value).lower(), str(value).lower())
    return normalized(value)


def enrich_article(original):
    """Keep field-level sources and disagreements, even when enrichment partly fails."""
    if original.get('item_type') != 'journalArticle' or not original.get('doi'):
        return original
    meta = copy.deepcopy(original)
    base_source = meta.get('_source', {})
    meta['_sources'] = [base_source] if base_source else []
    meta['_field_sources'] = {k: base_source for k, v in meta.items() if not k.startswith('_') and v}
    meta['_issues'] = []
    meta['_source_changes'] = []

    def issue(code, message, field=None, severity='warning'):
        meta['_issues'].append({'code': code, 'message': message, 'field': field, 'severity': severity})

    def merge(extra, *, jats=False):
        source = extra['_source']
        meta['_sources'].append(source)
        for key, value in extra.items():
            if key.startswith('_') or value in ('', None, [], {}):
                continue
            previous = meta.get(key)
            differs = bool(previous) and (previous != value if key == 'authors' else _comparable(key, previous) != _comparable(key, value))
            if differs:
                author_split = key == 'authors' and _author_names(previous) == _author_names(value)
                period = key in {'start_month', 'end_month', 'month_str'} and jats and extra.get('_issue_period')
                if not (author_split or period):
                    issue('SOURCE_CONFLICT', f'Fontes divergentes em {key}: {previous} / {value}. Confira a publicacao ou a resolucao indicada.', key)
                    continue
                meta['_source_changes'].append({'field': key, 'before': previous, 'after': value,
                                                 'source': source['name'], 'source_url': source['url']})
            if jats and extra.get('_issue_period') and key in {'start_month', 'month_str'}:
                for stale in ('start_month', 'end_month', 'month_str', 'day'):
                    if stale not in extra:
                        meta.pop(stale, None)
                        meta['_field_sources'].pop(stale, None)
            meta[key] = value
            meta['_field_sources'][key] = source
            if jats and extra.get('_issue_period') and key in {'start_month', 'end_month', 'month_str'}:
                for entry in meta['_issues']:
                    if entry['code'] == 'SOURCE_CONFLICT' and entry.get('field') == key:
                        entry.update(resolved=True, resolution='Usado o periodo explicito do fasciculo no XML do artigo.')
            if key == 'authors':
                meta['_warnings'] = [w for w in meta.get('_warnings', []) if not w.startswith('Marcadores de afiliacao')]

    params = {'query': 'DOI:"' + meta['doi'].replace('"', '') + '"', 'format': 'json',
              'resultType': 'core', 'pageSize': 2}
    source_url = EPMC + '/search?' + urlencode(params)
    try:
        records = _json(EPMC + '/search', params=params).get('resultList', {}).get('result', [])
        matches = [r for r in records if r.get('doi', '').casefold() == meta['doi'].casefold()]
        if not matches:
            return meta
        if len(matches) != 1:
            issue('AMBIGUOUS_SOURCE', 'Europe PMC retornou mais de um registro para o DOI; complementacao suspensa.')
            return meta
        core = _core_metadata(matches[0], source_url)
        if not _same_work(meta, core):
            issue('SOURCE_IDENTITY_CONFLICT', 'O registro Europe PMC nao corresponde ao titulo/autoria identificados.')
            return meta
        merge(core)
    except (LookupFailure, ValueError, TypeError, KeyError, AttributeError):
        issue('ENRICHMENT_UNAVAILABLE', 'Europe PMC: complementacao indisponivel ou invalida; dados anteriores preservados.')
        return meta

    pmcid = core.get('_pmcid', '')
    if re.fullmatch(r'PMC[0-9]+', pmcid):
        xml_url = f'{EPMC}/{pmcid}/fullTextXML'
        try:
            article = _jats_metadata(_xml(_get(xml_url)), xml_url, meta.get('title', ''))
            if article and _same_work(meta, article):
                merge(article, jats=True)
            elif article:
                issue('SOURCE_IDENTITY_CONFLICT', 'XML do artigo nao corresponde ao DOI/titulo; dados rejeitados.')
        except (LookupFailure, ValueError, TypeError, KeyError, AttributeError):
            issue('ENRICHMENT_UNAVAILABLE', 'PMC: XML indisponivel ou invalido; periodo completo pode estar pendente.')

    nlmid = core.get('_nlmid', '')
    if not meta.get('city') and re.fullmatch(r'[0-9]{6,16}[A-Z]?', nlmid):
        params = {'db': 'nlmcatalog', 'id': nlmid, 'retmode': 'xml'}
        url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'
        try:
            global _nlm_last_request
            with _nlm_lock:
                time.sleep(max(0, 0.35 - (time.monotonic() - _nlm_last_request)))
                _nlm_last_request = time.monotonic()
                root = _xml(_get(url, params=params))
            location = _catalog_location(root, nlmid, core['_issns'], meta.get('year'), url + '?' + urlencode(params))
            if location:
                merge(location)
                issue('CATALOG_LOCATION', 'Local entre colchetes obtido no catalogo do periodico (ISSN e intervalo de publicacao conferidos), nao na afiliacao dos autores.', 'city', 'info')
        except (LookupFailure, ValueError, TypeError, KeyError, AttributeError):
            issue('ENRICHMENT_UNAVAILABLE', 'NLM Catalog: local de publicacao nao recuperado.')
    return meta
