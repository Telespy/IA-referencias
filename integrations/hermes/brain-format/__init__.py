"""Hermes command and tool; the slash command returns the API report unchanged."""

import json
import logging
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def notify_processing():
    """Use Hermes' bound chat context so simultaneous requests stay isolated."""
    try:
        from gateway.session_context import get_session_env, session_context_engaged
        if not session_context_engaged() or get_session_env('HERMES_SESSION_PLATFORM') != 'telegram':
            return
        chat_id = get_session_env('HERMES_SESSION_CHAT_ID')
        thread_id = get_session_env('HERMES_SESSION_THREAD_ID')
        if not re.fullmatch(r'-?[0-9]+', chat_id or ''):
            return
        if thread_id and not re.fullmatch(r'[0-9]+', thread_id):
            return
        from tools.send_message_tool import send_message_tool
        target = 'telegram:' + chat_id + (':' + thread_id if thread_id else '')
        result = send_message_tool({
            'target': target,
            'message': 'Recebi sua lista. Estou consultando as fontes e corrigindo as referencias. Aguarde o relatorio com as pendencias.',
        })
        data = json.loads(result) if isinstance(result, str) else result
        if not isinstance(data, dict) or not data.get('success'):
            logger.warning('Brain Format: nao foi possivel confirmar o aviso de processamento.')
    except ImportError:
        return  # Standalone tests/CLI do not have a Hermes gateway.
    except Exception:
        # A notification failure must not discard the bibliography or leak secrets.
        logger.warning('Brain Format: falha ao enviar aviso de processamento; correcao continua.')


HELP = (
    'Envie /referencias seguido da lista, uma referencia por linha.\n'
    'Exemplo:\n/referencias\n'
    'Titulo: ELMO 1.0: a helmet interface for CPAP and high-flow oxygen delivery\n'
    'Lei federal 11892/2008\nCamara dos Deputados. PL 2630/2020\nSenado Federal. PL 2338/2023\n'
    'STF ADI 4449/AL\nSTF RE 663696/MG\n\n'
    'O resultado inclui referencias ABNT, alteracoes, fontes e pendencias. '
    'Dados nao confirmados sao marcados para revisao. '
    'Para listas grandes, envie lotes menores ou use a interface web local.'
)


def request_correction(text, online=True):
    endpoint = os.environ.get('BRAIN_FORMAT_URL', 'http://brain-format:8000').rstrip('/')
    payload = json.dumps({'text': text, 'online': online}).encode('utf-8')
    request = Request(endpoint + '/api/format', data=payload,
                      headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=600) as response:
            data = json.load(response)
        if not isinstance(data.get('results'), list) or not isinstance(data.get('abnt_full'), str):
            raise ValueError('invalid response')
        return data
    except HTTPError as exc:
        if exc.code in {400, 413, 422, 429}:
            return {'error': 'Lista invalida ou limite excedido. Use ate 50 referencias, uma por linha, com ate 4000 caracteres cada. Em caso de muitas consultas, aguarde um minuto.'}
        return {'error': 'API indisponivel. A lista nao foi corrigida; tente novamente.'}
    except (URLError, TimeoutError, OSError, ValueError):
        return {'error': 'Nao foi possivel obter um resultado valido da API. Nenhuma correcao foi confirmada.'}


def reference_command(raw_args):
    if not raw_args.strip():
        return HELP
    started = time.monotonic()
    logger.info('Brain Format: comando /referencias recebido; iniciando consulta.')
    notify_processing()
    result = request_correction(raw_args)
    if result.get('error'):
        logger.warning('Brain Format: consulta falhou apos %.1fs.', time.monotonic() - started)
        return result['error']
    summary = result.get('summary', {})
    logger.info('Brain Format: consulta concluida em %.1fs; total=%s, revisao=%s, falhas=%s.',
                time.monotonic() - started, result['total'], summary.get('needs_review', 0), summary.get('error', 0))
    header = (f'Brain Format: {result["total"]} referencias. '
              f'{summary.get("verified", 0)} conferidas nas fontes; '
              f'{summary.get("needs_review", 0)} para revisao; '
              f'{summary.get("error", 0)} com falha.\n\n')
    return header + result['abnt_full']


def correction_tool(args, **kwargs):
    text = args.get('text', '')
    if not isinstance(text, str) or not text.strip():
        return json.dumps({'error': HELP}, ensure_ascii=False)
    result = request_correction(text)
    if result.get('error'):
        return json.dumps(result, ensure_ascii=False)
    # The report already includes the evidence. Avoid triplicating it in a
    # small local model's context with APA and comparative reports as well.
    compact = {key: result[key] for key in ('success', 'total', 'abnt_full')}
    # Hermes treats any literal "error" key in its preview as a failed tool.
    # Keep per-item failures visible without mislabelling a completed batch.
    summary = result.get('summary', {})
    compact['summary'] = {
        'verified': summary.get('verified', 0),
        'needs_review': summary.get('needs_review', 0),
        'processing_failures': summary.get('error', 0),
    }
    return json.dumps(compact, ensure_ascii=False)


def register(ctx):
    ctx.register_command('referencias', reference_command,
                         description='Corrigir lista de referencias ABNT com avisos',
                         args_hint='<lista de referencias>')
    ctx.register_tool(
        name='corrigir_referencias', toolset='brain_format', handler=correction_tool,
        schema={
            'name': 'corrigir_referencias',
            'description': (
                'Corrige referencias pela API local. Envie o texto original integral, '
                'aceitando titulos, DOI, ISBN, leis federais, projetos de lei, ADI e RE do STF. '
                'Nao adivinhe edicao, jurisdicao ou casa: preserve os pedidos de esclarecimento e candidatos. '
                'uma referencia por linha. Reproduza abnt_full sem alterar referencias, '
                'fontes ou avisos. Nunca afirme ausencia de erros. Se a API falhar, '
                'informe a falha. Para retorno direto e fiel use /referencias.'
            ),
            'parameters': {'type': 'object', 'properties': {
                'text': {'type': 'string', 'description': 'Lista original de referencias.', 'maxLength': 200000}
            }, 'required': ['text'], 'additionalProperties': False},
        },
    )
