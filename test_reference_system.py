import unittest
from unittest.mock import patch

from formatters import format_abnt, format_apa, get_missing_attributes
from main import process_reference_line
from parsers import identify_input_type, parse_raw_citation_text


class ReferenceSystemTests(unittest.TestCase):
    def test_isbn_input_is_routed_to_book_fetcher(self):
        with patch("main.fetch_google_books") as fetch_books:
            fetch_books.return_value = {
                "item_type": "book",
                "title": "Livro de teste",
                "authors": [{"family": "SILVA", "given": "Maria"}],
                "year": "2020",
                "publisher": "Teste",
                "city": "São Paulo",
                "isbn": "9788535208030",
            }

            result = process_reference_line("9788535208030")

        fetch_books.assert_called_once_with("9788535208030")
        self.assertEqual(result["item_type"], "book")
        self.assertIn("Livro de teste", result["meta"]["title"])

    def test_doi_url_is_routed_to_crossref(self):
        with patch("main.fetch_crossref_doi") as fetch_doi:
            fetch_doi.return_value = {
                "item_type": "journalArticle",
                "title": "Array programming with NumPy",
                "authors": [{"family": "Harris", "given": "Charles R."}],
                "journal": "Nature",
                "year": "2020",
                "volume": "585",
                "issue": "7825",
                "page": "357-362",
                "doi": "10.1038/s41586-020-2649-2",
                "city": "London, UK",
            }

            result = process_reference_line("https://doi.org/10.1038/s41586-020-2649-2")

        fetch_doi.assert_called_once_with("10.1038/s41586-020-2649-2")
        self.assertEqual(result["item_type"], "journalArticle")
        self.assertIn("NumPy", result["apa"])

    def test_failed_exact_doi_does_not_search_unrelated_work(self):
        with patch("main.fetch_crossref_doi", return_value={}) as fetch_doi, patch("main.fetch_crossref_search") as search:
            result = process_reference_line("10.9999/not-found")

        fetch_doi.assert_called_once_with("10.9999/not-found")
        search.assert_not_called()
        self.assertEqual(result["meta"]["doi"], "10.9999/not-found")
        self.assertIn("Título da obra", result["missing_fields"])

    def test_chapter_edition_is_not_duplicated(self):
        raw = (
            "ALMEIDA, Carlos. O papel da tecnologia na sala de aula. "
            "In: SILVA, Maria; SOUZA, João (org.). Educação contemporânea: "
            "desafios e perspectivas. 2. ed. São Paulo: Cortez, 2019. p. 45-60."
        )
        meta = parse_raw_citation_text(raw)
        abnt = format_abnt(meta)

        self.assertEqual(meta["item_type"], "chapter")
        self.assertEqual(meta["book_title"], "Educação contemporânea: desafios e perspectivas")
        self.assertEqual(abnt.count("2. ed."), 1)
        self.assertIn("2019. p. 45-60.", abnt)

    def test_chapter_editor_role_is_not_invented(self):
        raw = (
            "SILVA, Tarcizio. Dos autômatos e robôs às redes difusas de agência no racismo algorítmico. "
            "In: TAVARES, A. R. Vestígios do futuro: 100 anos de Isaac Asimov. "
            "Rio de Janeiro: Editora Etheria, 2020."
        )
        meta = parse_raw_citation_text(raw)
        abnt = format_abnt(meta)

        self.assertEqual(meta["item_type"], "chapter")
        self.assertEqual(meta["book_title"], "Vestígios do futuro: 100 anos de Isaac Asimov")
        self.assertEqual(meta["book_authors"][0]["family"], "TAVARES")
        self.assertEqual(meta["book_authors"][0]["given"], "A. R.")
        self.assertEqual(meta["book_authors"][0]["role"], "")
        self.assertNotIn("(ed.)", abnt)

    def test_subtitle_starts_with_lowercase_in_abnt(self):
        raw = (
            "WOODWARD, Kathryn. Identidade e diferença: uma introdução teórica e conceitual. "
            "In: SILVA, Tomaz Tadeu da (org.). Identidade e diferença: a perspectiva dos estudos culturais. "
            "Petrópolis: Vozes, 2000. p. 7-72."
        )
        meta = parse_raw_citation_text(raw)
        abnt = format_abnt(meta)

        self.assertEqual(meta["item_type"], "chapter")
        self.assertIn("**Identidade e diferença**: a perspectiva dos estudos culturais.", abnt)

    def test_website_is_not_classified_as_legal_book(self):
        raw = (
            "MINISTÉRIO DA EDUCAÇÃO. Reforma do ensino médio: perguntas e respostas. "
            "Portal MEC, Brasília, DF, 10 mar. 2022. Disponível em: "
            "https://gov.br/mec/reforma. Acesso em: 10 jan. 2023."
        )
        meta = parse_raw_citation_text(raw)

        self.assertEqual(meta["item_type"], "website")
        self.assertEqual(meta["access_date"], "10 jan. 2023")
        self.assertIn("Portal MEC", format_abnt(meta))

    def test_complete_print_article_does_not_require_doi_or_url(self):
        raw = (
            "SAVIANI, Dermeval. O choque teórico da politecnia. "
            "Trabalho, Educação e Saúde, Rio de Janeiro, v. 1, n. 1, "
            "p. 131-152, 2003."
        )
        meta = parse_raw_citation_text(raw)

        self.assertEqual(get_missing_attributes(meta), [])

    def test_apa_without_author_starts_with_title(self):
        meta = {
            "item_type": "book",
            "title": "Manual sem autor",
            "year": "",
            "publisher": "",
            "authors": [],
        }

        self.assertTrue(format_apa(meta).startswith("*Manual sem autor*. (n.d.)."))

    def test_identifier_detection_preserves_full_isbn(self):
        self.assertEqual(identify_input_type("9788535208030"), {"type": "isbn", "query": "9788535208030"})

    def test_book_with_page_count_is_classified_as_book_not_journal(self):
        raw = "LUCKESI, Cipriano Carlos. Avaliação da aprendizagem escolar. São Paulo: Cortez, 2011. 180 p."
        meta = parse_raw_citation_text(raw)
        self.assertEqual(meta["item_type"], "book")
        self.assertEqual(meta["publisher"], "Cortez")
        self.assertEqual(meta["year"], "2011")
        self.assertIn("Cortez, 2011.", format_abnt(meta))

    def test_proceedings_classification_and_abnt(self):
        raw = (
            "SOUZA, João. Metodologias ativas no ensino fundamental. "
            "In: CONGRESSO BRASILEIRO DE EDUCAÇÃO, 3., 2019, Natal. "
            "Anais [...]. Natal: IFRN, 2019. p. 10-25."
        )
        meta = parse_raw_citation_text(raw)
        self.assertEqual(meta["item_type"], "proceedings")
        self.assertEqual(meta["event_name"], "CONGRESSO BRASILEIRO DE EDUCAÇÃO")
        self.assertEqual(meta["page"], "10-25")
        abnt = format_abnt(meta)
        self.assertIn("*In*: CONGRESSO BRASILEIRO DE EDUCAÇÃO", abnt)

    def test_legislation_classification_and_abnt(self):
        raw = (
            "BRASIL. Lei nº 11.892, de 29 de dezembro de 2008. "
            "Institui a Rede Federal de Educação Profissional. "
            "Brasília, DF: Presidência da República, 2008."
        )
        meta = parse_raw_citation_text(raw)
        self.assertEqual(meta["item_type"], "legislation")
        self.assertEqual(meta["jurisdiction"], "BRASIL")
        self.assertIn("Presidência da República", format_abnt(meta))

    def test_newspaper_classification_and_abnt(self):
        raw = (
            "SILVA, Carlos. A inteligência artificial no mercado editorial. "
            "Folha de S.Paulo, São Paulo, 15 mar. 2022. Caderno Ilustrada, p. B2."
        )
        meta = parse_raw_citation_text(raw)
        self.assertEqual(meta["item_type"], "newspaperArticle")
        self.assertEqual(meta["newspaper"], "Folha de S.Paulo")
        abnt = format_abnt(meta)
        self.assertIn("**Folha de S.Paulo**", abnt)

    def test_patent_classification_and_abnt(self):
        raw = (
            "SOUZA, Marcos. Dispositivo de filtragem biológica. "
            "BR 10 2012 000000 0 A2. Depósito: 10 jan. 2012. Concessão: 15 out. 2019."
        )
        meta = parse_raw_citation_text(raw)
        self.assertEqual(meta["item_type"], "patent")
        self.assertEqual(meta["patent_no"], "BR 10 2012 000000 0 A2")
        abnt = format_abnt(meta)
        self.assertIn("BR 10 2012 000000 0 A2", abnt)


if __name__ == "__main__":
    unittest.main()
