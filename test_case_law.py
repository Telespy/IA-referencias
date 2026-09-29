import unittest
from unittest.mock import patch

from case_law import parse_case_request, fetch_stf_case
from correction import correct_reference, reference_report
from formatters import format_case_citation


def correct(raw, fetched=None, online=True):
    return correct_reference(raw, online=online, fetch_doi=lambda _: {}, fetch_book=lambda _: {},
                             search=lambda _: [], fetch_url=lambda _: {},
                             fetch_case=lambda _: fetched or {})


class CaseLawTests(unittest.TestCase):
    def test_parse_adi_and_supplied_page(self):
        parsed = parse_case_request('BRASIL. Supremo Tribunal Federal. Ação Direta de Inconstitucionalidade 4.449/AL, p. 1')
        self.assertEqual(parsed['case_number'], '4449')
        self.assertEqual(parsed['case_state'], 'AL')
        self.assertEqual(parsed['case_page'], '1')

    def test_parse_re(self):
        parsed = parse_case_request('STF RE 663696/MG')
        self.assertEqual(parsed['case_class'], 'RE')
        self.assertEqual(parsed['case_number'], '663696')
        self.assertEqual(parsed['case_state'], 'MG')

    def test_re_without_source_is_not_a_fabricated_reference(self):
        result = correct('STF RE 663696/MG')
        self.assertEqual(result['abnt'], 'STF RE 663696/MG')
        self.assertEqual(result['citation'], '')

    def test_unverified_does_not_invent_ementa(self):
        result = correct('STF ADI 4449/AL')
        self.assertEqual(result['status'], 'needs_review')
        self.assertNotIn('Rel. Min.', result['citation'])
        self.assertIn('Ementa do acórdão', result['missing_fields'])

    def test_offline_does_not_claim_verified(self):
        result = correct('STF ADI 4449/AL', online=False)
        self.assertFalse(result['approved'])

    def test_citation_order_and_separate_reference(self):
        meta = {'item_type': 'caseLaw', 'case_class': 'ADI', 'case_number': '4449',
                'relator': 'Marco Aurélio', 'court_body': 'Tribunal Pleno',
                'judgment_date': '28/03/2019', 'publication_date': '01/08/2019'}
        result = correct('STF ADI 4449/AL', meta)
        self.assertEqual(format_case_citation(meta),
                         '(STF, ADI 4.449, Rel. Min. Marco Aurélio, Tribunal Pleno, j. 28/03/2019, DJe 01/08/2019)')
        report = reference_report(result)
        self.assertIn('Citação: (STF, ADI 4.449', report)
        self.assertIn('Referência: ', report)

    def test_source_mismatch_is_rejected(self):
        html = b'<html>ADI 4449 Relator(a): MIN. MARCO AURELIO</html>'
        docket = b'<div></div>'
        with patch('case_law._stf_get', side_effect=[(html, 'https://portal.stf.jus.br/processos/detalhe.asp?incidente=3934977'),
                                                    (docket, 'https://portal.stf.jus.br/processos/abaAndamentos.asp')]):
            self.assertEqual(fetch_stf_case({'case_class': 'ADI', 'case_number': '4449', 'case_state': 'SP'}), {})


if __name__ == '__main__':
    unittest.main()
