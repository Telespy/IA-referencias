import copy
import importlib.util
import json
import sys
from types import ModuleType
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from api.index import app, _rate_limits, split_references
from main import process_reference_line
from parsers import parse_raw_citation_text
from sources import LookupFailure, _crossref_metadata, fetch_google_books, fetch_by_url, _get
from reference_validation import verify_work_identity

RAW = ('HOLANDA, M. A. et al. Elmo-CPAP 1.0: a helmet interface for CPAP and high-flow oxygen delivery. '
       'Jornal Brasileiro de Pneumologia, v. 47, n. 3, e20200590, 2021. '
       'DOI: https://doi.org/10.1590/S1807-59322021000000001. Acesso em: 22 ago. 2026.')
ARTICLE = {
    'item_type': 'journalArticle',
    'title': 'ELMO 1.0: a helmet interface for CPAP and high-flow oxygen delivery',
    'authors': [{'family': 'Holanda', 'given': 'Marcelo Alcantara'}],
    'journal': 'Jornal Brasileiro de Pneumologia', 'year': '2021',
    'doi': '10.36416/1806-3756/e20200590', 'page': 'e20200590',
    '_source': {'name': 'Crossref', 'url': 'https://api.crossref.org/works/example', 'retrieved_at': '2026-09-27T00:00:00Z'},
}


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        # Source fixtures must never invoke the live supplemental services.
        patcher = patch('main.enrich_article', side_effect=lambda meta: meta)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_author_particle_and_compact_pages_do_not_destroy_article(self):
        raw = ('CANEN, Ana; OLIVEIRA, Angela M. A. de. Multiculturalismo e curriculo em acao: um estudo de caso. '
               'Rev. Bras. Educ. [online]. 2002, n.21, pp.61-74. ISSN 1413-2478.')
        meta = parse_raw_citation_text(raw)
        self.assertEqual(meta['authors'][1]['given'], 'Angela M. A. de')
        self.assertTrue(meta['title'].startswith('Multiculturalismo'))
        self.assertEqual(meta['journal'], 'Rev. Bras. Educ')
        self.assertEqual(meta['page'], '61-74')
        self.assertEqual(meta['year'], '2002')

    def test_placeholder_url_is_reported_without_corrupting_thesis(self):
        raw = ('CARNEIRO, Aparecida Sueli. A construcao do outro. 2005. '
               'Tese (Doutorado) - Universidade de Sao Paulo, Sao Paulo, 2005. '
               'Disponivel em: xxxx. Acesso em: 11 set. 2026.')
        result = process_reference_line(raw, online=False)
        self.assertEqual(result['meta']['year'], '2005')
        self.assertEqual(result['meta']['city'], 'Sao Paulo')
        self.assertFalse(result['meta'].get('url'))
        self.assertIn('INVALID_URL', [i['code'] for i in result['issues']])
        self.assertFalse(result['approved'])

    def test_markdown_document_url_is_not_flagged_as_invalid(self):
        result = process_reference_line(RAW + ' Disponivel em: [PDF](https://example.org/obra.pdf).', online=False)
        self.assertNotIn('INVALID_URL', [i['code'] for i in result['issues']])

    def test_compound_family_name_is_preserved(self):
        from parsers import parse_authors
        self.assertEqual(parse_authors('SILVA JUNIOR, Jose')[0]['family'], 'SILVA JUNIOR')

    def test_monograph_does_not_invent_specialization_degree(self):
        result = process_reference_line('SILVA, Maria. Pesquisa. 2020. Monografia - Universidade Exemplo, Recife, 2020.', online=False)
        self.assertNotIn('Especializa', result['meta'].get('degree_type', ''))

    def test_initials_et_al_and_elocation(self):
        meta = parse_raw_citation_text(RAW)
        self.assertEqual(meta['authors'][0]['family'], 'HOLANDA')
        self.assertEqual(meta['authors'][0]['given'], 'M. A.')
        self.assertTrue(meta['authors'][0]['et_al'])
        self.assertTrue(meta['title'].startswith('Elmo-CPAP 1.0:'))
        self.assertEqual(meta['journal'], ARTICLE['journal'])
        self.assertEqual(meta['page'], 'e20200590')

    def test_markdown_link_does_not_override_document_url(self):
        raw = RAW + ' Disponivel em: [PDF](https://example.org/a_1.pdf).'
        self.assertEqual(parse_raw_citation_text(raw)['url'], 'https://example.org/a_1.pdf')

    @patch('main.fetch_crossref_search', return_value=[ARTICLE])
    @patch('main.fetch_crossref_doi', return_value={})
    def test_wrong_doi_recovered_by_identity_not_certified(self, *_):
        result = process_reference_line(RAW)
        self.assertEqual(result['meta']['doi'], ARTICLE['doi'])
        self.assertEqual(result['meta']['title'], ARTICLE['title'])
        self.assertTrue(result['identity_verified'])
        self.assertFalse(result['approved'])
        self.assertIn('volume', result['unverified_fields'])
        self.assertEqual(result['provenance']['title']['source'], 'Crossref')
        self.assertTrue(any(c['field'] == 'doi' for c in result['corrections']))
        self.assertNotIn('*et al.*.', result['abnt'])
        self.assertIn('ELMO', result['abnt'])

    def test_unrelated_doi_metadata_is_rejected(self):
        unrelated = dict(ARTICLE, title='An unrelated clinical trial', authors=[{'family': 'Smith'}])
        with patch('main.fetch_crossref_doi', return_value=unrelated), patch('main.fetch_crossref_search', return_value=[]):
            result = process_reference_line(RAW)
        self.assertFalse(result['identity_verified'])
        self.assertNotIn('Smith', result['abnt'])
        self.assertIn('DOI_CONFLICT', [i['code'] for i in result['issues']])

    def test_ambiguous_matches_are_not_selected(self):
        duplicate = dict(ARTICLE, doi='10.1234/duplicate')
        with patch('main.fetch_crossref_doi', return_value={}), patch('main.fetch_crossref_search', return_value=[ARTICLE, duplicate]):
            result = process_reference_line(RAW)
        self.assertFalse(result['identity_verified'])
        self.assertIn('AMBIGUOUS_MATCH', [i['code'] for i in result['issues']])

    def test_wrong_year_or_author_rejected(self):
        user = parse_raw_citation_text(RAW)
        self.assertFalse(verify_work_identity(user, dict(ARTICLE, year='2020')))
        self.assertFalse(verify_work_identity(user, dict(ARTICLE, authors=[{'family': 'Silva'}])))
        self.assertFalse(verify_work_identity(user, dict(ARTICLE, title=ARTICLE['title'].replace('1.0', '2.0'))))

    def test_bare_bad_doi_has_no_title_search(self):
        with patch('main.fetch_crossref_doi', return_value={}), patch('main.fetch_crossref_search') as search:
            result = process_reference_line('10.1234/not-found')
        search.assert_not_called()
        self.assertFalse(result['approved'])

    def test_source_failure_is_visible(self):
        with patch('main.fetch_crossref_doi', side_effect=LookupFailure('TLS falhou')):
            result = process_reference_line('10.1234/a')
        self.assertIn('SOURCE_UNAVAILABLE', [i['code'] for i in result['issues']])
        self.assertFalse(result['approved'])

    def test_offline_mode_never_calls_sources(self):
        with patch('main.fetch_crossref_doi') as doi, patch('main.fetch_crossref_search') as search:
            result = process_reference_line(RAW, online=False)
        doi.assert_not_called()
        search.assert_not_called()
        self.assertFalse(result['identity_verified'])

    def test_book_is_not_enriched_from_a_title_table(self):
        result = process_reference_line('BAUMAN, Zygmunt. Modernidade liquida.', online=False)
        self.assertFalse(result['meta'].get('year'))
        self.assertFalse(result['meta'].get('publisher'))
        self.assertFalse(result['meta'].get('access_date'))

    def test_legislation_never_invents_ementa_publisher_or_url(self):
        raw = 'BRASIL. Lei nº 11.892, de 29 de dezembro de 2008.'
        result = process_reference_line(raw, online=False)
        self.assertFalse(result['meta'].get('ementa'))
        self.assertFalse(result['meta'].get('url'))
        self.assertFalse(result['meta'].get('publisher'))
        self.assertEqual(result['meta']['year'], '2008')
        self.assertIn('LEGAL_REVIEW', [i['code'] for i in result['issues']])

    def test_future_access_date_is_reported(self):
        result = process_reference_line(RAW.replace('2026.', '2099.'), online=False)
        self.assertIn('FUTURE_ACCESS_DATE', [i['code'] for i in result['issues']])

    def test_unsupported_document_preserves_original(self):
        raw = 'AUTOR. Podcast sobre referencias. 2023.'
        result = process_reference_line(raw, online=False)
        self.assertEqual(result['abnt'], raw)
        self.assertEqual(result['item_type'], 'unknown')

    def test_only_complete_evidence_can_be_approved(self):
        source = dict(ARTICLE, volume='47', issue='3', city='Sao Paulo', start_month=5)
        with patch('main.fetch_crossref_doi', return_value=source):
            result = process_reference_line(RAW)
        self.assertTrue(result['approved'])
        self.assertEqual(result['status'], 'verified')

    def test_bad_source_authorship_preserves_supplied_authors(self):
        source = dict(ARTICLE, _warnings=['Marcadores de afiliacao removidos.'])
        with patch('main.fetch_crossref_doi', return_value=source):
            result = process_reference_line(RAW)
        self.assertEqual(result['meta']['authors'][0]['given'], 'M. A.')
        self.assertFalse(result['provenance']['authors']['verified'])

    def test_crossref_day_is_not_end_month(self):
        item = {'title': ['Example'], 'type': 'journal-article', 'DOI': '10.1/example',
                'published-print': {'date-parts': [[2021, 3, 5]]}, 'article-number': 'e12345',
                'author': [{'family': 'Holanda1,2', 'given': 'Marcelo'}]}
        result = _crossref_metadata(item)
        self.assertNotIn('end_month', result)
        self.assertEqual(result['page'], 'e12345')
        self.assertEqual(result['authors'][0]['family'], 'Holanda')
        self.assertTrue(result['_warnings'])

    def test_arbitrary_url_is_not_fetched(self):
        with patch('sources._get') as request:
            self.assertEqual(fetch_by_url('http://169.254.169.254/latest/meta-data'), {})
        request.assert_not_called()

    def test_google_books_rejects_different_isbn(self):
        wrong = {'items': [{'volumeInfo': {'title': 'Wrong edition', 'industryIdentifiers': [{'identifier': '9780000000000'}]}}]}
        with patch('sources._json', side_effect=[wrong, {}, {}]):
            self.assertEqual(fetch_google_books('9788535208030'), {})

    def test_book_edition_fallback_checks_equivalent_isbn_and_author(self):
        edition = {'title': '1984', 'isbn_10': ['0451524934'], 'publish_date': '1984',
                   'authors': [{'key': '/authors/OL118077A'}], 'publishers': ['Signet Classic']}
        with patch('sources._json', side_effect=[LookupFailure('limite'), {}, edition, {'name': 'George Orwell'}]):
            book = fetch_google_books('9780451524935')
        self.assertEqual(book['isbn'], '9780451524935')
        self.assertEqual(book['title'], '1984')
        self.assertEqual(book['authors'][0]['family'], 'Orwell')
        self.assertEqual(book['_source']['name'], 'Open Library')

    def test_book_edition_fallback_rejects_other_edition(self):
        edition = {'title': 'Other edition', 'isbn_13': ['9788535208030']}
        with patch('sources._json', side_effect=[{}, {}, edition]) as request:
            self.assertEqual(fetch_google_books('9780451524935'), {})
        self.assertEqual(request.call_count, 3)

    def test_catalog_redirect_is_limited_to_https_edition_on_same_host(self):
        for location in ('https://evil.example/books/OL1M.json', 'http://127.0.0.1/books/OL1M.json',
                         'https://openlibrary.org.evil.example/books/OL1M.json',
                         'https://openlibrary.org/search.json'):
            response = Mock(status_code=302, headers={'Location': location})
            with patch('sources.requests.get', return_value=response) as request:
                with self.assertRaises(LookupFailure):
                    _get('https://openlibrary.org/isbn/9780451524935.json')
            request.assert_called_once()
        redirect = Mock(status_code=302, headers={'Location': '/books/OL1M.json'})
        record = Mock(status_code=200, content=b'{}')
        with patch('sources.requests.get', side_effect=[redirect, record]) as request:
            self.assertIs(_get('https://openlibrary.org/isbn/9780451524935.json'), record)
        self.assertEqual(request.call_args.args[0], 'https://openlibrary.org/books/OL1M.json')


class ApiTests(unittest.TestCase):
    def setUp(self):
        _rate_limits.clear()
        self.client = TestClient(app)

    def test_json_report_keeps_warnings_provenance_and_order(self):
        response = self.client.post('/api/format', json={'text': 'SILVA, Maria. Livro. Recife: Teste, 2020.\nSOUZA, Jose. Outro. Natal: Teste, 2021.', 'online': False})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['total'], 2)
        self.assertTrue(data['results'][0]['raw'].startswith('SILVA'))
        self.assertTrue(data['results'][0]['provenance'])
        self.assertTrue(data['results'][0]['issues'])
        self.assertIn('REVISAO NECESSARIA', data['abnt_full'])
        self.assertIn('Content-Security-Policy', response.headers)

    def test_long_reference_is_rejected_not_truncated(self):
        self.assertEqual(self.client.post('/api/format', json={'text': 'a' * 4001}).status_code, 400)

    def test_batch_limit(self):
        self.assertEqual(self.client.post('/api/format', json={'text': '\n'.join(['a'] * 51)}).status_code, 400)

    def test_blank_and_oversize_input(self):
        self.assertEqual(self.client.post('/api/format', json={'text': ' \n '}).status_code, 400)
        self.assertEqual(self.client.post('/api/format', content=b'a' * (512 * 1024 + 1)).status_code, 413)

    def test_one_exception_does_not_lose_other_references(self):
        good = process_reference_line('SILVA, Maria. Livro. Natal: Teste, 2020.', online=False)
        with patch('api.index.process_reference_line', side_effect=[RuntimeError('SECRET'), good]):
            response = self.client.post('/api/format', json={'text': 'um\ndois'})
        data = response.json()
        self.assertEqual(data['total'], 2)
        self.assertEqual(data['summary']['error'], 1)
        self.assertNotIn('SECRET', response.text)

    def test_wrapped_blocks(self):
        self.assertEqual(split_references('AUTOR. Titulo.\nEditora, 2020.\n\nOUTRO. Livro.', 'blocks'),
                         ['AUTOR. Titulo. Editora, 2020.', 'OUTRO. Livro.'])

    def test_blank_lines_do_not_merge_separate_references(self):
        self.assertEqual(split_references('um\n\ndois\ntres'), ['um', 'dois', 'tres'])


class HermesPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parent / 'integrations/hermes/brain-format/__init__.py'
        spec = importlib.util.spec_from_file_location('brain_format_plugin_test', path)
        cls.plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.plugin)

    def test_slash_response_preserves_api_report_exactly(self):
        report = '1. [REVISAO NECESSARIA]\nReferencia.\nAviso: DOI nao verificado.'
        data = {'total': 1, 'summary': {'needs_review': 1}, 'abnt_full': report}
        with patch.object(self.plugin, 'request_correction', return_value=data) as request:
            output = self.plugin.reference_command('lista original')
        request.assert_called_once_with('lista original')
        self.assertTrue(output.endswith(report))

    def test_failure_does_not_fabricate_reference(self):
        with patch.object(self.plugin, 'request_correction', return_value={'error': 'API indisponivel'}):
            self.assertEqual(self.plugin.reference_command('algo'), 'API indisponivel')

    def test_help_does_not_call_api(self):
        with patch.object(self.plugin, 'request_correction') as request:
            self.assertIn('/referencias', self.plugin.reference_command(' '))
        request.assert_not_called()

    def test_progress_notice_uses_origin_chat_and_topic_only(self):
        context = ModuleType('gateway.session_context')
        sender = ModuleType('tools.send_message_tool')
        context.session_context_engaged = lambda: True
        values = {'HERMES_SESSION_PLATFORM': 'telegram', 'HERMES_SESSION_CHAT_ID': '123456',
                  'HERMES_SESSION_THREAD_ID': '7'}
        context.get_session_env = lambda key: values.get(key, '')
        sender.send_message_tool = Mock(return_value='{"success":true}')
        with patch.dict(sys.modules, {'gateway.session_context': context, 'tools.send_message_tool': sender}):
            self.plugin.notify_processing()
            self.assertEqual(sender.send_message_tool.call_args.args[0]['target'], 'telegram:123456:7')
            sender.send_message_tool.reset_mock()
            values['HERMES_SESSION_PLATFORM'] = 'api_server'
            self.plugin.notify_processing()
            sender.send_message_tool.assert_not_called()
            values['HERMES_SESSION_PLATFORM'] = 'telegram'
            values['HERMES_SESSION_CHAT_ID'] = ''
            self.plugin.notify_processing()
            sender.send_message_tool.assert_not_called()

    def test_notice_failure_does_not_discard_report(self):
        context = ModuleType('gateway.session_context')
        context.session_context_engaged = Mock(side_effect=RuntimeError('private exception'))
        context.get_session_env = Mock()
        data = {'total': 1, 'summary': {}, 'abnt_full': 'Referencia. Aviso: pendente.'}
        with patch.dict(sys.modules, {'gateway.session_context': context}), \
                patch.object(self.plugin, 'request_correction', return_value=data), \
                self.assertLogs(self.plugin.logger, level='WARNING') as logs:
            result = self.plugin.reference_command('referencia original')
        self.assertTrue(result.endswith(data['abnt_full']))
        self.assertNotIn('private exception', '\n'.join(logs.output))

    def test_tool_summary_does_not_trigger_hermes_error_heuristic(self):
        for failures in (0, 1):
            data = {'success': True, 'total': 2, 'abnt_full': 'Relatorio com avisos.',
                    'summary': {'verified': 0, 'needs_review': 2 - failures, 'error': failures}}
            with patch.object(self.plugin, 'request_correction', return_value=data):
                output = self.plugin.correction_tool({'text': 'lista'})
            self.assertNotIn('"error"', output[:500].lower())
            self.assertEqual(json.loads(output)['summary']['processing_failures'], failures)
            self.assertEqual(json.loads(output)['abnt_full'], data['abnt_full'])


if __name__ == '__main__':
    unittest.main()
