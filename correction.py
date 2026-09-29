"""Correction pipeline with per-field evidence and explicit review states."""

import re
from datetime import date, datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from config import ABNT_MONTHS_PT
from formatters import format_abnt, format_apa, get_item_type_label, get_missing_attributes
from parsers import identify_input_type, parse_raw_citation_text
from publication_places import normalize_place
from reference_validation import normalized, select_candidate, verify_work_identity
from sources import LookupFailure, valid_isbn
from title_lookup import title_query, select_title, public_candidate


FIELD_LABELS = {
    'authors': 'autoria', 'title': 'titulo', 'journal': 'periodico',
    'year': 'ano', 'volume': 'volume', 'issue': 'numero', 'page': 'paginas/localizador',
    'city': 'local', 'publisher': 'editora', 'edition': 'edicao', 'doi': 'DOI',
    'isbn': 'ISBN', 'book_title': 'titulo do livro', 'book_authors': 'autoria do livro',
    'institution': 'instituicao', 'degree_type': 'tipo e programa academico',
    'degree_year': 'ano de defesa', 'event_name': 'evento', 'event_number': 'numero do evento',
    'event_year': 'ano do evento', 'event_city': 'local do evento',
    'proceedings_title': 'titulo dos anais', 'jurisdiction': 'jurisdicao',
    'ementa': 'ementa', 'site_name': 'site', 'newspaper': 'jornal',
    'patent_no': 'patente', 'deposit_info': 'deposito', 'concession_info': 'concessao',
    'date_str': 'data', 'month_str': 'mes', 'section': 'secao',
    'start_month': 'mes inicial', 'end_month': 'mes final', 'day': 'dia',
    'legal_number': 'numero da norma/projeto', 'legal_year': 'ano da norma/projeto',
    'legal_type': 'tipo legislativo', 'legal_date': 'data de assinatura',
    'legislative_house': 'casa legislativa', 'publication_title': 'veiculo de publicacao',
    'publication_date': 'data de publicacao',
}
SUPPORTED_TYPES = {'book', 'chapter', 'journalArticle', 'proceedings', 'thesis',
                   'legislation', 'bill', 'legal', 'website', 'newspaperArticle', 'patent'}
MANUAL_PATTERN = re.compile(
    r'\b(?:jurisprud[eê]ncia|ac[oó]rd[aã]o|s[uú]mula|habeas corpus|'
    r'podcast|partitura|documento cartogr[aá]fico|mapa topogr[aá]fico|'
    r'filme|fotografia|software|dataset|preprint)\b', re.I)


def correction_today():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).date()


def correct_reference(raw_line, *, online, fetch_doi, fetch_book, search, fetch_url, enrich=None,
                      fetch_title=None, fetch_legal=None):
    raw = raw_line.strip()
    if not raw:
        return None
    raw_for_parser = re.sub(r'^\s*(?:\[\d+\]|\d+[.)]|[-*])\s+', '', raw)
    raw_for_parser = re.sub(r'^\s*(?:corrija|corrigir)\s+(?:essa\s+)?refer[eê]ncia\s*(?:para\s+ABNT)?\s*:\s*', '', raw_for_parser, flags=re.I)
    parsed = parse_raw_citation_text(raw_for_parser)
    detected = identify_input_type(raw_for_parser)
    title_input = title_query(raw_for_parser, parsed, detected)
    if title_input:
        parsed = {'title': title_input, 'item_type': 'unknown'}
    issues, corrections, sources = [], [], []
    fetched, evidence = {}, {}
    suggestions = []

    def issue(code, message, severity='warning', field=None):
        issues.append({'code': code, 'message': message, 'severity': severity, 'field': field})

    def lookup(fn, query, name):
        try:
            return fn(query)
        except LookupFailure as exc:
            issue('SOURCE_UNAVAILABLE', f'{name}: {exc}')
            return {}
        except (ValueError, KeyError, TypeError, AttributeError):
            issue('SOURCE_INVALID', f'{name}: metadados incompletos ou invalidos.')
            return {}

    def remember_source(source):
        if source and not any(s.get('name') == source.get('name') and s.get('url') == source.get('url') for s in sources):
            sources.append(source)

    declared_url = re.search(r'\bDispon[ií]vel em:\s*(.*?)(?=\s*Acesso em:|$)', raw, re.I | re.S)
    invalid_url = False
    if declared_url:
        candidate_url = re.search(r'https?://[^\s)<>]+', declared_url[1], re.I)
        try:
            invalid_url = not candidate_url or not urlsplit(candidate_url[0]).hostname
        except ValueError:
            invalid_url = True
        if invalid_url:
            issue('INVALID_URL', 'O campo Disponivel em nao contem um endereco HTTP/HTTPS valido. Informe o link da publicacao.', field='url')

    doi = parsed.get('doi', '')
    isbn = parsed.get('isbn', '')
    unsupported = bool(MANUAL_PATTERN.search(raw_for_parser))
    if unsupported:
        issue('UNSUPPORTED_TYPE', 'Tipo de documento requer revisao manual; a entrada original foi preservada.')
    elif online:
        if parsed.get('item_type') in {'legislation', 'bill'} and fetch_legal:
            response = lookup(fetch_legal, parsed, 'Fontes legislativas oficiais')
            fetched = response.get('match', {})
            issues.extend(response.get('issues', []))
        elif title_input and fetch_title:
            response = lookup(fetch_title, title_input, 'Busca por titulo')
            issues.extend(response.get('issues', []))
            fetched, matches = select_title(title_input, response.get('candidates', []))
            edition_unconfirmed = fetched.get('item_type') == 'book' and not fetched.get('_work_only')
            if edition_unconfirmed:
                fetched = {}
            suggestions = [public_candidate(m) for m in matches]
            for match in matches:
                remember_source(match.get('_source'))
            if fetched:
                issue('TITLE_MATCH', 'Obra identificada pelo titulo nas fontes consultadas; confira a autoria e o identificador retornados.', 'info')
                if fetched.get('item_type') == 'book':
                    issue('BOOK_EDITION_REQUIRED', 'O titulo identifica a obra, nao a edicao consultada. Envie o ISBN da sua edicao para confirmar ano, editora e local.')
            elif edition_unconfirmed:
                issue('BOOK_EDITION_REQUIRED', 'Foi encontrada uma edicao possivel, mas o titulo sozinho nao confirma que seja a consultada. Reenvie o ISBN ou DOI dessa edicao apos conferir o candidato.')
            elif matches:
                issue('AMBIGUOUS_TITLE', 'Correspondencias possiveis, sem selecao automatica. Confira os candidatos e reenvie o DOI ou ISBN da obra/edicao correta.')
            else:
                issue('TITLE_NOT_CONFIRMED', 'Titulo nao confirmado nas fontes consultadas. Informe autoria, DOI, ISBN ou a referencia completa.')
        elif doi:
            candidate = lookup(fetch_doi, doi, 'Crossref')
            if candidate and verify_work_identity(parsed, candidate):
                fetched = candidate
            elif candidate:
                issue('DOI_CONFLICT', 'O DOI informado aponta para uma obra diferente. Ele nao foi usado para completar os dados.', field='doi')
            else:
                issue('DOI_UNVERIFIED', 'DOI nao confirmado na Crossref; isso nao prova que o DOI seja inexistente.', field='doi')
        elif isbn:
            if not valid_isbn(isbn):
                issue('INVALID_ISBN', 'ISBN com digito verificador invalido.', field='isbn')
            else:
                candidate = lookup(fetch_book, isbn, 'Catalogos de livros')
                if candidate and verify_work_identity(parsed, candidate):
                    fetched = candidate
                else:
                    issue('ISBN_UNVERIFIED', 'ISBN nao confirmado para esta obra e edicao.', field='isbn')
        elif detected['type'] == 'url':
            fetched = lookup(fetch_url, detected['query'], 'URL')

        # Search only when there is enough bibliographic context, never for a bare bad DOI.
        if not fetched and not isbn and parsed.get('item_type') in {'journalArticle', 'proceedings'} and len(normalized(parsed.get('title')).split()) >= 4:
            query = ' '.join(filter(None, [parsed.get('title'), parsed.get('journal'), parsed.get('year')]))
            candidates = lookup(search, query, 'Busca Crossref')
            fetched, ambiguous = select_candidate(parsed, candidates)
            if ambiguous:
                issue('AMBIGUOUS_MATCH', 'Mais de uma obra corresponde aos dados. Informe o DOI ou consulte a publicacao.')
    else:
        issue('OFFLINE', 'Consulta online desativada. Os dados bibliograficos nao foram verificados.')

    if fetched and fetched.get('item_type') not in {'legislation', 'bill'} and online and enrich:
        enriched = lookup(enrich, fetched, 'Complementacao bibliografica')
        if enriched:
            fetched = enriched
    meta = {key: value for key, value in parsed.items() if value not in ('', None, [], {})}
    for key in meta:
        evidence[key] = {'source': 'entrada', 'verified': False}
    if fetched:
        source = fetched.get('_source') or {'name': 'Catalogo bibliografico', 'url': '', 'retrieved_at': ''}
        for fetched_source in fetched.get('_sources') or [source]:
            remember_source(fetched_source)
        issues.extend(fetched.get('_issues', []))
        corrections.extend(fetched.get('_source_changes', []))
        if fetched.get('start_month') or fetched.get('month_str'):
            # A verified issue period replaces the entire parsed date group.
            period_source = (fetched.get('_field_sources', {}).get('start_month')
                             or fetched.get('_field_sources', {}).get('month_str') or source)
            for key in ('start_month', 'end_month', 'month_str', 'day'):
                if key in meta and key not in fetched:
                    previous = meta.pop(key)
                    evidence.pop(key, None)
                    corrections.append({'field': key, 'before': previous, 'after': None,
                                        'source': period_source['name'], 'source_url': period_source['url']})
        for key, value in fetched.items():
            if key.startswith('_') or value in ('', None, [], {}):
                continue
            field_source = fetched.get('_field_sources', {}).get(key) or source
            if key == 'authors' and fetched.get('_warnings') and meta.get('authors'):
                continue
            # Preserve access information supplied by the person who consulted the work.
            if key in {'access_date', 'url'} and meta.get(key):
                if value == meta[key]:
                    evidence[key] = {'source': field_source['name'], 'url': field_source['url'], 'verified': True}
                continue
            previous = meta.get(key)
            if previous and previous != value and key != 'item_type':
                corrections.append({'field': key, 'before': previous, 'after': value,
                                    'source': field_source['name'], 'source_url': field_source['url']})
            meta[key] = value
            evidence[key] = {'source': field_source['name'], 'url': field_source['url'], 'verified': True}
            if key in fetched.get('_derived_fields', []):
                evidence[key]['derived'] = True
        for warning in fetched.get('_warnings', []):
            issue('SOURCE_METADATA_REVIEW', warning)
        for entry in issues:
            if entry['code'] == 'SOURCE_CONFLICT' and not entry.get('resolved') and entry.get('field') in evidence:
                evidence[entry['field']].update(verified=False, conflicted=True)
        if doi and meta.get('doi', '').casefold() != doi.casefold():
            for entry in issues:
                if entry['code'] in {'DOI_CONFLICT', 'DOI_UNVERIFIED'}:
                    entry['resolved'] = True
            issue('DOI_CORRECTED', f'DOI substituido por {meta["doi"]}, apos conferir titulo, autoria e ano.', 'info', 'doi')

    for field in ('city', 'event_city'):
        if not meta.get(field):
            continue
        place = normalize_place(meta[field])
        if place.details:
            evidence[field]['normalization'] = place.details
        if place.value != meta[field]:
            corrections.append({'field': field, 'before': meta[field], 'after': place.value,
                                'source': 'Normalizacao geografica (IBGE)',
                                'source_url': place.details['rule_source']})
            meta[field] = place.value
        for code, message in place.warnings:
            issue(code, message, field=field)
            evidence[field]['verified'] = False

    item_type = meta.get('item_type', 'unknown')
    if unsupported or item_type not in SUPPORTED_TYPES:
        item_type = 'unknown'
        meta['item_type'] = item_type
    if not fetched:
        issue('NOT_VERIFIED', 'Obra nao confirmada; entrada original preservada.' if item_type == 'unknown'
              else 'Referencia formatada apenas com os dados fornecidos. Confira a publicacao original.')
    if meta.get('url') and not evidence.get('url', {}).get('verified'):
        issue('URL_UNVERIFIED', 'O endereco informado foi preservado, mas seu conteudo nao foi conferido.', field='url')
    if any(a.get('et_al') for a in meta.get('authors', [])):
        issue('INCOMPLETE_AUTHORS', 'Lista de autores abreviada na entrada; a referencia APA exige a autoria completa.', field='authors')
    access_date = meta.get('access_date', '')
    today = correction_today()
    if not access_date and online and fetched and (meta.get('url') or meta.get('doi')):
        access_date = f'{today.day} {ABNT_MONTHS_PT[today.month]} {today.year}'
        meta['access_date'] = access_date
        evidence['access_date'] = {'source': 'data da correcao', 'verified': False,
                                   'generated': True, 'timezone': 'America/Sao_Paulo'}
        issue('ACCESS_DATE_GENERATED', 'Data de acesso preenchida com a data desta correcao (America/Sao_Paulo); nao atesta disponibilidade do link.', 'info', 'access_date')
    if access_date:
        months = ['jan', 'fev', 'mar', 'abr', 'maio', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
        match = re.fullmatch(r'(\d{1,2})\s+([a-z]+)\.?\s*(\d{4})', access_date, re.I)
        try:
            if not match:
                raise ValueError
            accessed = date(int(match[3]), months.index(match[2].lower()) + 1, int(match[1]))
            if accessed > today:
                issue('FUTURE_ACCESS_DATE', 'Data de acesso no futuro; informe a data em que consultou a obra.', field='access_date')
        except ValueError:
            issue('INVALID_ACCESS_DATE', 'Data de acesso invalida.', field='access_date')

    missing = get_missing_attributes(meta)
    if item_type == 'journalArticle' and meta.get('issue') and not (meta.get('start_month') or meta.get('month_str')):
        missing.append('Mes/periodo do fasciculo (nao recuperado)')
    if invalid_url:
        missing.append('URL de acesso valida')
    if (meta.get('url') or meta.get('doi')) and not access_date:
        missing.append('Data de acesso informada pelo usuario')
    if item_type in {'legislation', 'bill'}:
        if not meta.get('jurisdiction'):
            missing.append('Jurisdicao da legislacao')
        if not fetched.get('_official_legal'):
            issue('LEGAL_REVIEW', 'Legislacao: conferir numero, data, jurisdicao, ementa e veiculo de publicacao na fonte oficial.')
    unverified = [key for key in FIELD_LABELS if meta.get(key) and not evidence.get(key, {}).get('verified')]
    if unverified:
        issue('UNVERIFIED_FIELDS', 'Dados ainda sem confirmacao: ' + ', '.join(FIELD_LABELS[k] for k in unverified) + '.')
    if missing:
        issue('MISSING_FIELDS', 'Elementos pendentes: ' + '; '.join(dict.fromkeys(missing)) + '.')
    blocking = [i for i in issues if i['severity'] != 'info' and not i.get('resolved')]
    approved = bool(fetched and not blocking and item_type in SUPPORTED_TYPES)
    abnt = format_abnt(meta) if item_type != 'unknown' else raw
    apa = format_apa(meta) if item_type != 'unknown' else raw
    return {
        'raw': raw, 'meta': meta, 'item_type': item_type,
        'item_type_label': get_item_type_label(item_type),
        'abnt': abnt, 'apa': apa, 'missing_fields': list(dict.fromkeys(missing)),
        'status': 'verified' if approved else 'needs_review', 'approved': approved,
        'identity_verified': bool(fetched), 'issues': issues,
        'warnings': [i['message'] for i in issues if i['severity'] != 'info'],
        'corrections': corrections, 'provenance': evidence, 'sources': sources,
        'unverified_fields': unverified, 'candidates': suggestions,
        'verification_scope': 'Conferencia com as fontes consultadas; nao e garantia de ausencia de erros.',
    }


def correction_value(value):
    if value is None:
        return 'ausente na fonte consultada'
    if isinstance(value, list) and all(isinstance(author, dict) for author in value):
        return '; '.join(', '.join(filter(None, [a.get('family'), a.get('given')])) for a in value)
    return str(value)


def reference_report(result, index=None, style='abnt'):
    label = 'CONFERIDA NAS FONTES' if result.get('approved') else 'REVISAO NECESSARIA'
    prefix = f'{index}. ' if index is not None else ''
    lines = [f'{prefix}[{label}]', result[style]]
    for correction in result.get('corrections', []):
        field = FIELD_LABELS.get(correction['field'], correction['field'])
        lines.append(f'Alteracao em {field}: {correction_value(correction["before"])} -> {correction_value(correction["after"])}')
    for entry in result.get('issues', []):
        resolved = ' (resolvido)' if entry.get('resolved') else ''
        resolution = ' ' + entry['resolution'] if entry.get('resolution') else ''
        lines.append(f'Aviso{resolved}: {entry["message"]}{resolution}')
    for source in result.get('sources', []):
        lines.append(f'Fonte: {source["name"]} {source["url"]}')
    for candidate in result.get('candidates', []):
        details = [candidate.get('title', ''), correction_value(candidate.get('authors', [])), candidate.get('year', '')]
        details.extend(f'{key.upper()}: {candidate[key]}' for key in ('doi', 'isbn') if candidate.get(key))
        if candidate.get('catalog_url'):
            details.append('Catalogo de edicoes: ' + candidate['catalog_url'])
        lines.append('Candidato: ' + ' | '.join(str(v) for v in details if v))
    return '\n'.join(lines)
