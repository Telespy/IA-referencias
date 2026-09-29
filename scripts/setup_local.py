"""Initialize private Docker configuration; enter Telegram secrets locally."""

import argparse
import getpass
import json
import os
import re
import secrets
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parent.parent


def initialize():
    dashboard = ROOT / 'hermes-dashboard.local.env'
    if not dashboard.exists():
        password = secrets.token_urlsafe(24)
        dashboard.write_text(
            f'HERMES_DASHBOARD_BASIC_AUTH_USERNAME=referencias\n'
            f'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD={password}\n'
            f'HERMES_DASHBOARD_BASIC_AUTH_SECRET={secrets.token_hex(32)}\n'
            f'API_SERVER_KEY={secrets.token_hex(32)}\n', encoding='utf-8')
    persisted_key = dotenv_values(ROOT / 'hermes-data/.env').get('API_SERVER_KEY')
    if persisted_key and dotenv_values(dashboard).get('API_SERVER_KEY') != persisted_key:
        set_key(dashboard, 'API_SERVER_KEY', persisted_key)
    telegram = ROOT / 'telegram.local.env'
    if not telegram.exists():
        telegram.write_text('TELEGRAM_BOT_TOKEN=\nTELEGRAM_ALLOWED_USERS=\n', encoding='utf-8')
    print('Configuracao local pronta. Credenciais do painel: hermes-dashboard.local.env')


def normalize_bot_token(value):
    # Copying from formatted messages can include invisible formatting or quotes.
    token = value.translate(str.maketrans('', '', '\u200b\u200c\u200d\ufeff')).strip()
    if token.startswith('TELEGRAM_BOT_TOKEN='):
        token = token.partition('=')[2].strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in '\"\'`':
        token = token[1:-1].strip()
    if not token:
        raise ValueError('Nenhum token foi recebido. Cole o token completo do BotFather.')
    if any(ord(char) < 32 or ord(char) == 127 for char in token):
        raise ValueError('A colagem trouxe caracteres de controle. No Windows, use --telegram para abrir a janela de cadastro; copie somente o token.')
    # Telegram validates the credential; do not assume a fixed token length.
    if len(token) > 512 or not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token):
        raise ValueError('Formato de token invalido. Copie somente o token do BotFather: numeros, dois-pontos e codigo. Nao use o ID, @usuario, API hash ou a mensagem inteira.')
    return token


def read_telegram_window():
    try:
        import tkinter as tk
        from tkinter import simpledialog
    except ImportError:
        raise SystemExit('Janela indisponivel. Instale o suporte Tcl/Tk do Python ou use --telegram-terminal.') from None
    try:
        root = tk.Tk()
    except tk.TclError:
        raise SystemExit('Nao foi possivel abrir a janela. Use --telegram-terminal em um terminal interativo.') from None
    root.withdraw()
    try:
        token = simpledialog.askstring(
            'Brain Format - Telegram',
            'Cole somente o token do BotFather (Ctrl+V).\nO campo oculta os caracteres:',
            show='*', parent=root)
        if token is None:
            return None
        allowed = simpledialog.askstring(
            'Brain Format - Telegram',
            'Informe o ID numerico da sua conta pessoal\n(nao o ID do bot nem o @usuario):', parent=root)
        return None if allowed is None else (token, allowed)
    finally:
        root.destroy()


def read_telegram_credentials(*, terminal=False):
    if os.name == 'nt' and not terminal:
        print('Abrindo janela de cadastro. O token fica oculto por asteriscos.')
        return read_telegram_window()
    token = getpass.getpass('Token do bot (entrada oculta): ')
    allowed = input('Seu ID NUMERICO do Telegram: ')
    return token, allowed


def configure_telegram(*, terminal=False):
    credentials = read_telegram_credentials(terminal=terminal)
    if credentials is None:
        print('Cadastro cancelado; credenciais anteriores preservadas.')
        return
    raw_token, allowed = credentials
    try:
        token = normalize_bot_token(raw_token)
    except ValueError as exc:
        raise SystemExit(f'{exc} Nenhum dado foi salvo.') from None
    allowed = allowed.strip()
    if not re.fullmatch(r'[1-9]\d*', allowed):
        raise SystemExit('Informe seu ID numerico, sem @; nenhum dado foi salvo.')
    try:
        with urlopen(f'https://api.telegram.org/bot{token}/getMe', timeout=15) as response:
            bot = json.load(response)
    except HTTPError as exc:
        if exc.code in (401, 404):
            raise SystemExit('O Telegram recusou o token. Confira no BotFather se ele esta completo e ativo. Nenhum dado foi salvo.') from None
        raise SystemExit('O Telegram esta indisponivel ou limitou a consulta. Tente novamente mais tarde. Nenhum dado foi salvo.') from None
    except (URLError, OSError):
        raise SystemExit('Falha de conexao segura com o Telegram. Isso nao significa token invalido; verifique internet e certificados. Nenhum dado foi salvo.') from None
    except ValueError:
        raise SystemExit('Resposta invalida do Telegram. Nenhum dado foi salvo.') from None
    if (not isinstance(bot, dict) or not bot.get('ok')
            or not isinstance(bot.get('result'), dict) or not bot['result'].get('is_bot')
            or not isinstance(bot['result'].get('username'), str)):
        raise SystemExit('O Telegram nao confirmou os dados do bot. Nenhum dado foi salvo.')
    (ROOT / 'telegram.local.env').write_text(
        f'TELEGRAM_BOT_TOKEN={token}\nTELEGRAM_ALLOWED_USERS={allowed}\n', encoding='utf-8')
    print('Bot validado: @' + bot['result']['username'])
    print('Ative com: docker compose up -d --force-recreate hermes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--telegram', action='store_true', help='Cadastrar bot; no Windows abre uma janela com token oculto.')
    mode.add_argument('--telegram-terminal', action='store_true', help='Cadastrar bot pelo terminal, sem janela.')
    args = parser.parse_args()
    initialize()
    if args.telegram or args.telegram_terminal:
        configure_telegram(terminal=args.telegram_terminal)
