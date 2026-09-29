import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from dotenv import dotenv_values
from scripts import setup_local


TOKEN = '123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghi'
USER_ID = '12345678'


class TokenParsingTests(unittest.TestCase):
    def test_plain_and_copied_wrappers(self):
        for value in (TOKEN, f'  {TOKEN}\r\n', f'"{TOKEN}"', f"'{TOKEN}'",
                      f'`{TOKEN}`', f'\ufeff{TOKEN}\u200b',
                      f'TELEGRAM_BOT_TOKEN="{TOKEN}"'):
            with self.subTest(value_type='synthetic token'):
                self.assertEqual(setup_local.normalize_bot_token(value), TOKEN)

    def test_format_does_not_assume_a_fixed_credential_length(self):
        self.assertEqual(setup_local.normalize_bot_token('123:abc'), '123:abc')

    def test_paste_control_character_has_actionable_message(self):
        for value in ('\x16', '\x16' + TOKEN, TOKEN + '\x1b'):
            with self.assertRaisesRegex(ValueError, 'caracteres de controle') as error:
                setup_local.normalize_bot_token(value)
            self.assertNotIn(TOKEN, str(error.exception))

    def test_empty_token(self):
        with self.assertRaisesRegex(ValueError, 'Nenhum token foi recebido'):
            setup_local.normalize_bot_token(' \n ')

    def test_other_credentials_and_unsafe_paths_are_rejected(self):
        for value in (USER_ID, '@meu_bot', 'abcdef0123456789',
                      'Token: ' + TOKEN, TOKEN + '/getMe', TOKEN + '?a=b',
                      TOKEN + ' outra palavra', '123:' + 'a' * 513):
            with self.assertRaises(ValueError) as error:
                setup_local.normalize_bot_token(value)
            self.assertNotIn(TOKEN, str(error.exception))


class TelegramSetupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / 'telegram.local.env'
        self.previous = 'TELEGRAM_BOT_TOKEN=previous\nTELEGRAM_ALLOWED_USERS=99\n'
        self.path.write_text(self.previous, encoding='utf-8')
        self.root_patch = patch.object(setup_local, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def configure(self, credentials=(TOKEN, USER_ID), response=None, error=None):
        payload = response if response is not None else {
            'ok': True, 'result': {'is_bot': True, 'username': 'teste_ficticio_bot'}}
        with patch.object(setup_local, 'read_telegram_credentials', return_value=credentials), \
                patch.object(setup_local, 'urlopen', side_effect=error) as request, \
                redirect_stdout(io.StringIO()) as output:
            request.return_value.__enter__.return_value = io.StringIO(json.dumps(payload))
            setup_local.configure_telegram()
        return request, output.getvalue()

    def assert_preserved(self):
        self.assertEqual(self.path.read_text(encoding='utf-8'), self.previous)

    def test_validated_credentials_saved_without_printing_token(self):
        request, output = self.configure(credentials=(f'`{TOKEN}`', f' {USER_ID} '))
        request.assert_called_once_with(f'https://api.telegram.org/bot{TOKEN}/getMe', timeout=15)
        self.assertEqual(dotenv_values(self.path)['TELEGRAM_BOT_TOKEN'], TOKEN)
        self.assertEqual(dotenv_values(self.path)['TELEGRAM_ALLOWED_USERS'], USER_ID)
        self.assertIn('Bot validado: @teste_ficticio_bot', output)
        self.assertNotIn(TOKEN, output)

    def test_cancel_does_not_query_or_replace_configuration(self):
        request, output = self.configure(credentials=None)
        request.assert_not_called()
        self.assertIn('cancelado', output)
        self.assert_preserved()

    def test_bad_token_and_bad_user_id_do_not_query_or_save(self):
        with patch.object(setup_local, 'urlopen') as request:
            for credentials in (('\x16', USER_ID), (TOKEN, '@usuario')):
                with patch.object(setup_local, 'read_telegram_credentials', return_value=credentials):
                    with self.assertRaises(SystemExit):
                        setup_local.configure_telegram()
            request.assert_not_called()
        self.assert_preserved()

    def test_rejected_token_never_prints_secret_url_or_overwrites_file(self):
        for status in (401, 404):
            error = HTTPError(f'https://api.telegram.org/bot{TOKEN}/getMe', status, TOKEN, {}, None)
            with self.assertRaisesRegex(SystemExit, 'Telegram recusou') as caught:
                self.configure(error=error)
            self.assertNotIn(TOKEN, str(caught.exception))
            self.assert_preserved()

    def test_outage_does_not_claim_token_is_invalid(self):
        error = HTTPError(f'https://api.telegram.org/bot{TOKEN}/getMe', 429, TOKEN, {}, None)
        with self.assertRaisesRegex(SystemExit, 'limitou a consulta') as caught:
            self.configure(error=error)
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assert_preserved()

    def test_connection_failure_is_separate_and_private(self):
        with self.assertRaisesRegex(SystemExit, 'conexao segura') as caught:
            self.configure(error=URLError('request failed for ' + TOKEN))
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assert_preserved()

    def test_invalid_response_does_not_replace_configuration(self):
        for payload in ([], {'ok': False}, {'ok': True, 'result': {}},
                        {'ok': True, 'result': {'is_bot': True}}):
            with self.assertRaisesRegex(SystemExit, 'nao confirmou'):
                self.configure(response=payload)
            self.assert_preserved()

    def test_windows_default_uses_window_not_getpass(self):
        with patch.object(setup_local.os, 'name', 'nt'), \
                patch.object(setup_local, 'read_telegram_window', return_value=(TOKEN, USER_ID)) as window, \
                patch.object(setup_local.getpass, 'getpass') as terminal, redirect_stdout(io.StringIO()):
            self.assertEqual(setup_local.read_telegram_credentials(), (TOKEN, USER_ID))
        window.assert_called_once_with()
        terminal.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec('tkinter'), 'Tkinter unavailable')
    def test_window_masks_token_and_releases_resources(self):
        with patch('tkinter.Tk') as root, \
                patch('tkinter.simpledialog.askstring', side_effect=[TOKEN, USER_ID]) as ask:
            self.assertEqual(setup_local.read_telegram_window(), (TOKEN, USER_ID))
        self.assertEqual(ask.call_args_list[0].kwargs['show'], '*')
        root.return_value.destroy.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
