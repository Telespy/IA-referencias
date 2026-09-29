"""Title discovery without assigning an arbitrary edition to a book."""

import re
from urllib.parse import urlencode

from reference_validation import normalized, title_similarity
from sources import _json, _stamp, _book_authors, fetch_crossref_search, LookupFailure


def title_query(raw, parsed, detected):
    explicit = re.match(r'^t[i\u00ed]tulo\s*:\s*(.+)$', raw, re.I | re.S)
    if explicit:
        return explicit[1].strip().strip('"').rstrip('.')
    if detected['type'] != 'text' or parsed.get('doi') or parsed.get('isbn'):
        return ''
    if parsed.get('item_type') != 'book' or any(parsed.get(k) for k in ('edition', 'url')):
        return ''
    if re.search(r',\s*(?:18|19|20)\d{2}\b', raw) and parsed.get('publisher'):
        return ''
    if re.match(r'^[^:.]+,\s*[^:]+\.\s', raw) or re.search(r'\bet al\b|\bIn:', raw, re.I):
        return ''
    # Punctuation in a bare title (e.g. ELMO 1.0) is not an author boundary.
    if parsed.get('authors') and re.match(r'^[A-Z\u00c0-\u00dd][A-Z\u00c0-\u00dd\s-]+\.\s', raw):
        return ''
    return raw.strip().strip('"').rstrip('.')


def search_book_titles(title):
    url = 'https://openlibrary.org/search.json?' + urlencode({
        'title': title, 'limit': 10, 'fields': 'key,title,author_name,edition_count'})
    data = _json(url)
    results = []
    for doc in data.get('docs', []):
        key = doc.get('key', '')
        if not re.fullmatch(r'/works/OL[0-9]+W', key) or not doc.get('title'):
            continue
        results.append(_stamp({'item_type': 'book', 'title': doc['title'],
                               'authors': _book_authors(doc.get('author_name', [])),
                               'catalog_url': 'https://openlibrary.org' + key,
                               'edition_count': doc.get('edition_count'), '_work_only': True},
                              'Open Library - busca de obras', url))
    return results


def fetch_title_candidates(title):
    candidates, issues = [], []
    for name, search in (('Crossref', fetch_crossref_search), ('Open Library', search_book_titles)):
        try:
            candidates.extend(search(title))
        except LookupFailure as exc:
            issues.append({'code': 'SOURCE_UNAVAILABLE', 'message': f'Busca por titulo ({name}): {exc}',
                           'severity': 'warning', 'field': None})
        except (ValueError, KeyError, TypeError, AttributeError):
            issues.append({'code': 'SOURCE_INVALID', 'message': f'Busca por titulo ({name}): metadados invalidos.',
                           'severity': 'warning', 'field': None})
    return {'candidates': candidates, 'issues': issues}


def select_title(title, candidates):
    selected, seen = [], set()
    for candidate in candidates:
        similarity = title_similarity(title, candidate.get('title', ''))
        if similarity < 0.8:
            continue
        key = candidate.get('doi') or candidate.get('isbn') or candidate.get('catalog_url')
        if not key:
            # Never collapse different books/editions solely by identical title.
            key = repr((candidate.get('title'), candidate.get('authors'), candidate.get('publisher'), candidate.get('year'), candidate.get('edition')))
        key = str(key).casefold()
        if key in seen:
            continue
        seen.add(key)
        selected.append((similarity, candidate))
    selected.sort(key=lambda item: item[0], reverse=True)
    suggestions = [c for _, c in selected[:5]]
    if not selected:
        return {}, suggestions
    score, candidate = selected[0]
    distinct_numbers = re.findall(r'\d+', title) != re.findall(r'\d+', candidate.get('title', ''))
    if score < 0.97 or distinct_numbers or (len(selected) > 1 and selected[1][0] >= score - 0.05):
        return {}, suggestions
    if candidate.get('item_type') != 'book' and len(normalized(title).split()) < 4:
        return {}, suggestions
    return candidate, suggestions


def public_candidate(meta):
    return {key: meta[key] for key in ('title', 'authors', 'year', 'item_type', 'doi', 'isbn',
                                     'publisher', 'edition', 'catalog_url', 'edition_count') if meta.get(key)}
