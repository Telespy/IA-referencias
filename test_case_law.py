import unittest
from unittest.mock import patch

from case_law import parse_case_request, fetch_stf_case, _first_pdf_text
from correction import correct_reference, reference_report
from formatters import format_case_citation


def correct(raw, fetched=None, online=True):
    return correct_reference(raw, online=online, fetch_doi=lambda _: {}, fetch_book=lambda _: {},
                             search=lambda _: [], fetch_url=lambda _: {},
                             fetch_case=lambda _: fetched or {})


class CaseLawTests(unittest.TestCase):
    def test_nested_appeal_pdf(self):
        class Page:
            def __init__(self, text):
                self.text = text

            def extract_text(self):
                return self.text

        first = ('Ementa e Acórdão\n03/11/2022 PRIMEIRA TURMA\n'
                 'AG.REG. NOS EMB.DECL. NO AG.REG. NO RECURSO EXTRAORDINÁRIO 1.334.584 RIO DE JANEIRO\n'
                 'RELATOR : MIN. DIAS TOFFOLI\nEMENTA\n'
                 'Agravo regimental em embargos de declaração em agravo regimental. '
                 'A transformação de cargos sem concurso público viola a Constituição.\n'
                 'Documento assinado digitalmente\n')
        second = ('Ementa e Acórdão\nRE 1334584 A GR-ED-AGR / RJ\n'
                  'O recurso não foi provido.\nACÓRDÃO\nVistos, relatados e discutidos.')
        with patch('case_law.PdfReader') as reader:
            reader.return_value.is_encrypted = False
            reader.return_value.pages = [Page(first), Page(second)]
            found = _first_pdf_text(b'%PDF-example', 'RE', '1334584')
        self.assertEqual(found['case_suffix'], 'AgR-ED-AgR')
        self.assertEqual(found['case_state'], 'RJ')
        self.assertTrue(found['ementa'].endswith('O recurso não foi provido.'))
        self.assertNotIn('ACÓRDÃO', found['ementa'])

    def test_main_judgment_takes_precedence_over_appeal(self):
        records = [{'publication_date': '10/01/2023', 'disclosure_date': '09/01/2023',
                    'url': 'https://portal.stf.jus.br/processos/downloadPeca.asp?id=1&ext=.pdf'},
                   {'publication_date': '22/08/2019', 'disclosure_date': '21/08/2019',
                    'url': 'https://portal.stf.jus.br/processos/downloadPeca.asp?id=2&ext=.pdf'}]
        appeal = {'case_state': 'MG', 'case_suffix': 'AgR-ED-AgR', 'judgment_date': '03/11/2022',
                  'relator': 'Dias Toffoli', 'court_body': 'Primeira Turma', 'ementa': 'Agravo confirmado.'}
        main = {'case_state': 'MG', 'judgment_date': '28/02/2019',
                'relator': 'Luiz Fux', 'court_body': 'Tribunal Pleno', 'ementa': 'Recurso confirmado.'}
        response = [(b'<html>RE 663696</html>', 'https://portal.stf.jus.br/processos/detalhe.asp?incidente=4168352'),
                    (b'<div></div>', 'https://portal.stf.jus.br/processos/abaAndamentos.asp'),
                    (b'%PDF-first', records[0]['url']), (b'%PDF-second', records[1]['url'])]
        with patch('case_law._stf_get', side_effect=response), patch('case_law._publications', return_value=records), \
             patch('case_law._first_pdf_text', side_effect=[appeal, main]):
            found = fetch_stf_case({'case_class': 'RE', 'case_number': '663696', 'case_state': 'MG'})
        self.assertNotIn('case_suffix', found)
        self.assertEqual(found['publication_date'], '22/08/2019')

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
