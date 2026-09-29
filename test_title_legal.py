import copy
import unittest
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.index import app, _rate_limits
from correction import reference_report
from legal_references import parse_legal_request, fetch_legal_reference
from main import process_reference_line
from parsers import parse_raw_citation_text
from sources import LookupFailure
from title_lookup import select_title, search_book_titles, fetch_title_candidates

TITLE = 'ELMO 1.0: a helmet interface for CPAP and high-flow oxygen delivery'
VENTILATION = 'Mechanical Ventilation to Minimize Progression of Lung Injury in Acute Respiratory Failure'
ARTICLE = {'item_type': 'journalArticle', 'title': TITLE, 'authors': [{'family': 'Holanda'}],
           'year': '2021', 'doi': '10.36416/1806-3756/e20200590', 'volume': '47', 'issue': '3',
           'page': 'e20200590', 'city': 'Fortaleza', 'journal': 'Jornal Brasileiro de Pneumologia',
           'start_month': 5, '_source': {'name': 'Fixture', 'url': 'https://example.org', 'retrieved_at': '2026-09-28'}}
LAW = {'DetalheDocumento': {'documentos': {'documento': [{
    'identificacao': {'tipo': 'LEI-n', 'numero': '11892', 'dataassinatura': '29/12/2008',
                     'urlDocumento': 'https://normas.leg.br/?urn=urn:lex:br:federal:lei:2008-12-29;11892'},
    'ementa': 'Institui a Rede Federal de Educacao Profissional, Cientifica e Tecnologica.',
    'publicacoes': {'publicacao': [{'tipo': 'PUB', 'fonte': 'Diario Oficial da Uniao  de 30/12/2008',
                                  'siglaFonte': 'DOU-2008-12-30', 'data': '30/12/2008', 'pagina': '1'}]},
}]}}}
CAMARA_LIST = {'dados': [{'id': 2256735, 'siglaTipo': 'PL', 'numero': 2630, 'ano': 2020}]}
CAMARA_DETAIL = {'dados': {**CAMARA_LIST['dados'][0], 'ementa': 'Institui regras para a Internet.',
                          'dataApresentacao': '2020-07-03T16:28',
                          'statusProposicao': {'descricaoSituacao': 'Pronta para Pauta', 'dataHora': '2024-04-24'}}}
SENADO = [{'identificacao': 'PL 2338/2023', 'codigoMateria': 157233, 'id': 8441243,
           'ementa': 'Dispoe sobre o uso da Inteligencia Artificial.', 'dataApresentacao': '2023-05-03',
           'situacaoAtual': 'REMETIDA A CAMARA DOS DEPUTADOS', 'dataSituacaoAtual': '2025-03-17'}]


class TitleTests(unittest.TestCase):
    def setUp(self):
        patcher = patch('main.enrich_article', side_effect=lambda meta: meta)
        patcher.start()
        self.addCleanup(patcher.stop)
        doi_patcher = patch('main.fetch_crossref_doi', return_value=ARTICLE)
        doi_patcher.start()
        self.addCleanup(doi_patcher.stop)

    def correct(self, text, candidates, issues=None):
        with patch('main.fetch_title_candidates', return_value={'candidates': candidates, 'issues': issues or []}):
            return process_reference_line(text)

    def test_bare_and_explicit_title_do_not_invent_author_from_decimal(self):
        for raw in (TITLE, 'Titulo: ' + TITLE):
            result = self.correct(raw, [ARTICLE])
            self.assertEqual(result['meta']['doi'], ARTICLE['doi'])
            self.assertTrue(result['approved'])
            self.assertEqual(result['meta']['authors'], ARTICLE['authors'])

    def test_duplicate_title_with_distinct_doi_is_not_selected(self):
        result = self.correct(TITLE, [ARTICLE, dict(ARTICLE, doi='10.1234/other')])
        self.assertFalse(result['identity_verified'])
        self.assertEqual(len(result['candidates']), 2)
        self.assertIn('Candidato:', reference_report(result))
        self.assertEqual(result['abnt'], TITLE)

    def test_same_doi_is_deduplicated(self):
        self.assertTrue(self.correct(TITLE, [ARTICLE, ARTICLE])['identity_verified'])

    def test_search_sources_deduplicated_despite_retrieval_timestamp(self):
        other = dict(ARTICLE, doi='10.1234/other', _source=dict(ARTICLE['_source'], retrieved_at='later'))
        result = self.correct(TITLE, [ARTICLE, other])
        self.assertEqual(len(result['sources']), 1)

    def test_numeric_title_difference_is_not_accepted(self):
        result = self.correct(TITLE, [dict(ARTICLE, title=TITLE.replace('1.0', '2.0'))])
        self.assertFalse(result['identity_verified'])

    def test_short_generic_article_requires_identifier(self):
        result = self.correct('Titulo: Educacao', [dict(ARTICLE, title='Educacao')])
        self.assertFalse(result['identity_verified'])

    def test_no_matching_title_preserves_input(self):
        result = self.correct(TITLE, [dict(ARTICLE, title='An unrelated clinical trial')])
        self.assertFalse(result['approved'])
        self.assertFalse(result['candidates'])

    def test_selected_title_rechecks_doi_and_uses_canonical_record(self):
        candidate = dict(ARTICLE, title=VENTILATION, authors=[{'family': 'Wrong'}],
                         doi='10.1164/rccm.201605-1081cp')
        canonical = dict(candidate, authors=[{'family': 'Brochard', 'given': 'Laurent'}],
                         volume='195', issue='4', page='438-442', journal='American Journal of Respiratory and Critical Care Medicine')
        with patch('main.fetch_crossref_doi', return_value=canonical) as doi_fetch:
            result = self.correct(VENTILATION, [candidate])
        doi_fetch.assert_called_once_with(candidate['doi'])
        self.assertEqual(result['meta']['authors'], canonical['authors'])
        self.assertIn('v. 195, n. 4, p. 438-442', result['abnt'])

    def test_title_doi_mismatch_stays_unverified(self):
        with patch('main.fetch_crossref_doi', return_value=dict(ARTICLE, title='Different paper')):
            result = self.correct(TITLE, [ARTICLE])
        self.assertFalse(result['identity_verified'])
        self.assertIn('TITLE_DOI_UNVERIFIED', [i['code'] for i in result['issues']])

    def test_book_work_does_not_invent_edition(self):
        book = {'item_type': 'book', 'title': 'Dom Casmurro', 'authors': [{'family': 'Assis', 'given': 'Machado de'}],
                'catalog_url': 'https://openlibrary.org/works/OL1W', '_work_only': True}
        result = self.correct('Dom Casmurro', [book])
        self.assertEqual(result['item_type'], 'book')
        self.assertFalse(result['approved'])
        self.assertFalse(result['meta'].get('year'))
        self.assertFalse(result['meta'].get('publisher'))
        self.assertIn('BOOK_EDITION_REQUIRED', [i['code'] for i in result['issues']])

    def test_distinct_book_editions_are_not_collapsed(self):
        books = [dict(ARTICLE, item_type='book', doi='', title='A book title', isbn=i) for i in ('9780451524935', '9780141036144')]
        match, candidates = select_title('A book title', books)
        self.assertFalse(match)
        self.assertEqual(len(candidates), 2)

    def test_single_catalog_edition_is_not_selected_from_title_alone(self):
        result = self.correct('Titulo: A book title', [dict(ARTICLE, item_type='book', title='A book title', publisher='One publisher')])
        self.assertFalse(result['identity_verified'])
        self.assertNotIn('publisher', result['meta'])
        self.assertIn('BOOK_EDITION_REQUIRED', [i['code'] for i in result['issues']])

    def test_unavailable_source_prevents_approval(self):
        result = self.correct(TITLE, [ARTICLE], [{'code': 'SOURCE_UNAVAILABLE', 'message': 'Offline', 'severity': 'warning'}])
        self.assertFalse(result['approved'])

    @patch('title_lookup._json')
    def test_book_search_never_mixes_work_edition_arrays(self, request):
        request.return_value = {'docs': [{'key': '/works/OL1W', 'title': 'Dom Casmurro', 'author_name': ['Machado de Assis'],
                                        'publisher': ['A', 'B'], 'publish_year': [1900, 2000], 'edition_count': 123}]}
        book = search_book_titles('Dom Casmurro')[0]
        self.assertNotIn('year', book)
        self.assertNotIn('publisher', book)
        self.assertEqual(book['edition_count'], 123)

    @patch('title_lookup.search_book_titles', return_value=[])
    @patch('title_lookup.fetch_crossref_search', side_effect=LookupFailure('Unavailable'))
    def test_search_failure_is_not_hidden(self, *_):
        self.assertEqual(fetch_title_candidates(TITLE)['issues'][0]['code'], 'SOURCE_UNAVAILABLE')

    def test_offline_title_performs_no_lookup(self):
        with patch('main.fetch_title_candidates') as fetch:
            result = process_reference_line(TITLE, online=False)
        fetch.assert_not_called()
        self.assertEqual(result['abnt'], TITLE)

    def test_candidates_survive_api_response_model(self):
        _rate_limits.clear()
        with patch('main.fetch_title_candidates', return_value={'candidates': [ARTICLE, dict(ARTICLE, doi='10.1234/other')]}):
            result = TestClient(app).post('/api/format', json={'text': TITLE}).json()
        self.assertEqual(len(result['results'][0]['candidates']), 2)
        self.assertIn('Candidato:', result['abnt_full'])


class LegalTests(unittest.TestCase):
    def law(self, raw='Lei federal 11892/2008', payload=None):
        with patch('legal_references._planalto_law', return_value={}), patch('legal_references._json', return_value=copy.deepcopy(payload or LAW)):
            return process_reference_line(raw)

    def test_planalto_law_reference_uses_presidency_imprint(self):
        from unittest.mock import Mock
        html = ('<html><body>Presidência da República. Casa Civil. '
                'LEI Nº 12.503, DE 11 DE OUTUBRO DE 2011. '
                'Denomina “Rodovia Joaquim Pinto Lapa” o trecho da rodovia BR-408 compreendido entre a cidade de Carpina e o entroncamento com a BR-232, no Estado de Pernambuco. '
                'A PRESIDENTA DA REPÚBLICA Faço saber que o Congresso Nacional decreta. '
                'Brasília, 11 de outubro de 2011; 190º da Independência.</body></html>')
        with patch('correction.correction_today', return_value=date(2026, 9, 29)), patch('legal_references._get', return_value=Mock(content=html.encode('utf-8'))) as request:
            result = process_reference_line('Lei federal 12503/2011')
        self.assertEqual(request.call_args.args[0], 'https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12503.htm')
        self.assertIn('Mozilla/5.0', request.call_args.kwargs['headers']['User-Agent'])
        self.assertTrue(result['approved'], result)
        self.assertEqual(result['abnt'],
            'BRASIL. **Lei nº 12.503, de 11 de outubro de 2011**. Denomina “Rodovia Joaquim Pinto Lapa” o trecho da rodovia BR-408 compreendido entre a cidade de Carpina e o entroncamento com a BR-232, no Estado de Pernambuco. Brasília, DF: Presidência da República, 2011. Disponível em: [https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12503.htm](https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12503.htm). Acesso em: 29 set. 2026.')

    def test_planalto_identity_mismatch_falls_back_to_senado(self):
        from unittest.mock import Mock
        wrong = '<html>Presidência da República LEI Nº 12.504, DE 11 DE OUTUBRO DE 2011. Outro assunto. A PRESIDENTA DA REPÚBLICA Brasília, 11 de outubro de 2011</html>'
        with patch('legal_references._get', return_value=Mock(content=wrong.encode('utf-8'))), patch('legal_references._json', return_value=LAW):
            result = process_reference_line('Lei federal 12503/2011')
        self.assertFalse(result['identity_verified'])

    def test_number_year_and_full_date_parsed(self):
        for raw in ('Lei federal 11892/2008', 'BRASIL. Lei n\u00ba 11.892, de 29 de dezembro de 2008.'):
            parsed = parse_raw_citation_text(raw)
            self.assertEqual(parsed['item_type'], 'legislation')
            self.assertEqual(parsed['legal_number'], '11892')
            self.assertEqual(parsed['year'], '2008')

    def test_short_bill_is_not_a_book(self):
        self.assertEqual(parse_raw_citation_text('PL 2630/2020')['item_type'], 'bill')

    def test_law_matches_official_identity_and_distinguishes_dates(self):
        result = self.law()
        self.assertTrue(result['identity_verified'])
        self.assertFalse(result['approved'])
        self.assertIn('LEGAL_PUBLICATION_DETAILS', [i['code'] for i in result['issues']])
        self.assertIn('29 de dezembro de 2008', result['abnt'])
        self.assertIn('30 dez. 2008', result['abnt'])
        self.assertIn('**Diario Oficial da Uniao**', result['abnt'])
        self.assertTrue(result['provenance']['city']['derived'])
        self.assertNotIn('secao', result['meta'])

    def test_supplied_wrong_ementa_is_corrected_and_logged(self):
        result = self.law('BRASIL. Lei n\u00ba 11.892, de 29 de dezembro de 2008. Uma ementa incorreta.')
        self.assertEqual(result['meta']['ementa'], LAW['DetalheDocumento']['documentos']['documento'][0]['ementa'])
        self.assertTrue(any(c['field'] == 'ementa' for c in result['corrections']))

    def test_unsupported_jurisdiction_never_calls_federal_api(self):
        for raw in ('Lei municipal 11892/2008', 'SAO PAULO. Lei 11892/2008', 'Lei estadual 11892/2008',
                    'Camara Legislativa do Distrito Federal. PL 2338/2023', 'Camara Municipal de Natal. PL 2630/2020'):
            with patch('legal_references._json') as request:
                result = process_reference_line(raw)
            request.assert_not_called()
            self.assertFalse(result['identity_verified'])

    def test_missing_scope_does_not_assume_federal(self):
        with patch('legal_references._json') as request:
            result = process_reference_line('Lei 11892/2008')
        request.assert_not_called()
        self.assertNotIn('BRASIL.', result['abnt'])
        self.assertIn('LEGAL_JURISDICTION_REQUIRED', [i['code'] for i in result['issues']])

    def test_missing_year_does_not_fetch_unbounded_search(self):
        with patch('legal_references._json') as request:
            result = process_reference_line('Lei federal 11892')
        request.assert_not_called()
        self.assertIn('LEGAL_IDENTIFIER_REQUIRED', [i['code'] for i in result['issues']])

    def test_missing_house_is_actionable(self):
        with patch('legal_references._json') as request:
            result = process_reference_line('PL 2630/2020')
        request.assert_not_called()
        self.assertIn('LEGISLATIVE_HOUSE_REQUIRED', [i['code'] for i in result['issues']])

    def test_wrong_official_number_year_or_type_rejected(self):
        for key, value in (('numero', '11893'), ('tipo', 'DEC'), ('dataassinatura', '29/12/2009')):
            payload = copy.deepcopy(LAW)
            payload['DetalheDocumento']['documentos']['documento'][0]['identificacao'][key] = value
            self.assertFalse(self.law(payload=payload)['identity_verified'])

    def test_multiple_official_records_rejected(self):
        payload = copy.deepcopy(LAW)
        payload['DetalheDocumento']['documentos']['documento'] *= 2
        self.assertFalse(self.law(payload=payload)['identity_verified'])

    def test_user_publisher_cannot_become_verified(self):
        query = parse_legal_request('Lei federal 11892/2008')
        query.update(publisher='Inventada', city='Inventada', section='99')
        with patch('legal_references._json', return_value=LAW):
            meta = fetch_legal_reference(query)['match']
        self.assertNotIn('publisher', meta)
        self.assertNotIn('section', meta)

    def test_historical_law_does_not_get_brasilia(self):
        payload = copy.deepcopy(LAW)
        doc = payload['DetalheDocumento']['documentos']['documento'][0]
        doc['identificacao']['dataassinatura'] = '29/12/1908'
        doc['publicacoes']['publicacao'][0].update(data='30/12/1908', siglaFonte='DOU-1908-12-30')
        result = self.law('Lei federal 11892/1908', payload)
        self.assertFalse(result['meta'].get('city'))
        self.assertFalse(result['approved'])

    def test_offline_never_calls_legal_api(self):
        with patch('main.fetch_legal_reference') as fetch:
            result = process_reference_line('Lei federal 11892/2008', online=False)
        fetch.assert_not_called()
        self.assertFalse(result['approved'])

    def test_law_api_outage_is_not_nonexistence(self):
        with patch('legal_references._json', side_effect=LookupFailure('Unavailable')):
            result = process_reference_line('Lei federal 11892/2008')
        self.assertFalse(result['approved'])
        self.assertIn('SOURCE_UNAVAILABLE', [i['code'] for i in result['issues']])

    def test_untrusted_norm_url_not_returned(self):
        payload = copy.deepcopy(LAW)
        payload['DetalheDocumento']['documentos']['documento'][0]['identificacao']['urlDocumento'] = 'https://127.0.0.1/private'
        result = self.law(payload=payload)
        self.assertFalse(result['meta'].get('url'))
        self.assertFalse(result['approved'])

    def test_camara_bill_keeps_bill_type_and_status(self):
        with patch('legal_references._json', side_effect=[CAMARA_LIST, CAMARA_DETAIL]):
            result = process_reference_line('Camara dos Deputados. PL 2630/2020')
        self.assertEqual(result['item_type'], 'bill')
        self.assertTrue(result['approved'])
        self.assertIn('Projeto de lei n. 2630', result['abnt'])
        self.assertIn('BILL_NOT_LAW', [i['code'] for i in result['issues']])
        self.assertEqual(result['meta']['bill_status'], 'Pronta para Pauta')

    def test_senado_uses_current_process_api(self):
        with patch('legal_references._json', return_value=SENADO) as request:
            result = process_reference_line('Senado Federal. PL 2338/2023')
        self.assertTrue(result['approved'])
        self.assertIn('/processo?', request.call_args.args[0])
        self.assertIn('Senado Federal.', result['abnt'])

    def test_camara_detail_identity_rechecked(self):
        detail = copy.deepcopy(CAMARA_DETAIL)
        detail['dados']['ano'] = 2021
        with patch('legal_references._json', side_effect=[CAMARA_LIST, detail]):
            result = process_reference_line('Camara dos Deputados. PL 2630/2020')
        self.assertFalse(result['identity_verified'])
        self.assertIn('SOURCE_INVALID', [i['code'] for i in result['issues']])

    def test_senado_multiple_processes_not_silently_selected(self):
        with patch('legal_references._json', return_value=SENADO * 2):
            result = process_reference_line('Senado Federal. PL 2338/2023')
        self.assertFalse(result['identity_verified'])


if __name__ == '__main__':
    unittest.main()
