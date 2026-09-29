"""Brazilian federal legal references, resolved only against official APIs."""

import re
import unicodedata
from datetime import datetime
from urllib.parse import urlencode, urlsplit

from bs4 import BeautifulSoup

from config import ABNT_MONTHS_PT
from sources import LookupFailure, _get, _json, _stamp

SENADO = 'https://legis.senado.leg.br/dadosabertos'
CAMARA = 'https://dadosabertos.camara.leg.br/api/v2'
MONTHS = ('janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro').split()
DOU_PLACE_SOURCE = ('https://www.gov.br/imprensanacional/pt-br/centrais-de-conteudo/'
                    'info-produtos-da-exposicao-especial/transferencia-da-imprensa-nacional-para-brasilia')
HOUSE_PLACES = {
    'camara': 'https://www2.camara.leg.br/a-camara/visiteacamara/telefone-e-endereco-da-camara-dos-deputados',
    'senado': 'https://www12.senado.leg.br/institucional/falecomosenado',
}


def _fold(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c)).lower()


def parse_legal_request(text):
    text = text.strip()
    # Unicode NFKD turns superscript zero in "n⁰" into the digit 0.
    folded = _fold(text.replace('\u2070', '\u00ba'))
    match = re.search(r'\b(projeto de lei complementar|projeto de lei|plp|pls|plc|pl|lei complementar|lei)\b', folded)
    if not match or match.start() > 100:
        return {}
    prefix = folded[:match.start()].strip(' .:')
    # Do not turn a book/article mentioning a law into a legal document.
    if prefix and not re.fullmatch(r'[a-z .()/-]+', prefix):
        return {}
    if prefix and not (prefix == 'brasil' or 'senado' in prefix or 'camara' in prefix
                       or text[:match.start()].strip(' .:').isupper()):
        return {}
    kind = match[1]
    bill = kind.startswith(('projeto', 'pl'))
    tail = folded[match.end():]
    number = re.match(r'\s*(?:(?:federal|estadual|municipal|distrital)\s+)?(?:n(?:o|[.])?\s*[o°º.]?\s*)?(\d[\d.]*)', tail)
    number_value = str(int(number[1].replace('.', ''))) if number else ''
    rest = tail[number.end():] if number else tail
    year = re.match(r'\s*(?:/|,?\s+de\s+)(\d{4})\b', rest)
    date_match = re.match(r'\s*,?\s*de\s+(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})', rest)
    year_value = year[1] if year else date_match[3] if date_match else ''
    house = 'senado' if 'senado' in prefix or re.search(r'\b(?:do\s+)?senado(?:\s+federal)?\b', rest) else ''
    if 'camara dos deputados' in prefix or re.search(r'\bcamara dos deputados\b', rest):
        house = 'camara'
    scope = 'federal' if prefix == 'brasil' or 'federal' in folded[:match.end() + 20] or house else ''
    if re.search(r'\b(estadual|municipal|distrital|distrito federal|assembleia|prefeitura)\b', folded[:match.end() + 25]) or (prefix and prefix != 'brasil' and not house):
        scope = 'other'
    sigla = {'plp': 'PLP', 'pls': 'PLS', 'plc': 'PLC', 'projeto de lei complementar': 'PLP'}.get(kind, 'PL') if bill else ('LCP' if kind == 'lei complementar' else 'LEI')
    label = ('Projeto de lei complementar' if sigla == 'PLP' else 'Projeto de lei') if bill else ('Lei complementar' if sigla == 'LCP' else 'Lei')
    title = f'{label} n. {number_value}' if number_value else text
    if year_value and number_value:
        title += f', de {year_value}'
    if date_match and number_value:
        title = text[match.start():match.end() + (number.end() if number else 0) + date_match.end()].strip()
    return {'item_type': 'bill' if bill else 'legislation', 'title': title,
            'legal_number': number_value, 'legal_year': year_value, 'legal_type': sigla,
            'legal_scope': scope, 'legislative_house': house,
            'jurisdiction': 'BRASIL' if scope == 'federal' else text[:match.start()].strip(' .:') if prefix else '',
            'year': year_value}


def legal_issue(code, message, severity='warning'):
    return {'code': code, 'message': message, 'severity': severity, 'field': None}


def _list(value):
    return value if isinstance(value, list) else [value] if isinstance(value, dict) else []


def _date(value, long=False):
    parsed = datetime.strptime(value, '%d/%m/%Y').date()
    if long:
        month = MONTHS[parsed.month - 1].replace('marco', 'mar\u00e7o')
        return f'{parsed.day} de {month} de {parsed.year}'
    return f'{parsed.day} {ABNT_MONTHS_PT[parsed.month]} {parsed.year}'


def _official_link(value, hosts):
    parsed = urlsplit(value or '')
    return value if parsed.scheme == 'https' and parsed.hostname in hosts and not parsed.username and not parsed.port else ''


def _place(meta, authority_url):
    source = _stamp({}, 'Local institucional (fonte oficial)', authority_url)['_source']
    meta['city'] = '[Bras\u00edlia, DF]'
    meta.setdefault('_sources', [meta['_source']]).append(source)
    meta.setdefault('_field_sources', {})['city'] = source
    meta.setdefault('_issues', []).append(legal_issue(
        'INFERRED_LEGAL_PLACE', 'Local entre colchetes atribuido pela sede oficial do veiculo/orgao; nao extraido do registro bibliografico.', 'info'))
    meta['_derived_fields'] = ['city']
    return meta


def _planalto_url(query):
    year = int(query['legal_year'])
    if query['legal_type'] != 'LEI':
        return ''
    if year < 2003:
        return f'https://www.planalto.gov.br/ccivil_03/leis/l{int(query["legal_number"])}.htm'
    first = 2003 + 4 * ((year - 2003) // 4)
    return (f'https://www.planalto.gov.br/ccivil_03/_ato{first}-{first + 3}/'
            f'{year}/lei/l{int(query["legal_number"])}.htm')


def _planalto_law(query):
    url = _planalto_url(query)
    if not url:
        return {}
    response = _get(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; BrainFormat/3.0; official legislation lookup)',
        'Accept': 'text/html,application/xhtml+xml',
    })
    if response is None:
        return {}
    declared_utf8 = re.search(br'charset\s*=\s*["\']?utf-?8', response.content[:4096], re.I)
    soup = BeautifulSoup(response.content, 'html.parser',
                         from_encoding='utf-8' if declared_utf8 else 'windows-1252')
    for superscript in soup.find_all('sup'):
        if superscript.get_text(strip=True).lower() in {'o', 'º', '°'}:
            superscript.replace_with('º')
    text = ' '.join(soup.get_text(' ', strip=True).split())
    text = re.sub(r'(?<=\d)\s+º(?=\W|$)', 'º', text)
    if not re.search(r'Presid[eê]ncia da Rep[uú]blica', text, re.I):
        return {}
    number = f'{int(query["legal_number"]):,}'.replace(',', '.')
    heading = re.search(
        rf'\bLEI\s+N\s*[.º°o]?\s*{re.escape(number)}\s*,?\s*DE\s+'
        r'(\d{1,2})\s+DE\s+([A-ZÇÃÉÊÍÓÔÚ]+)\s+DE\s+(\d{4})\.?', text, re.I)
    if not heading or heading[3] != query['legal_year']:
        return {}
    month = _fold(heading[2])
    if month not in MONTHS:
        return {}
    try:
        signed = datetime(int(heading[3]), MONTHS.index(month) + 1, int(heading[1])).date()
    except ValueError:
        return {}
    end = re.search(r'\b[OA]\s+PRESIDENT[EA]\s+DA\s+REP[UÚ]BLICA\b', text[heading.end():], re.I)
    if not end or end.start() > 1200:
        return {}
    ementa = text[heading.end():heading.end() + end.start()].strip(' .')
    ementa = re.sub(r'^(?:Mensagem de Veto\s*)?(?:\(Vide [^)]+\)\s*)?', '', ementa, flags=re.I).strip(' .')
    if not ementa or len(ementa) > 750:
        return {}
    dateline = re.search(r'\bBras[ií]lia\s*,\s*' + re.escape(heading[1]) + r'\s+de\s+'
                         + re.escape(heading[2]) + r'\s+de\s+' + re.escape(heading[3]), text, re.I)
    if not dateline:
        return {}
    title = f'Lei nº {number}, de {signed.day} de {heading[2].lower()} de {signed.year}'
    meta = _stamp({**_identity(query), 'title': title, 'jurisdiction': 'BRASIL',
                   'authors': [{'family': 'BRASIL', 'given': '', 'is_corporate': True}],
                   'ementa': ementa + '.', 'legal_date': signed.strftime('%d/%m/%Y'),
                   'city': 'Brasília, DF', 'publisher': 'Presidência da República',
                   'url': url, 'publication_mode': 'planalto', '_official_legal': True},
                  'Presidência da República - Planalto', url)
    meta['_issues'] = [legal_issue('LEGAL_SCOPE',
        'Conferencia bibliografica da pagina do Planalto; nao certifica vigencia nem consolida alteracoes posteriores.', 'info')]
    return meta


def _senado_law(query):
    kind = 'Lei' if query['legal_type'] == 'LEI' else 'Lcp'
    url = f"{SENADO}/legislacao/{kind}/{query['legal_number']}/{query['legal_year']}.json"
    docs = _list(_json(url).get('DetalheDocumento', {}).get('documentos', {}).get('documento'))
    matches = []
    for doc in docs:
        identity = doc.get('identificacao', {})
        date = identity.get('dataassinatura', '')
        expected = 'LEI-n' if kind == 'Lei' else 'LCP'
        if (str(identity.get('numero', '')).lstrip('0') == query['legal_number'].lstrip('0')
                and date[-4:] == query['legal_year'] and identity.get('tipo') == expected):
            matches.append(doc)
    if len(matches) != 1:
        return {}
    doc = matches[0]
    identity = doc['identificacao']
    number = f"{int(query['legal_number']):,}".replace(',', '.')
    label = 'Lei' if kind == 'Lei' else 'Lei complementar'
    meta = _stamp({**_identity(query), 'title': f'{label} n. {number}, de {_date(identity["dataassinatura"], long=True)}',
                   'jurisdiction': 'BRASIL', 'authors': [{'family': 'BRASIL', 'given': '', 'is_corporate': True}],
                   'ementa': str(doc.get('ementa') or '').strip(),
                   'legal_date': identity['dataassinatura'],
                   'url': _official_link(identity.get('urlDocumento'), {'normas.leg.br'}),
                   '_official_legal': True}, 'Senado Federal - Legislacao', url)
    publications = [p for p in _list(doc.get('publicacoes', {}).get('publicacao')) if p.get('tipo') == 'PUB']
    if len(publications) == 1:
        pub = publications[0]
        # The original publication date is distinct from the signature date.
        meta.update(publication_title=re.sub(r'\s+de\s+\d{2}/\d{2}/\d{4}.*$', '', pub.get('fonte', '')).strip(),
                    publication_date=_date(pub['data']) if pub.get('data') else '',
                    page=str(pub.get('pagina') or ''))
        if pub.get('siglaFonte', '').startswith('DOU-'):
            meta.setdefault('_issues', []).append(legal_issue('LEGAL_PUBLICATION_DETAILS',
                'O cadastro informa a pagina inicial; secao e extensao completa da paginacao do Diario Oficial nao foram verificadas. Confira a publicacao original.'))
        if pub.get('siglaFonte', '').startswith('DOU-') and datetime.strptime(pub['data'], '%d/%m/%Y').date().isoformat() >= '1961-01-01':
            _place(meta, DOU_PLACE_SOURCE)
    meta.setdefault('_issues', []).append(legal_issue('LEGAL_SCOPE',
        'Conferencia bibliografica da publicacao original; nao certifica vigencia nem consolida alteracoes posteriores.', 'info'))
    return meta


def _law(query):
    try:
        planalto = _planalto_law(query)
    except LookupFailure:
        planalto = {}
    if planalto:
        return planalto
    return _senado_law(query)


def _bill(query):
    house = query['legislative_house']
    number, year, sigla = query['legal_number'], query['legal_year'], query['legal_type']
    if house == 'camara':
        url = CAMARA + '/proposicoes?' + urlencode({'siglaTipo': sigla, 'numero': number, 'ano': year, 'itens': 100})
        data = _json(url)
        records = [r for r in data.get('dados', []) if r.get('siglaTipo') == sigla
                   and str(r.get('numero')) == number and str(r.get('ano')) == year]
        if len(records) != 1 or any(x.get('rel') == 'next' for x in data.get('links', [])):
            return {}
        identifier = str(records[0].get('id', ''))
        if not identifier.isdigit():
            raise ValueError('Invalid proposition identifier')
        url = CAMARA + '/proposicoes/' + identifier
        detail = _json(url).get('dados', {})
        if (str(detail.get('id')) != identifier or detail.get('siglaTipo') != sigla
                or str(detail.get('numero')) != number or str(detail.get('ano')) != year):
            raise ValueError('Proposition identity mismatch')
        ementa = detail.get('ementa', '')
        link = 'https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=' + identifier
        date = detail.get('dataApresentacao', '')[:10]
        status = detail.get('statusProposicao', {}).get('descricaoSituacao', '')
        status_date = detail.get('statusProposicao', {}).get('dataHora', '')
        publisher = 'C\u00e2mara dos Deputados'
    else:
        url = SENADO + '/processo?' + urlencode({'sigla': sigla, 'numero': number, 'ano': year})
        data = _json(url)
        if not isinstance(data, list):
            raise ValueError('Invalid Senate process response')
        records = [r for r in data if r.get('identificacao') == f'{sigla} {number}/{year}']
        if len(records) != 1:
            return {}
        detail = records[0]
        identifier = str(detail.get('codigoMateria', ''))
        if not identifier.isdigit():
            raise ValueError('Invalid matter identifier')
        link = 'https://www25.senado.leg.br/web/atividade/materias/-/materia/' + identifier
        ementa, date = detail.get('ementa', ''), detail.get('dataApresentacao', '')
        status, status_date = detail.get('situacaoAtual', ''), detail.get('dataSituacaoAtual', '')
        publisher = 'Senado Federal'
    label = {'PLP': 'Projeto de lei complementar', 'PLS': 'Projeto de lei do Senado',
             'PLC': 'Projeto de lei da Camara'}.get(sigla, 'Projeto de lei')
    meta = _stamp({**_identity(query), 'title': f'{label} n. {number}, de {year}',
                   'jurisdiction': 'BRASIL', 'legislative_house': publisher,
                   'authors': [{'family': 'BRASIL. ' + publisher, 'given': '', 'is_corporate': True}],
                   'publisher': publisher, 'ementa': ementa, 'url': link,
                   'presentation_date': date, 'bill_status': status, 'bill_status_date': status_date,
                   '_official_legal': True}, publisher + ' - Dados Abertos', url)
    if date and date >= '1961-01-01':
        _place(meta, HOUSE_PLACES[house])
    meta.setdefault('_issues', []).append(legal_issue('BILL_NOT_LAW',
        'Referencia ao projeto de lei na casa consultada, nao a uma lei sancionada. '
        + (f'Situacao informada pela fonte: {status} ({status_date}).' if status else 'Situacao nao recuperada.'), 'info'))
    return meta


def _identity(query):
    # Never stamp user-supplied bibliographic fields as official evidence.
    return {key: query[key] for key in ('item_type', 'legal_number', 'legal_year', 'legal_type', 'year')}


def fetch_legal_reference(query):
    if not re.fullmatch(r'[0-9]{1,9}', query.get('legal_number', '')) or not re.fullmatch(r'[0-9]{4}', query.get('legal_year', '')):
        return {'issues': [legal_issue('LEGAL_IDENTIFIER_REQUIRED', 'Informe tipo, numero e ano. Exemplo: Lei federal 11892/2008.')]}
    if query['item_type'] == 'bill' and query.get('legal_scope') != 'other' and query.get('legislative_house') not in HOUSE_PLACES:
        return {'issues': [legal_issue('LEGISLATIVE_HOUSE_REQUIRED', 'Informe a casa legislativa: Camara dos Deputados ou Senado Federal.')]}
    if query.get('legal_scope') != 'federal':
        return {'issues': [legal_issue('LEGAL_JURISDICTION_REQUIRED',
            'Confirme a jurisdicao. A consulta automatica cobre normas federais brasileiras; estaduais/municipais precisam de fonte oficial e revisao. Exemplo: Lei federal 11892/2008.')]}
    if query['item_type'] == 'bill' and query.get('legislative_house') not in HOUSE_PLACES:
        return {'issues': [legal_issue('LEGISLATIVE_HOUSE_REQUIRED', 'Informe a casa legislativa: Camara dos Deputados ou Senado Federal.')]}
    meta = _bill(query) if query['item_type'] == 'bill' else _law(query)
    return {'match': meta, 'issues': [] if meta else [legal_issue('LEGAL_NOT_CONFIRMED',
        'Nao foi encontrada correspondencia unica na fonte oficial para este tipo, numero e ano. Isso nao prova inexistencia.') ]}
