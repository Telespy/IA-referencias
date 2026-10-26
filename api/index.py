import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from main import process_reference_line
from correction import reference_report
from reference_extractor import MAX_DOCUMENT_BYTES, extract_references

MAX_PAYLOAD_BYTES = 512 * 1024
MAX_UPLOAD_REQUEST_BYTES = MAX_DOCUMENT_BYTES + 64 * 1024
MAX_REFERENCES_COUNT = 50
MAX_LINE_LENGTH = 4000
_rate_limits = {}
app = FastAPI(title='Brain Format API', version='3.0.0', docs_url='/api/docs',
              openapi_url='/api/openapi.json',
              description='Referencias ABNT com evidencias, correcoes e pendencias de revisao.')


@app.middleware('http')
async def limits_and_headers(request: Request, call_next):
    if request.method == 'POST':
        is_upload = request.url.path == '/api/extract'
        limit = MAX_UPLOAD_REQUEST_BYTES if is_upload else MAX_PAYLOAD_BYTES
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > limit:
                message = 'Limite de 10 MB excedido.' if is_upload else 'Limite de 512 KB excedido.'
                return JSONResponse(status_code=413, content={'detail': message})
        request._body = bytes(body)
    if request.url.path == '/api/format':
        now = time.monotonic()
        expired = [ip for ip, times in _rate_limits.items() if now - times[-1] > 60]
        for ip in expired:
            del _rate_limits[ip]
        client = request.client.host if request.client else 'local'
        recent = [t for t in _rate_limits.get(client, []) if now - t < 60]
        if len(recent) >= 60:
            return JSONResponse(status_code=429, content={'detail': 'Aguarde um minuto antes de tentar novamente.'})
        _rate_limits[client] = recent + [now]
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    if not request.url.path.startswith('/api/docs'):
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        )
    return response


class FormatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_PAYLOAD_BYTES)
    online: bool = True
    input_format: Literal['lines', 'blocks'] = 'lines'


class ReferenceResult(BaseModel):
    raw: str
    item_type: str
    item_type_label: str
    abnt: str
    citation: str = ''
    apa: str
    meta: dict[str, Any] = Field(default_factory=dict)
    status: str
    approved: bool
    identity_verified: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    corrections: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    unverified_fields: list[str] = Field(default_factory=list)
    verification_scope: str = ''


class FormatResponse(BaseModel):
    success: bool
    total: int
    summary: dict[str, int]
    results: list[ReferenceResult]
    abnt_full: str
    apa_full: str
    comp_full: str


def sanitize_input(text):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text).strip()


def split_references(text, input_format='lines'):
    """Do not guess line wrapping: block mode must be explicitly selected."""
    text = sanitize_input(text)
    if input_format == 'blocks':
        return [' '.join(block.split()) for block in re.split(r'\n\s*\n', text) if block.strip()]
    return [line.strip() for line in text.splitlines() if line.strip()]


@app.get('/api/health')
def health_check():
    return {'status': 'healthy', 'service': 'brain-format-api', 'version': '3.0.0'}


def _process(line, online):
    try:
        return process_reference_line(line, online=online)
    except Exception:
        message = 'Falha ao processar esta referencia. Entrada preservada; tente novamente ou revise manualmente.'
        return {'raw': line, 'item_type': 'unknown', 'item_type_label': 'Nao identificado',
                'abnt': line, 'apa': line, 'status': 'error', 'approved': False,
                'warnings': [message], 'issues': [{'code': 'PROCESSING_ERROR', 'message': message, 'severity': 'error'}]}


@app.post('/api/extract')
def extract_document_references(file: UploadFile = File(...)):
    """Extrai as entradas da seção de referências de um DOCX, PDF, TXT ou MD. Não consulta fontes externas."""
    content = file.file.read(MAX_DOCUMENT_BYTES + 1)
    try:
        return extract_references(file.filename or '', content)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post('/api/format', response_model=FormatResponse)
def format_references(req: FormatRequest):
    lines = split_references(req.text, req.input_format)
    if not lines:
        raise HTTPException(400, 'Nenhuma referencia informada.')
    if len(lines) > MAX_REFERENCES_COUNT:
        raise HTTPException(400, 'Limite de 50 referencias por lote.')
    if any(len(line) > MAX_LINE_LENGTH for line in lines):
        raise HTTPException(400, 'Uma referencia excede 4000 caracteres. Nenhum texto foi truncado.')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda line: _process(line, req.online), lines))
    summary = {state: sum(r['status'] == state for r in results)
               for state in ('verified', 'needs_review', 'error')}
    abnt = '\n\n'.join(reference_report(r, i) for i, r in enumerate(results, 1))
    apa = '\n\n'.join(reference_report(r, i, 'apa') for i, r in enumerate(results, 1))
    combined = '\n\n'.join(f'Original: {r["raw"]}\n' + reference_report(r, i) + f'\nAPA: {r["apa"]}'
                           for i, r in enumerate(results, 1))
    return {'success': not summary['error'], 'total': len(results), 'summary': summary,
            'results': results, 'abnt_full': abnt, 'apa_full': apa, 'comp_full': combined}


public_dir = ROOT_DIR / 'public'
if public_dir.exists():
    app.mount('/', StaticFiles(directory=str(public_dir), html=True), name='public')
