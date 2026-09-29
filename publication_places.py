"""Normalize a supplied place, never infer a publication location from a brand."""

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from reference_validation import normalized


AUTHORITY_PATH = Path(__file__).parent / 'data' / 'brazilian_places.json'
RULE_SOURCE = 'https://more.ufsc.br/suporte/ajuda'
# Bibliographic examples include historical and international homonyms that a
# current municipality list cannot rule out (e.g. Brasilia, DF / Brasilia, MG).
QUALIFICATION_NAMES = {'brasilia', 'barcelona', 'coimbra', 'matozinhos', 'nazare'}
QUALIFICATION_SOURCE = 'https://www.mestrados.uemg.br/images/livros-pdf/catalogo-2024/Normalizacao/normalizacao.pdf'
BRAZIL_NAMES = {'brasil', 'brazil', 'br', 'bra'}


@dataclass
class PlaceResult:
    value: str
    original: str
    comparison_key: str = ''
    warnings: list = field(default_factory=list)
    details: dict = field(default_factory=dict)


@lru_cache(maxsize=1)
def _authority():
    try:
        data = json.loads(AUTHORITY_PATH.read_text(encoding='utf-8'))
        if data['schema_version'] != 1 or len(data['states']) != 27 or len(data['cities']) < 5500:
            return None
        places, states = {}, {}
        for uf, name in data['states'].items():
            states[normalized(uf)] = uf
            states[normalized(name)] = uf
        for identifier, name, uf in data['cities']:
            if uf not in data['states'] or not isinstance(name, str) or not isinstance(identifier, int):
                return None
            places.setdefault(normalized(name), []).append({'id': identifier, 'name': name, 'uf': uf})
        return data, places, states
    except (OSError, ValueError, KeyError, TypeError):
        return None


def normalize_place(value):
    original = str(value or '').strip()
    result = PlaceResult(value=original, original=original, comparison_key=normalized(original))
    if not original or normalized(original) in {'s l', 'sine loco', 'sem local'}:
        return result
    # Preserve multiple places and uncertain catalog strings for human review.
    bracketed = original.startswith('[') and original.endswith(']')
    inner = original[1:-1].strip() if bracketed else original
    if any(mark in inner for mark in (';', '[', ']', '?')):
        result.warnings.append(('PLACE_FORMAT_REVIEW', 'Local com multiplas cidades ou qualificacao incerta; confira a forma no documento.'))
        return result
    authority = _authority()
    if authority is None:
        result.warnings.append(('PLACE_AUTHORITY_UNAVAILABLE', 'Base geografica local indisponivel; local original preservado.'))
        return result
    data, places, states = authority
    # Recognize catalog forms such as City, UF, Country and City (UF), Country.
    separated = re.sub(r'\s*\(([^()]+)\)\s*', r', \1, ', inner)
    separated = re.sub(r'\s*[-/]\s*([A-Za-z]{2})(?=\s*(?:,|$))',
                       lambda match: ', ' + match[1] if normalized(match[1]) in states else match[0], separated)
    separated = re.sub(r'\s+[-\u2013]\s+', ', ', separated)
    parts = [part.strip().rstrip(' :') for part in separated.split(',') if part.strip().rstrip(' :')]
    if not parts:
        return result
    name = normalized(parts[0])
    qualifiers = parts[1:]
    brazil = any(normalized(part) in BRAZIL_NAMES for part in qualifiers)
    uf_values = {states[normalized(part)] for part in qualifiers if normalized(part) in states}
    unknown = [part for part in qualifiers if normalized(part) not in states and normalized(part) not in BRAZIL_NAMES]
    candidates = places.get(name, [])
    # Never turn Cambridge, MA, USA into a Brazilian city or discard its country.
    if unknown or len(uf_values) > 1:
        if brazil or (uf_values and candidates):
            result.warnings.append(('PLACE_QUALIFIER_CONFLICT', 'Qualificadores do local divergentes ou nao reconhecidos; valor original preservado.'))
        return result
    if not candidates:
        if brazil or uf_values:
            result.warnings.append(('PLACE_NOT_IN_AUTHORITY', 'Local nao identificado na base brasileira atual; pode ser historico. Nao foi substituido nem associado a uma sede atual.'))
        return result
    if not qualifiers and name not in QUALIFICATION_NAMES and len(candidates) == 1:
        # A bare name can belong to another country; do not infer a UF or country.
        result.comparison_key = 'br:' + str(candidates[0]['id'])
        return result

    uf = next(iter(uf_values), '')
    matched = [place for place in candidates if not uf or place['uf'] == uf]
    if not matched:
        result.warnings.append(('PLACE_STATE_CONFLICT', 'Cidade e UF nao correspondem na base brasileira atual; confira a fonte, inclusive nomes historicos.'))
        return result
    ambiguous = len({place['uf'] for place in candidates}) > 1 or name in QUALIFICATION_NAMES
    if ambiguous and not uf:
        result.warnings.append(('AMBIGUOUS_PLACE', 'Nome de cidade ambiguo; informe a UF ou o pais conforme a publicacao. Nenhuma localizacao foi presumida.'))
        return result
    selected = matched[0]
    city = selected['name'] + (', ' + uf if ambiguous else '')
    result.value = '[' + city + ']' if bracketed else city
    result.comparison_key = 'br:' + str(selected['id'])
    result.details = {
        'original_value': original, 'normalized_value': result.value,
        'rule_source': RULE_SOURCE, 'geographic_source': data['source'],
        'geographic_source_urls': data['source_urls'], 'retrieved_at': data['retrieved_at'],
        'scope': 'Geographic spelling and disambiguation only; not bibliographic verification.',
        'ibge_id': selected['id'], 'uf': selected['uf'], 'qualification_required': ambiguous,
    }
    if name in QUALIFICATION_NAMES:
        result.details['qualification_source'] = QUALIFICATION_SOURCE
    return result
