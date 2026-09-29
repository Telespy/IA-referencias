"""Run inside Hermes: check authorization, then optionally send an integration test.

PowerShell: Get-Content scripts/verify_telegram.py -Raw |
  docker compose exec -T --user hermes hermes python - --chat-id YOUR_ID --send-test
This does not consume Telegram updates or start a second polling process.
"""

import argparse
import asyncio
import json
import logging
import os


REFERENCE = (
    'CANEN, Ana; OLIVEIRA, Angela M. A. de. Multiculturalismo e curr\u00edculo em a\u00e7\u00e3o: um estudo de caso. '
    'Rev. Bras. Educ. [online]. 2002, n.21, pp.61-74. ISSN 1413-2478.\n'
    'CARNEIRO, Aparecida Sueli. A constru\u00e7\u00e3o do outro como n\u00e3o-ser como fundamento do ser. '
    '2005. Tese (Doutorado) - Universidade de S\u00e3o Paulo, S\u00e3o Paulo, 2005. '
    'Dispon\u00edvel em: xxxx. Acesso em: 11 set. 2026.'
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--chat-id', required=True)
    parser.add_argument('--send-test', action='store_true')
    args = parser.parse_args()
    if not args.chat_id.isdigit() or args.chat_id not in os.environ.get('TELEGRAM_ALLOWED_USERS', '').split(','):
        raise SystemExit('O destino deve ser um usuario explicitamente autorizado neste Docker.')

    from gateway.config import load_gateway_config, Platform
    from gateway.run import GatewayRunner
    from gateway.session import SessionSource
    from gateway.platforms.event import MessageEvent, MessageType
    from tools.send_message_tool import send_message_tool

    config = load_gateway_config()
    runner = GatewayRunner(config)
    source = SessionSource(platform=Platform.TELEGRAM, chat_id=args.chat_id,
                           chat_type='dm', user_id=args.chat_id)
    authorized = runner._is_user_authorized(source)
    print(json.dumps({'authorized_by_hermes': authorized,
                      'typing_enabled': config.platforms[Platform.TELEGRAM].typing_indicator,
                      'multiplex_profiles': config.multiplex_profiles}), flush=True)
    if not authorized:
        return 1
    if not args.send_test:
        return 0
    event = MessageEvent(text='/referencias\n' + REFERENCE, source=source, message_type=MessageType.COMMAND)
    try:
        handled, report, command = asyncio.run(
            runner._hm_dispatch_quick_and_plugin_commands(event, source, event.get_command()))
        if not handled or command != 'referencias' or not report:
            raise RuntimeError('Comando nao processado')
        if 'Brain Format: 2 referencias' not in report or 'endereco HTTP/HTTPS valido' not in report:
            raise RuntimeError('O relatorio nao passou nos criterios do teste')
        delivery = send_message_tool({
            'target': 'telegram:' + args.chat_id,
            'message': 'Teste integrado do corretor (entrada de teste local):\n\n' + report,
        })
        delivery = json.loads(delivery) if isinstance(delivery, str) else delivery
        print(json.dumps({'simulated_command_processed': handled, 'reference_count': 2,
                          'report_delivered': bool(delivery.get('success')),
                          'message_id': delivery.get('message_id'),
                          'real_inbound_message_tested': False}), flush=True)
        return 0 if delivery.get('success') else 1
    finally:
        if runner._executor:
            runner._executor.shutdown(wait=True)


if __name__ == '__main__':
    # Never dump exception URLs containing a bot credential to the terminal.
    logging.basicConfig(level=logging.ERROR)
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'test_failed': True, 'failure_type': type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
