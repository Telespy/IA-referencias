import io
import unittest
import zipfile
from xml.sax.saxutils import escape

import reference_extractor as rx


def make_docx(paragraphs: list[str]) -> bytes:
    """DOCX mínimo em memória: um parágrafo <w:p> por item da lista."""
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>' for text in paragraphs
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


TCC_PARAGRAPHS = [
    "1 INTRODUÇÃO",
    "O estudo de Silva (2019) mostrou ganhos, e outros trabalhos confirmam (SOUZA et al., 2020; BRASIL, 2012).",
    "Também há citação sem entrada (PEREIRA, 2015).",
    "REFERÊNCIAS ........................ 45",
    "APÊNDICE A – Questionário",
    "5 REFERÊNCIAS",
    "SILVA, Maria. Análise de dados. São Paulo: Atlas, 2019. 320 p.",
    "SOUZA, João; LIMA, Ana; ROCHA, Paulo; TEIXEIRA, Clara. Um estudo. Revista X, v. 2, n. 1, p. 1-9, 2020. DOI: 10.1234/abc.2020.1.",
    "BRASIL. Lei nº 12.711, de 29 de agosto de 2012. Dispõe sobre o ingresso nas universidades federais. Diário Oficial da União, Brasília, DF, 30 ago. 2012.",
    "ABNT. NBR 6023: informação e documentação: referências: elaboração. Rio de Janeiro: ABNT, 2018.",
    "GOOGLE. Google Translate. 2024. Disponível em: https://translate.google.com. Acesso em: 10 out. 2024.",
    "APÊNDICE B – Tabela",
    "Texto que não deve virar referência.",
]


class SectionTests(unittest.TestCase):
    def test_docx_uses_last_heading_and_skips_toc(self):
        lines, paragraph_mode = rx.read_document("tcc.docx", make_docx(TCC_PARAGRAPHS))
        self.assertTrue(paragraph_mode)
        ref_lines, body_lines = rx.find_reference_section(lines)
        self.assertEqual(len(ref_lines), 5)
        self.assertTrue(ref_lines[0].startswith("SILVA, Maria"))
        self.assertTrue(any("Silva (2019)" in line for line in body_lines))

    def test_section_stops_at_appendix(self):
        ref_lines, _ = rx.find_reference_section(TCC_PARAGRAPHS)
        self.assertFalse(any("Texto que não deve" in line for line in ref_lines))
        self.assertFalse(any("APÊNDICE" in line for line in ref_lines))

    def test_missing_section_returns_none(self):
        self.assertIsNone(rx.find_reference_section(["Introdução", "Texto qualquer."]))


class SplitTests(unittest.TestCase):
    def test_paragraph_mode_keeps_each_paragraph_as_entry(self):
        entries = rx.split_entries(["SILVA, Maria. Título longo", "  ", "BRASIL. Lei"], paragraph_mode=True)
        self.assertEqual(entries, ["SILVA, Maria. Título longo", "BRASIL. Lei"])

    def test_line_mode_joins_wrapped_lines_and_splits_authors(self):
        lines = [
            "SILVA, Maria. Análise de dados com",
            "métodos mistos. São Paulo: Atlas, 2019.",
            "SOUZA, João. Outro trabalho. Revista,",
            "2020.",
            "",
            "___. Segundo trabalho do mesmo autor. 2021.",
        ]
        entries = rx.split_entries(lines, paragraph_mode=False)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0], "SILVA, Maria. Análise de dados com métodos mistos. São Paulo: Atlas, 2019.")
        self.assertEqual(entries[1], "SOUZA, João. Outro trabalho. Revista, 2020.")
        self.assertTrue(entries[2].startswith("___."))

    def test_line_mode_rejoins_pdf_hyphenation(self):
        entries = rx.split_entries(["SILVA, Maria. Título univer-", "sidade. 2019."], paragraph_mode=False)
        self.assertEqual(entries, ["SILVA, Maria. Título universidade. 2019."])


class CitationTests(unittest.TestCase):
    def test_entity_acronym_matches_entry(self):
        entries = ["CONSELHO NACIONAL DE SAÚDE (Brasil). Resolução nº 510, de 2016. Brasília: CNS, 2016."]
        result = rx.cross_check(rx.find_citations("Regras (CNS, 2016)."), entries)
        self.assertEqual(result["sem_referencia"], [])

    def test_sentence_starter_is_not_a_surname(self):
        citations = rx.find_citations("Segundo Gil (2008) e Conforme Gil (2008).")
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["nomes"], ["gil"])

    def test_finds_parenthetical_and_narrative_citations(self):
        body = "Segundo Silva (2019), e (SOUZA et al., 2020; BRASIL, 2012, p. 4). Ver (PEREIRA, 2015)."
        found = {(c["sobrenome"].split()[-1], c["ano"]) for c in rx.find_citations(body)}
        self.assertEqual(found, {("Silva", "2019"), ("SOUZA", "2020"), ("BRASIL", "2012"), ("PEREIRA", "2015")})

    def test_ignores_page_only_parentheses(self):
        self.assertEqual(rx.find_citations("Conforme o texto (p. 12)."), [])

    def test_cross_check_reports_missing_and_uncited(self):
        entries = [
            "SILVA, Maria. Análise. São Paulo: Atlas, 2019.",
            "SOUZA, João. Outro. Revista, 2020. Acesso em: 10 out. 2024.",
            "LIMA, Ana. Sem citação. Editora, 2010.",
        ]
        citations = rx.find_citations("(SILVA, 2019) e (SOUZA et al., 2020) e (PEREIRA, 2015)")
        result = rx.cross_check(citations, entries)
        self.assertEqual([c["sobrenome"] for c in result["sem_referencia"]], ["PEREIRA"])
        self.assertEqual(result["referencias_sem_citacao"], [3])

    def test_access_year_does_not_count_as_publication_year(self):
        # Citação de 2024 não deve casar com entrada publicada em 2020 só por causa do acesso em 2024.
        entries = ["SOUZA, João. Outro. Revista, 2020. Acesso em: 10 out. 2024."]
        result = rx.cross_check(rx.find_citations("(SOUZA, 2024)"), entries)
        self.assertEqual(len(result["sem_referencia"]), 1)


class ExtractReferencesTests(unittest.TestCase):
    def test_end_to_end_docx(self):
        report = rx.extract_references("tcc.docx", make_docx(TCC_PARAGRAPHS))
        self.assertTrue(report["secao_encontrada"])
        self.assertEqual(report["total"], 5)
        first, second = report["referencias"][0], report["referencias"][1]
        self.assertEqual(second["doi"], "10.1234/abc.2020.1")
        self.assertEqual(report["referencias"][4]["acesso"], "10 out. 2024")
        self.assertEqual(report["referencias"][3]["urls"], [])
        self.assertIn("isbn", first)
        missing = [c["sobrenome"] for c in report["citacoes"]["sem_referencia"]]
        self.assertEqual(missing, ["PEREIRA"])
        self.assertEqual(report["citacoes"]["referencias_sem_citacao"], [4, 5])
        self.assertTrue(any("sem entrada" in aviso for aviso in report["avisos"]))

    def test_txt_without_section_reports_warning(self):
        report = rx.extract_references("nota.txt", "Apenas um texto sem seção.".encode("utf-8"))
        self.assertFalse(report["secao_encontrada"])
        self.assertEqual(report["total"], 0)
        self.assertTrue(report["avisos"])

    def test_unsupported_extension_rejected(self):
        with self.assertRaises(ValueError):
            rx.read_document("planilha.xlsx", b"x")

    def test_corrupt_docx_rejected(self):
        with self.assertRaises(ValueError):
            rx.read_document("tcc.docx", b"nao sou zip")

    def test_size_limit_rejected(self):
        with self.assertRaises(ValueError):
            rx.read_document("grande.txt", b"a" * (rx.MAX_DOCUMENT_BYTES + 1))


class RealWorldPatternTests(unittest.TestCase):
    def test_label_copy_block_is_removed_as_duplicate(self):
        paragraphs = [
            "REFERÊNCIAS",
            "BARROS, José D’Assunção. O campo da história. 9. ed. Petrópolis: Vozes, 2021.",
            "Barros, 2021 BARROS, José D’Assunção. O campo da história. 9. ed. Petrópolis: Vozes, 2021.",
            "Bauer; Gaskell, 2015. BAUER, Martin W.; GASKELL, George. Pesquisa. Petrópolis: Vozes, 2015.",
        ]
        report = rx.extract_references("tcc.docx", make_docx(paragraphs))
        self.assertEqual(report["total"], 2)
        self.assertTrue(any("repetida" in aviso for aviso in report["avisos"]))

    def test_trailing_non_reference_paragraphs_are_dropped(self):
        paragraphs = [
            "REFERÊNCIAS",
            "SILVA, Maria. Análise de dados. São Paulo: Atlas, 2019.",
            "Atividades",
            "1º ano (meses)",
        ]
        report = rx.extract_references("tcc.docx", make_docx(paragraphs))
        self.assertEqual(report["total"], 1)
        self.assertTrue(any("ignorados" in aviso for aviso in report["avisos"]))

    def test_citation_with_c_year_and_page_matches(self):
        body = "Segundo o IBGE (c2023) e Lakatos e Marconi (2003, p. 183)."
        found = {(c["nomes"][0] if len(c["nomes"]) == 1 else tuple(sorted(c["nomes"])), c["ano"]) for c in rx.find_citations(body)}
        self.assertIn(("ibge", "2023"), found)
        self.assertTrue(any({"lakatos", "marconi"} <= set(c["nomes"]) and c["ano"] == "2003" for c in rx.find_citations(body)))


class ApiExtractTests(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi.testclient import TestClient
            from api.index import app
        except ImportError as exc:  # pragma: no cover - depende do ambiente
            self.skipTest(f"Dependência de API ausente: {exc}")
        self.client = TestClient(app)

    def test_extract_endpoint_returns_entries(self):
        files = {"file": ("tcc.docx", make_docx(TCC_PARAGRAPHS), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        response = self.client.post("/api/extract", files=files)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total"], 5)
        self.assertEqual(body["referencias"][0]["indice"], 1)

    def test_extract_endpoint_rejects_unsupported_file(self):
        response = self.client.post("/api/extract", files={"file": ("dados.xlsx", b"x", "application/octet-stream")})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
