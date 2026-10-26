"""Identity checks are separate from formatting and never claim error-free output."""

import re
import unicodedata
from difflib import SequenceMatcher


def normalized(text):
    text = unicodedata.normalize('NFKD', str(text or '')).casefold()
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^\w\s]', ' ', text).split())


def title_similarity(left, right):
    left, right = normalized(left), normalized(right)
    if not left or not right:
        return 0.0
    a, b = set(left.split()), set(right.split())
    return min(SequenceMatcher(None, left, right).ratio(), 2 * len(a & b) / (len(a) + len(b)))


def authors_match(left, right):
    def surnames(authors):
        return [normalized(a.get('family', '')).split() for a in authors if a.get('family')]
    a, b = surnames(left), surnames(right)
    return bool(a and b and any(x == y or x[-1] == y[-1] for x in a for y in b))


def verify_work_identity(user, fetched):
    if not fetched or not fetched.get('title'):
        return False

    # DOI idêntico é um identificador forte. Não rejeite a obra apenas porque
    # uma fonte (ex.: Crossref) cadastrou um título abreviado, desde que os
    # demais sinais bibliográficos não entrem em conflito.
    user_doi = str(user.get('doi') or '').casefold().strip()
    fetched_doi = str(fetched.get('doi') or '').casefold().strip()
    if user_doi and fetched_doi and user_doi == fetched_doi:
        if user.get('item_type') and fetched.get('item_type') and user['item_type'] != fetched['item_type']:
            return False
        if user.get('year') and fetched.get('year') and str(user['year']) != str(fetched['year']):
            return False
        if user.get('authors') and fetched.get('authors') and not authors_match(user['authors'], fetched['authors']):
            return False
        for field in ('issue', 'page'):
            if user.get(field) and fetched.get(field) and normalized(user[field]) != normalized(fetched[field]):
                return False
        return True

    if not user.get('title'):
        return True
    similarity = title_similarity(user['title'], fetched['title'])
    if similarity < 0.85:
        return False
    numbers = lambda title: re.findall(r'\d+(?:\.\d+)*', title)
    if numbers(user['title']) != numbers(fetched['title']):
        return False
    if user.get('item_type') and fetched.get('item_type') != user['item_type']:
        return False
    if user.get('authors'):
        if not authors_match(user['authors'], fetched.get('authors', [])):
            return False
    if user.get('year') and fetched.get('year') and str(user['year']) != str(fetched['year']):
        return False
    # A near-title correction needs an independent author signal.
    return similarity >= 0.97 or bool(user.get('authors') and fetched.get('authors'))


def select_candidate(user, candidates):
    if isinstance(candidates, dict):
        candidates = [candidates]
    unique = {}
    for candidate in candidates or []:
        if verify_work_identity(user, candidate):
            unique[candidate.get('doi') or normalized(candidate['title'])] = candidate
    ranked = sorted(unique.values(), key=lambda m: title_similarity(user.get('title'), m['title']), reverse=True)
    if len(ranked) > 1:
        first = title_similarity(user['title'], ranked[0]['title'])
        second = title_similarity(user['title'], ranked[1]['title'])
        if first - second < 0.05:
            return {}, True
    return (ranked[0] if ranked else {}), False
