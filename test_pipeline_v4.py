import unittest
from unittest.mock import patch

from formatters import format_abnt, get_missing_attributes
from main import process_reference_line
from normalizer import normalize_reference_input
from resolver_pipeline import _safe_public_url, resolve_reference, enrich_from_official_page, academic_repository_metadata
from parsers import parse_raw_citation_text


AFP_RAW = (
    "AFP. Indústria da música está ameaçada por bandas geradas por IA: 'desafio incomparável'. "
    "**O Globo**, 30 jul. 2025. Disponível em: https\\://oglobo.\\\n"
    "&#x20;globo.com/cultura/musica/noticia/2025/07/30/industria-da-musica-esta-ameacada-por-bandas-geradas-por-ia-desafio-incomparavel.ghtml. "
    "Acesso em: 16 ago. 2026.\\"
)

FGV_RAW = (
    "OLIVEIRA, João Carlos Cochlar de. **Clareza e legitimidade**. 2020. "
    "Monografia (Bacharelado em Direito) – Fundação Getulio Vargas, Rio de Janeiro, 2020. "
    "Disponível em: https\\://\\\n"
    "&#x20;repositorio.fgv.br/items/398149b8-383a-4abe-8ca0-bc54796265c5. Acesso em: 14 ago. 2026."
)

WIPO_RAW = "WIPO. **O que é propriedade intelectual**? WIPO, 2021."


class NormalizerTests(unittest.TestCase):
    def test_repairs_wrapped_escaped_url_and_html_entity(self):
        clean, steps = normalize_reference_input(AFP_RAW)
        self.assertIn("https://oglobo.globo.com/", clean)
        self.assertNotIn("&#x20;", clean)
        self.assertNotIn("\\://", clean)
        self.assertTrue(steps)

    def test_removes_markdown_without_losing_content(self):
        clean, _ = normalize_reference_input("AUTOR. **Título principal**: subtítulo.")
        self.assertEqual(clean, "AUTOR. Título principal: subtítulo.")

    def test_original_is_preserved_but_parser_receives_clean_text(self):
        result = process_reference_line(AFP_RAW, online=False)
        self.assertEqual(result["raw"], AFP_RAW.strip())
        self.assertNotIn("**", result["normalized_input"])
        self.assertIn("https://oglobo.globo.com/", result["normalized_input"])


class AuthorityPipelineTests(unittest.TestCase):
    def test_oglobo_reference_is_completed_and_verified(self):
        result = process_reference_line(AFP_RAW)
        self.assertTrue(result["approved"], result)
        self.assertEqual(result["meta"]["city"], "Rio de Janeiro")
        self.assertEqual(result["meta"]["newspaper"], "O Globo")
        self.assertIn("Rio de Janeiro, 30 jul. 2025", result["abnt"])
        self.assertNotIn("****", result["abnt"])

    def test_fgv_subtitle_is_recovered(self):
        result = process_reference_line(FGV_RAW)
        self.assertTrue(result["approved"], result)
        self.assertEqual(
            result["meta"]["title"],
            "Clareza e legitimidade: como elementos de teoria musical podem iluminar a interpretação jurídica?",
        )
        self.assertEqual(result["meta"]["city"], "Rio de Janeiro")
        self.assertEqual(result["meta"]["institution"], "Fundação Getulio Vargas")
        self.assertEqual(result["meta"]["access_date"], "14 ago. 2026")
        self.assertIn("como elementos de teoria musical podem iluminar a interpretação jurídica?", result["abnt"])
        self.assertNotIn("?.", result["abnt"])

    def test_wipo_city_publisher_and_identifiers_are_recovered(self):
        result = process_reference_line(WIPO_RAW)
        self.assertTrue(result["approved"], result)
        self.assertEqual(result["meta"]["city"], "Genebra")
        self.assertEqual(result["meta"]["publisher"], "WIPO")
        self.assertEqual(result["meta"]["isbn"], "9789280532265")
        self.assertEqual(result["meta"]["doi"], "10.34667/tind.44584")
        self.assertIn("Genebra: WIPO, 2021", result["abnt"])
        self.assertNotIn("?.", result["abnt"])

    def test_verified_record_has_field_provenance_and_confidence(self):
        result = process_reference_line(WIPO_RAW)
        for field in ("title", "city", "publisher", "year"):
            self.assertTrue(result["provenance"][field]["verified"])
            self.assertGreaterEqual(result["provenance"][field]["confidence"], 0.99)

    def test_entity_profile_alone_never_approves_unknown_work(self):
        raw = "WIPO. Relatório experimental inexistente. WIPO, 2024."
        clean, _ = normalize_reference_input(raw)
        parsed = parse_raw_citation_text(clean)
        fetched = resolve_reference(clean, parsed, online=False)
        self.assertTrue(fetched.get("_entity_profile"))
        self.assertFalse(fetched.get("_work_verified"))

    def test_online_newspaper_does_not_require_physical_page(self):
        meta = {
            "item_type": "newspaperArticle",
            "authors": [{"family": "AFP", "given": ""}],
            "title": "Notícia online",
            "newspaper": "O Globo",
            "city": "Rio de Janeiro",
            "year": "2025",
            "date_str": "30 jul. 2025",
            "url": "https://example.com/noticia",
        }
        self.assertNotIn("Página ou Seção do jornal", get_missing_attributes(meta))

    def test_question_mark_is_not_followed_by_extra_period(self):
        meta = {
            "item_type": "book",
            "authors": [{"family": "WIPO", "given": "", "is_corporate": True}],
            "title": "O que é propriedade intelectual?",
            "city": "Genebra",
            "publisher": "WIPO",
            "year": "2021",
        }
        out = format_abnt(meta)
        self.assertNotIn("?.", out)


    @patch("main.enrich_article", side_effect=lambda meta: meta)
    @patch("resolver_pipeline.fetch_public_page_metadata")
    @patch("main.fetch_crossref_doi")
    def test_journal_doi_enriches_month_and_available_url_without_inventing_volume(
        self, fetch_crossref, fetch_page, _enrich
    ):
        raw = (
            "ROSENBLATT, Paulo; MOREIRA, Gabriel Eugênio Barreto. "
            "Nem tanto ao céu, nem tanto à terra: repensando a aplicação do propósito negocial "
            "a partir de uma análise da recente jurisprudência do CARF. "
            "Revista Direito Tributário Atual, São Paulo, n. 43, p. 499-523, 2019. "
            "DOI: https://doi.org/10.46801/2595-6280-rdta-43-22."
        )
        fetch_crossref.return_value = {
            "item_type": "journalArticle",
            "title": "Nem tanto ao Céu, nem tanto à Terra",
            "authors": [
                {"family": "Rosenblatt", "given": "Paulo"},
                {"family": "Moreira", "given": "Gabriel Eugênio Barreto"},
            ],
            "year": "2019",
            "journal": "Revista Direito Tributário Atual",
            "volume": "",
            "issue": "43",
            "page": "499-523",
            "publisher": "Instituto Brasileiro de Direito Tributario",
            "doi": "10.46801/2595-6280-rdta-43-22",
            "url": "https://revista.ibdt.org.br/index.php/RDTA/article/view/1458",
            "start_month": 12,
            "_source": {"name": "Crossref", "url": "https://api.crossref.org/works/test", "retrieved_at": ""},
        }
        fetch_page.return_value = {
            "title": "Nem tanto ao Céu, nem tanto à Terra: repensando a Aplicação do Propósito Negocial a partir de uma Análise da Recente Jurisprudência do CARF",
            "authors": [
                {"family": "Rosenblatt", "given": "Paulo"},
                {"family": "Moreira", "given": "Gabriel Eugênio Barreto"},
            ],
            "journal": "Revista Direito Tributário Atual",
            "issue": "43",
            "doi": "10.46801/2595-6280-rdta-43-22",
            "year": "2019",
            "start_month": 12,
            "url": "https://revista.ibdt.org.br/index.php/RDTA/article/view/1458",
        }

        result = process_reference_line(raw)
        self.assertEqual(result["item_type"], "journalArticle")
        self.assertEqual(result["meta"].get("start_month"), 12)
        self.assertFalse(result["meta"].get("volume"))
        self.assertIn("dez. 2019", result["abnt"])
        self.assertIn("Disponível em:", result["abnt"])
        self.assertIn("https://revista.ibdt.org.br/index.php/RDTA/article/view/1458", result["abnt"])
        self.assertNotIn("v. ", result["abnt"])
        self.assertNotIn("UNSUPPORTED_TYPE", [i["code"] for i in result["issues"]])


    @patch("resolver_pipeline.fetch_public_page_metadata")
    def test_generic_official_page_enrichment_works_for_book(self, fetch_page):
        base = {
            "item_type": "book",
            "title": "Manual de teste",
            "authors": [{"family": "SILVA", "given": "Ana"}],
            "year": "2024",
            "url": "https://example.org/manual",
            "_source": {"name": "Catálogo", "url": "https://catalog.example/manual", "retrieved_at": ""},
        }
        fetch_page.return_value = {
            "title": "Manual de teste",
            "authors": [{"family": "SILVA", "given": "Ana"}],
            "year": "2024",
            "publisher": "Editora Exemplo",
            "url": "https://example.org/manual",
        }
        out = enrich_from_official_page(base, base)
        self.assertEqual(out["publisher"], "Editora Exemplo")
        self.assertEqual(out["_field_sources"]["publisher"]["name"], "Página oficial da obra")

    @patch("resolver_pipeline.fetch_public_page_metadata")
    def test_generic_official_page_does_not_merge_different_work(self, fetch_page):
        base = {
            "item_type": "book",
            "title": "Manual de teste",
            "authors": [{"family": "SILVA", "given": "Ana"}],
            "year": "2024",
            "url": "https://example.org/manual",
        }
        fetch_page.return_value = {
            "title": "Outra obra completamente diferente",
            "authors": [{"family": "COSTA", "given": "Bruno"}],
            "year": "2020",
            "publisher": "Editora Errada",
            "url": "https://example.org/manual",
        }
        out = enrich_from_official_page(base, base)
        self.assertNotIn("publisher", out)


    def test_verified_thesis_record_keeps_degree_institution_city_and_canonical_url(self):
        raw = (
            "RUZYK, Carlos Eduardo Pianovski. Liberdade(s) e função: contribuição crítica para uma nova "
            "fundamentação da dimensão funcional do Direito Civil brasileiro. 2009."
        )
        result = process_reference_line(raw, online=False)
        self.assertEqual(result["item_type"], "thesis")
        self.assertEqual(result["meta"]["degree_type"], "Tese (Doutorado em Direito das Relações Sociais)")
        self.assertEqual(result["meta"]["institution"], "Universidade Federal do Paraná")
        self.assertEqual(result["meta"]["city"], "Curitiba")
        self.assertEqual(result["meta"]["url"], "https://acervodigital.ufpr.br/handle/1884/19174")
        self.assertNotIn("publisher", result["meta"])
        self.assertIn("Tese (Doutorado em Direito das Relações Sociais)", result["abnt"])
        self.assertIn("Universidade Federal do Paraná, Curitiba, 2009", result["abnt"])

    def test_generic_dspace_metadata_recovers_academic_structure(self):
        page = {
            "title": "Políticas públicas e educação",
            "authors": [{"family": "SOUZA", "given": "Ana"}],
            "url": "https://repositorio.exemplo.edu.br/handle/123/456",
            "_descriptions": [
                "Tese (doutorado) - Universidade Exemplo, Faculdade de Educação, "
                "Programa de Pós-Graduação em Educação. Defesa: Recife, 14/03/2022"
            ],
            "_contributors": [
                "Universidade Exemplo. Faculdade de Educação. Programa de Pós-Graduação em Educação"
            ],
            "_identifiers": ["https://hdl.handle.net/123/456"],
            "_types": ["livro digital"],
        }
        meta = academic_repository_metadata(page)
        self.assertEqual(meta["item_type"], "thesis")
        self.assertEqual(meta["degree_type"], "Tese (Doutorado em Educação)")
        self.assertEqual(meta["institution"], "Universidade Exemplo")
        self.assertEqual(meta["city"], "Recife")
        self.assertEqual(meta["year"], "2022")
        self.assertEqual(meta["defense_date"], "14/03/2022")


class URLSafetyTests(unittest.TestCase):
    def test_private_and_local_urls_are_rejected(self):
        for url in (
            "http://127.0.0.1/a",
            "http://10.0.0.1/a",
            "http://192.168.1.1/a",
            "http://localhost/a",
            "file:///etc/passwd",
        ):
            self.assertFalse(_safe_public_url(url), url)

    @patch("resolver_pipeline.socket.getaddrinfo")
    def test_hostname_resolving_to_private_ip_is_rejected(self, lookup):
        lookup.return_value = [(2, 1, 6, "", ("10.0.0.2", 443))]
        self.assertFalse(_safe_public_url("https://example.invalid/path"))


if __name__ == "__main__":
    unittest.main()
