import unittest

from formatters import format_sentence_case
from main import process_reference_line


class SentenceCaseTests(unittest.TestCase):
    def test_single_uppercase_letter_is_kept_mid_title(self):
        self.assertEqual(format_sentence_case("Análise de dados com R"), "Análise de dados com R")

    def test_proper_name_kept_in_sentence_case_input(self):
        self.assertEqual(format_sentence_case("Gestão escolar com João Souza em Pernambuco"),
                         "Gestão escolar com João Souza em Pernambuco")

    def test_title_case_input_is_still_lowercased(self):
        # Caixa de título (ex.: Crossref) mantém a regra geral de sentence case.
        self.assertEqual(format_sentence_case("Deep Residual Learning for Image Recognition"),
                         "Deep residual learning for image recognition")

    def test_norm_acronym_kept_uppercase(self):
        self.assertIn("**NBR 6023**", process_reference_line(
            "ABNT. NBR 6023: informação e documentação: referências: elaboração. Rio de Janeiro: ABNT, 2018.",
            online=False)["abnt"])


class UnsupportedTypeTests(unittest.TestCase):
    def test_interview_goes_to_review_not_book(self):
        result = process_reference_line("SILVA, Maria. Entrevista concedida a João Souza. São Paulo, 10 jan. 2020.", online=False)
        self.assertEqual(result["item_type"], "unknown")
        self.assertEqual(result["status"], "needs_review")

    def test_software_goes_to_review(self):
        result = process_reference_line("MARTINS, C. Título de software. Versão 2.0. São Paulo: Autor, 2020. Software.", online=False)
        self.assertEqual(result["item_type"], "unknown")
        self.assertEqual(result["status"], "needs_review")


class BookAndProceedingsTests(unittest.TestCase):
    def test_book_page_count_is_kept(self):
        result = process_reference_line("SOUZA, J. Análise de dados. 2. ed. São Paulo: Atlas, 2019. 320 p.", online=False)
        self.assertIn("2019. 320 p.", result["abnt"])

    def test_proceedings_year_not_duplicated_and_title_closed(self):
        result = process_reference_line(
            "HE, Kaiming et al. Deep Residual Learning for Image Recognition. In: IEEE CONFERENCE ON COMPUTER VISION "
            "AND PATTERN RECOGNITION, 2016, Las Vegas. Proceedings [...]. Las Vegas: IEEE, 2016. p. 770-778.",
            online=False)
        self.assertNotIn("2016., 2016", result["abnt"])
        self.assertIn("**Proceedings [...]**. Las Vegas: IEEE, 2016.", result["abnt"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
