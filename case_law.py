"""Resolve STF ADI judgments against the official case docket and signed PDF."""

import hashlib
import io
import re
import ssl
from datetime import datetime
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from sources import LookupFailure, _stamp


STF_HOST = 'portal.stf.jus.br'
CA_URL = 'https://secure.globalsign.com/cacert/gsgccr6alphasslca2025.crt'
CA_SHA256 = 'a883559231f8388daf35ce41c8101040ae8fd9b656434247b9475af592cc08ca'
USER_AGENT = 'Mozilla/5.0 (compatible; BrainFormat/3.0; official case-law lookup)'
MAX_PDF_BYTES = 12 * 1024 * 1024


def parse_case_request(raw):
    text = re.sub(r'^\s*(?:BRASIL\.\s*)?(?:Supremo Tribunal Federal(?:\s*\([^)]*\))?\.?\s*)?', '', raw, flags=re.I)
    match = re.search(r'\b(ADI|A[cç][aã]o Direta de Inconstitucionalidade|RE|Recurso Extraordin[aá]rio)\s*(?:n[.\u00ba\u00b0\u2070]?\s*)?(\d[\d.]*)\s*(?:/\s*([A-Z]{2}))?', text, re.I)
    if not match or (not re.search(r'\bSTF\b|Supremo Tribunal Federal|\bADI\b|A[cç][aã]o Direta de Inconstitucionalidade|\bRE\b|Recurso Extraordin[aá]rio', raw, re.I)):
        return {}
    number = str(int(match[2].replace('.', '')))
    if number == '0' or len(number) > 7:
        return {}
    state = (match[3] or '').upper()
    page = re.search(r'\bp\.\s*(\d+)\b', raw, re.I)
    case_class = 'ADI' if re.fullmatch(r'ADI|A[cç][aã]o Direta de Inconstitucionalidade', match[1], re.I) else 'RE'
    return {'item_type': 'caseLaw', 'case_class': case_class, 'case_number': number,
            'case_state': state, 'case_page': page[1] if page else ''}


class _SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != 'https' or target.hostname != STF_HOST or target.port or target.username:
            raise LookupFailure('Redirecionamento do STF saiu do dominio oficial.')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


@lru_cache(maxsize=1)
def _stf_opener():
    try:
        response = requests.get(CA_URL, timeout=(5, 10), allow_redirects=False)
        response.raise_for_status()
        intermediate = response.content
    except requests.RequestException as exc:
        raise LookupFailure('Certificado intermediario do STF indisponivel.') from exc
    if hashlib.sha256(intermediate).hexdigest() != CA_SHA256:
        raise LookupFailure('Certificado intermediario do STF mudou; conexao suspensa.')
    context = ssl.create_default_context()
    context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(intermediate))
    return build_opener(HTTPSHandler(context=context), _SameHostRedirect())


def _stf_get(url, *, pdf=False):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != STF_HOST or parsed.port or parsed.username:
        raise ValueError('STF URL outside allowlist')
    request = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/pdf' if pdf else 'text/html'})
    try:
        with _stf_opener().open(request, timeout=20) as response:
            if response.status != 200 or urlsplit(response.url).hostname != STF_HOST:
                raise LookupFailure('Fonte STF indisponivel ou resposta incompleta.')
            content = response.read(MAX_PDF_BYTES + 1)
            if len(content) > MAX_PDF_BYTES:
                raise LookupFailure('Documento do STF excedeu o limite de tamanho.')
            if pdf and not content.startswith(b'%PDF-'):
                raise LookupFailure('O link oficial nao retornou um PDF.')
            if not pdf and b'<html' not in content[:1024].lower() and b'<div' not in content[:1024].lower():
                raise LookupFailure('O portal do STF nao retornou HTML valido.')
            return content, response.url
    except (HTTPError, URLError, OSError, ssl.SSLError) as exc:
        raise LookupFailure('Portal STF indisponivel ou conexao segura falhou.') from exc


def _docket(html, case_class, number):
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(' ', strip=True)
    if not re.search(rf'\b{case_class}\s*{re.escape(number)}\b', text, re.I):
        return {}
    relator = re.search(r'Relator\(a\):\s*(?:MIN\.?\s*)?([^<]+?)(?=Redator do ac[oó]rd[aã]o:|Relator\(a\) do [uú]ltimo incidente:|$)', text, re.I)
    return {'relator': ' '.join(relator[1].split()).title() if relator else ''}


def _publications(html):
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    for row in soup.select('li'):
        heading = row.select_one('.andamento-nome')
        if not heading or not re.search(r'Publicado ac[oó]rd[aã]o,\s*DJE', heading.get_text(' ', strip=True), re.I):
            continue
        date = row.select_one('.andamento-data')
        link = next((a for a in row.select('a[href]') if 'Inteiro teor do ac' in a.get_text(' ', strip=True)), None)
        if not date or not link:
            continue
        identifier = re.fullmatch(r'downloadPeca\.asp\?id=(\d+)&ext=\.pdf', link['href'])
        if not identifier:
            continue
        detail = row.get_text(' ', strip=True)
        disclosed = re.search(r'divulgado em (\d{2}/\d{2}/\d{4})', detail, re.I)
        results.append({'publication_date': date.get_text(' ', strip=True),
                        'disclosure_date': disclosed[1] if disclosed else '',
                        'url': f'https://{STF_HOST}/processos/{link["href"]}'})
    return results


def _first_pdf_text(pdf_bytes, case_class, number):
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
        if reader.is_encrypted or len(reader.pages) < 2:
            return {}
        pages = [reader.pages[i].extract_text() or '' for i in range(min(5, len(reader.pages)))]
    except Exception as exc:
        raise LookupFailure('PDF oficial do ac_or_dao nao pode ser lido.') from exc
    first = pages[0]
    if re.search(r'EMB(?:ARGOS)?\.?\s*(?:DECL|DECLARAT)', first[:450], re.I):
        return {}
    number_pattern = f'{int(number):,}'.replace(',', r'\.')
    heading = (rf'A[CÇ][AÃ]O DIRETA DE INCONSTITUCIONALIDADE\s+{number_pattern}' if case_class == 'ADI'
               else rf'(?<!NO )RECURSO EXTRAORDIN[AÁ]RIO\s+{number_pattern}')
    if not re.search(heading, first[:450], re.I):
        return {}
    state = re.search(rf'\b{case_class}\s+{re.escape(number)}\s*/\s*([A-Z]{{2}})\b', ' '.join(pages[1:3]), re.I)
    if not state:
        return {}
    date = re.search(r'\b(\d{2}/\d{2}/\d{4})\s+(PLEN[AÁ]RIO|PRIMEIRA TURMA|SEGUNDA TURMA)\b', first, re.I)
    relator = re.search(r'\bRELATOR\s*:\s*MIN\.?\s*([^\n]+)', first, re.I)
    if not date or not relator:
        return {}
    pieces = []
    for page in pages:
        body = re.split(r'\n(?:\d+\s*\n)?Supremo Tribunal Federal\s*\nDocumento assinado', page, maxsplit=1)[0]
        body = re.sub(r'^Ementa e Ac[oó]rd[aã]o\s*', '', body, flags=re.I)
        body = re.sub(rf'^{case_class}\s+{re.escape(number)}\s*/\s*[A-Z]{{2}}\s*', '', body, flags=re.I)
        pieces.append(body)
    joined = '\n'.join(pieces)
    end = re.search(r'A\s+C\s+[OÓ]\s+R\s+D\s+[AÃ]\s+O', joined, re.I)
    if not end:
        return {}
    if case_class == 'RE':
        start = re.search(r'\bEMENTA\s*:\s*', joined[:end.start()], re.I)
        ementa_start = start.end() if start else None
    else:
        start = re.search(r'(?m)^([A-ZÀ-Ý][A-ZÀ-Ý\s\u2013-]{8,}\.\s+[A-ZÀ-Ý][a-zà-ÿ])', joined[:end.start()])
        ementa_start = start.start() if start else None
    if not start:
        return {}
    ementa = ' '.join(joined[ementa_start:end.start()].split())
    if not 80 <= len(ementa) <= 8000 or 'Documento assinado' in ementa:
        return {}
    return {'case_state': state[1].upper(), 'judgment_date': date[1],
            'court_body': {'PLENÁRIO': 'Tribunal Pleno', 'PRIMEIRA TURMA': 'Primeira Turma',
                           'SEGUNDA TURMA': 'Segunda Turma'}[date[2].upper()],
            'relator': ' '.join(relator[1].split()).title(), 'ementa': ementa.rstrip('.') + '.'}


def fetch_stf_case(query):
    number = query['case_number']
    case_class = query['case_class']
    if case_class not in {'ADI', 'RE'} or not re.fullmatch(r'\d{1,7}', number):
        return {}
    listing = f'https://{STF_HOST}/processos/listarProcessos.asp?classe={case_class}&numeroProcesso={number}'
    html, final_url = _stf_get(listing)
    incident = parse_qs(urlsplit(final_url).query).get('incidente', [''])[0]
    if not re.fullmatch(r'\d{1,12}', incident) or not _docket(html, case_class, number):
        return {}
    records, _ = _stf_get(f'https://{STF_HOST}/processos/abaAndamentos.asp?incidente={incident}&imprimir=')
    matches = []
    for publication in _publications(records)[:8]:
        pdf, _ = _stf_get(publication['url'], pdf=True)
        document = _first_pdf_text(pdf, case_class, number)
        if document and (not query.get('case_state') or query['case_state'] == document['case_state']):
            matches.append((publication, document))
    if len(matches) != 1:
        return {}
    publication, document = matches[0]
    judgment = datetime.strptime(document['judgment_date'], '%d/%m/%Y').date()
    published = datetime.strptime(publication['publication_date'], '%d/%m/%Y').date()
    if published < judgment:
        return {}
    formatted = f'{int(number):,}'.replace(',', '.')
    title_class = {'ADI': 'Ação Direta de Inconstitucionalidade', 'RE': 'Recurso Extraordinário'}[case_class]
    meta = _stamp({'item_type': 'caseLaw', 'case_class': case_class, 'case_number': number,
                   **document, 'title': f'{title_class} {formatted}/{document["case_state"]}',
                   'jurisdiction': 'BRASIL', 'court': 'Supremo Tribunal Federal',
                   'authors': [{'family': 'BRASIL', 'given': '', 'is_corporate': True}],
                   'city': 'Brasília, DF', 'publisher': 'Supremo Tribunal Federal',
                   'year': str(published.year), 'publication_date': publication['publication_date'],
                   'disclosure_date': publication['disclosure_date'], 'url': publication['url'],
                   'case_page': query.get('case_page', '')},
                  'Supremo Tribunal Federal - Inteiro teor do acordao', publication['url'])
    if query.get('case_page'):
        meta['_issues'] = [{'code': 'CASE_PAGE_UNVERIFIED', 'message':
                            'Pagina informada pelo usuario; a paginacao do PDF pode diferir da edicao do DJe.',
                            'severity': 'warning', 'field': 'case_page'}]
    return meta
