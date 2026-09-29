"""Bibliographic connectors. Only explicit source metadata enters the pipeline."""

import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


class LookupFailure(Exception):
    pass


def _request(url, **kwargs):
    # One retry for idempotent reads only. Never weaken TLS or follow redirects.
    headers = {"User-Agent": "BrainFormat/3.0 (bibliographic metadata lookup)"}
    headers.update(kwargs.pop('headers', {}))
    for attempt in range(2):
        try:
            response = requests.get(
                url, timeout=(5, 12), allow_redirects=False,
                headers=headers, **kwargs
            )
        except requests.exceptions.SSLError:
            raise
        except (requests.Timeout, requests.ConnectionError):
            if attempt:
                raise
            time.sleep(0.5)
            continue
        if attempt == 0 and response.status_code in {429, 500, 502, 503, 504}:
            retry_after = response.headers.get('Retry-After', '0.5')
            try:
                delay = float(retry_after)
            except (ValueError, TypeError):
                return response
            if not 0 <= delay <= 2:
                return response
            response.close()
            time.sleep(max(0.5, delay))
            continue
        return response


def _get(url, **kwargs):
    try:
        response = _request(url, **kwargs)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        if 300 <= response.status_code < 400:
            origin = urlparse(url)
            destination = urljoin(url, response.headers.get('Location', ''))
            target = urlparse(destination)
            # The ISBN endpoint redirects to a catalog edition. Only this exact
            # HTTPS host/path transition is accepted, with no arbitrary URL fetch.
            if (origin.scheme == 'https' and origin.netloc == 'openlibrary.org'
                    and re.fullmatch(r'/isbn/[0-9X]{10,13}\.json', origin.path)
                    and target.scheme == 'https' and target.netloc == 'openlibrary.org'
                    and not target.query and not target.fragment
                    and re.fullmatch(r'/books/OL[0-9]+M\.json', target.path)):
                return _get(destination)
            raise LookupFailure("Redirecionamento da fonte requer revisao.")
        if len(response.content) > 4 * 1024 * 1024:
            raise LookupFailure("Resposta da fonte excedeu o limite.")
        return response
    except requests.RequestException as exc:
        raise LookupFailure("Fonte indisponivel, limite de consultas ou falha de conexao segura.") from exc


def _json(url, **kwargs):
    response = _get(url, **kwargs)
    if response is None:
        return {}
    try:
        return response.json()
    except ValueError as exc:
        raise LookupFailure("Fonte retornou uma resposta invalida.") from exc


def _stamp(meta, source, url):
    meta['_source'] = {"name": source, "url": url,
                       "retrieved_at": datetime.now(timezone.utc).isoformat()}
    return meta


def _plain(value):
    return BeautifulSoup(str(value or ''), 'html.parser').get_text(' ', strip=True)


def normalize_pages(value):
    value = str(value or '').strip()
    repeated = re.fullmatch(r'([a-zA-Z]?\d+)\s*[-\u2013]\s*\1', value)
    return repeated[1] if repeated else value


def _crossref_metadata(data):
    type_map = {'journal-article': 'journalArticle', 'book': 'book',
                'monograph': 'book', 'edited-book': 'book', 'book-chapter': 'chapter',
                'proceedings-article': 'proceedings', 'dissertation': 'thesis'}
    title = _plain((data.get('title') or [''])[0])
    if not title:
        return {}
    doi = str(data.get('DOI', ''))
    published = data.get('published-print') or data.get('published-online') or data.get('issued') or {}
    parts = (published.get('date-parts') or [[]])[0]
    authors = []
    cleanup = []
    for author in data.get('author', []):
        cleaned = {}
        for key in ('family', 'given'):
            original = _plain(author.get(key, ''))
            # Publishers sometimes put affiliation superscripts in author names.
            cleaned[key] = re.sub(r'[\d,\s*\u00b9\u00b2\u00b3]+$', '', original).strip()
            if original != cleaned[key]:
                cleanup.append('Marcadores de afiliacao removidos da autoria; confira a grafia na publicacao.')
        if cleaned.get('family') or cleaned.get('given'):
            authors.append(cleaned)
        elif author.get('name'):
            authors.append({'family': _plain(author['name']), 'given': '', 'is_corporate': True})
    resource = data.get('resource', {}).get('primary', {}).get('URL', '')
    meta = {
        'item_type': type_map.get(data.get('type'), 'unknown'),
        'title': title, 'authors': authors, 'year': str(parts[0]) if parts else '',
        'journal': _plain((data.get('container-title') or [''])[0]),
        'volume': str(data.get('volume', '')), 'issue': str(data.get('issue', '')),
        'page': normalize_pages(data.get('page') or data.get('article-number')),
        'publisher': _plain(data.get('publisher', '')), 'doi': doi,
        'url': resource if resource.startswith(('https://', 'http://')) else '',
        '_issns': [s for s in data.get('ISSN', []) if re.fullmatch(r'[0-9]{4}-[0-9]{3}[0-9X]', str(s))],
        '_warnings': list(dict.fromkeys(cleanup)),
    }
    if len(parts) > 1 and isinstance(parts[1], int) and 1 <= parts[1] <= 12:
        meta['start_month'] = parts[1]
    if data.get('language'):
        meta['language'] = str(data['language'])
    if meta['item_type'] == 'chapter':
        meta['book_title'] = meta.pop('journal')
    if meta['item_type'] == 'proceedings':
        event = data.get('event', {})
        meta.update(event_name=_plain(event.get('name', '')),
                    event_city=_plain(event.get('location', '')),
                    event_number=str(event.get('number', '')),
                    proceedings_title=meta.pop('journal'))
    return _stamp(meta, 'Crossref', f'https://api.crossref.org/works/{quote(doi, safe="")}')


def fetch_crossref_doi(doi):
    url = f'https://api.crossref.org/works/{quote(doi, safe="")}'
    data = _json(url).get('message', {})
    return _crossref_metadata(data) if data else {}


def fetch_crossref_search(query):
    data = _json('https://api.crossref.org/works',
                 params={'query.bibliographic': query, 'rows': 5})
    return [meta for item in data.get('message', {}).get('items', [])
            if (meta := _crossref_metadata(item))]


def valid_isbn(value):
    digits = re.sub(r'[^0-9X]', '', value.upper())
    if len(digits) == 13 and digits.isdigit():
        return sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(digits)) % 10 == 0
    if len(digits) == 10 and digits[:9].isdigit() and (digits[-1].isdigit() or digits[-1] == 'X'):
        return sum((10 if c == 'X' else int(c)) * (10 - i) for i, c in enumerate(digits)) % 11 == 0
    return False


def _isbn_key(value):
    digits = re.sub(r'[^0-9X]', '', value.upper())
    if not valid_isbn(digits):
        return ''
    if len(digits) == 10:
        prefix = '978' + digits[:9]
        check = (-sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(prefix))) % 10
        return prefix + str(check)
    return digits


def _book_authors(names):
    authors = []
    for name in names:
        if ',' in name:
            family, given = name.split(',', 1)
        else:
            given, _, family = name.rpartition(' ')
            family = family or name
        authors.append({'family': family.strip(), 'given': given.strip()})
    return authors


def _openlibrary_edition(isbn):
    data = _json(f'https://openlibrary.org/isbn/{isbn}.json')
    identifiers = [_isbn_key(value)
                   for value in data.get('isbn_10', []) + data.get('isbn_13', [])]
    if _isbn_key(isbn) not in identifiers or not data.get('title'):
        return {}
    title = data['title'] + (': ' + data['subtitle'] if data.get('subtitle') else '')
    names, warnings = [], []
    for author in data.get('authors', []):
        key = author.get('key', '')
        if not re.fullmatch(r'/authors/OL[0-9]+A', key):
            continue
        try:
            person = _json('https://openlibrary.org' + key + '.json')
            if person.get('name'):
                names.append(person['name'])
        except LookupFailure:
            warnings.append('Autoria da edicao nao foi totalmente recuperada no catalogo.')
    year = re.search(r'\b\d{4}\b', data.get('publish_date', ''))
    return _stamp({'item_type': 'book', 'title': title, 'isbn': isbn,
                   'authors': _book_authors(names), 'year': year[0] if year else '',
                   'city': '; '.join(data.get('publish_places', [])),
                   'publisher': '; '.join(data.get('publishers', [])),
                   '_warnings': list(dict.fromkeys(warnings))},
                  'Open Library', f'https://openlibrary.org/isbn/{isbn}.json')


def fetch_google_books(isbn):
    if not valid_isbn(isbn):
        return {}
    google_error = None
    try:
        data = _json('https://www.googleapis.com/books/v1/volumes', params={'q': f'isbn:{isbn}'})
        for item in data.get('items', []):
            info = item.get('volumeInfo', {})
            identifiers = [_isbn_key(i.get('identifier', ''))
                           for i in info.get('industryIdentifiers', [])]
            if _isbn_key(isbn) not in identifiers:
                continue
            title = info.get('title', '')
            if info.get('subtitle'):
                title += ': ' + info['subtitle']
            return _stamp({'item_type': 'book', 'title': title,
                           'authors': _book_authors(info.get('authors', [])),
                           'year': info.get('publishedDate', '')[:4],
                           'publisher': info.get('publisher', ''), 'isbn': isbn},
                          'Google Books', 'https://www.googleapis.com/books/v1/volumes/' + quote(item['id']))
    except LookupFailure as exc:
        google_error = exc
    key = f'ISBN:{isbn}'
    url = 'https://openlibrary.org/api/books'
    openlibrary_error = None
    try:
        book = _json(url, params={'bibkeys': key, 'format': 'json', 'jscmd': 'data'}).get(key, {})
    except LookupFailure as exc:
        book, openlibrary_error = {}, exc
    if not book:
        edition = _openlibrary_edition(isbn)
        if edition:
            return edition
        if openlibrary_error or google_error:
            raise openlibrary_error or google_error
        return {}
    year = re.search(r'\b\d{4}\b', book.get('publish_date', ''))
    return _stamp({'item_type': 'book', 'title': book.get('title', ''),
                   'authors': _book_authors([a['name'] for a in book.get('authors', [])]),
                   'year': year.group(0) if year else '', 'isbn': isbn,
                   'publisher': '; '.join(p['name'] for p in book.get('publishers', [])),
                   'city': '; '.join(p['name'] for p in book.get('publish_places', []))},
                  'Open Library', book.get('url', f'https://openlibrary.org/isbn/{isbn}'))


def fetch_by_url(url):
    """Use identifiers in URLs; never let user input fetch arbitrary LAN addresses."""
    parsed = urlparse(url)
    if parsed.scheme == 'https' and parsed.hostname in {'doi.org', 'dx.doi.org'}:
        return fetch_crossref_doi(parsed.path.lstrip('/'))
    return {}
