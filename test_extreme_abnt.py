import unittest

from parsers import parse_raw_citation_text
from formatters import format_abnt


class ExtremeABNTSuite(unittest.TestCase):
    """Data-driven regression suite for noisy and edge-case ABNT references."""

    CASES = [
        # Livros
        ("book", "SILVA, João. Introdução à pesquisa científica. São Paulo: Atlas, 2020.", ["SILVA", "Atlas", "2020"]),
        ("book", "SILVA, João; SOUZA, Maria. Metodologia científica. Rio de Janeiro: LTC, 2019.", ["SILVA", "SOUZA", "LTC"]),
        ("book", "SILVA, João; SOUZA, Maria; LIMA, Carlos. Pesquisa aplicada. Recife: UFPE, 2021.", ["2021", "Pesquisa aplicada"]),
        ("book", "SILVA, João; SOUZA, Maria; LIMA, Carlos; COSTA, Ana. Pesquisa interdisciplinar. São Paulo: Atlas, 2022.", ["et al.", "Atlas"]),
        ("book", "CASTELO BRANCO, Carlos. Teoria geral da administração. Fortaleza: Premius, 2018.", ["CASTELO BRANCO", "Fortaleza", "2018"]),
        ("book", "ESPÍRITO SANTO, Marcos. Gestão pública contemporânea. Vitória: EDUFES, 2017.", ["ESPÍRITO SANTO", "2017"]),
        ("book", "SILVA JÚNIOR, Paulo. Direito administrativo. Brasília, DF: Fórum, 2020.", ["SILVA JÚNIOR", "2020"]),
        ("book", "OLIVEIRA NETO, José. Contabilidade aplicada. Belo Horizonte: Del Rey, 2016.", ["OLIVEIRA NETO", "2016"]),
        ("book", "MORAES FILHO, Evaristo. Sociologia do direito. São Paulo: Saraiva, 2015.", ["MORAES FILHO", "2015"]),
        ("book", "SOUZA, Ana. Manual de pesquisa: métodos e técnicas. 3. ed. rev. e ampl. São Paulo: Atlas, 2023.", ["Manual de pesquisa", "São Paulo", "2023"]),
        ("book", "LUCKESI, Cipriano Carlos. Avaliação da aprendizagem escolar. São Paulo: Cortez, 2011. 180 p.", ["Cortez", "2011"]),
        ("book", "ASSOCIAÇÃO BRASILEIRA DE NORMAS TÉCNICAS. Informação e documentação. Rio de Janeiro: ABNT, 2018.", ["ABNT", "2018"]),

        # Capítulos
        ("chapter", "ALMEIDA, Carlos. Tecnologia na escola. In: SILVA, Maria (org.). Educação contemporânea. São Paulo: Cortez, 2019. p. 45-60.", ["In", "Educação contemporânea", "45-60"]),
        ("chapter", "WOODWARD, Kathryn. Identidade e diferença: uma introdução teórica e conceitual. In: SILVA, Tomaz Tadeu da (org.). Identidade e diferença: a perspectiva dos estudos culturais. Petrópolis: Vozes, 2000. p. 7-72.", ["Vozes", "7-72"]),
        ("chapter", "SANTOS, José. Redes digitais. In: CASTELO BRANCO, Carlos; SOUZA, Ana (orgs.). Comunicação e sociedade. Fortaleza: UFC, 2021. p. 10-29.", ["CASTELO BRANCO", "UFC", "10-29"]),
        ("chapter", "PEREIRA, Ana. Saúde coletiva. In: OLIVEIRA NETO, José (ed.). Políticas de saúde. Recife: UFPE, 2020. p. 101-119.", ["OLIVEIRA NETO", "UFPE"]),

        # Periódicos
        ("journalArticle", "SAVIANI, Dermeval. O choque teórico da politecnia. Trabalho, Educação e Saúde, Rio de Janeiro, v. 1, n. 1, p. 131-152, 2003.", ["Trabalho, Educação e Saúde", "131-152", "2003"]),
        ("journalArticle", "SILVA, Maria; COSTA, João. Inteligência artificial na educação. Revista Brasileira de Educação, Rio de Janeiro, v. 28, n. 2, p. 1-18, 2023.", ["Revista Brasileira de Educação", "2023"]),
        ("journalArticle", "PEREIRA, A. B. Ciência aberta: desafios atuais. Ciência da Informação, Brasília, DF, v. 52, n. 1, p. 22-38, jan./abr. 2023.", ["Ciência da Informação", "22-38"]),
        ("journalArticle", "HARRIS, Charles R. Array programming with NumPy. Nature, London, v. 585, n. 7825, p. 357-362, 2020. DOI: 10.1038/s41586-020-2649-2.", ["Nature", "10.1038/s41586-020-2649-2"]),
        ("journalArticle", "SANTOS, A. Educação inclusiva. Revista Educação Especial, Santa Maria, v. 35, p. e12, 2022.", ["Revista Educação Especial", "e12"]),
        ("journalArticle", "COSTA, João. Pesquisa qualitativa: fundamentos. Revista Pesquisa, Salvador, v. 10, supl. 2, p. 10-18, 2021.", ["Revista Pesquisa", "10-18"]),

        # Teses/dissertações/TCC
        ("thesis", "SILVA, Maria. Formação docente e tecnologias digitais. 2022. 180 f. Tese (Doutorado em Educação) - Universidade Federal do Ceará, Fortaleza, 2022.", ["Tese", "Universidade Federal do Ceará", "2022"]),
        ("thesis", "CASTELO BRANCO, Ana. Políticas públicas de saúde no Brasil. 2020. 140 f. Dissertação (Mestrado em Saúde Pública) - Universidade Federal do Ceará, Fortaleza, 2020.", ["Dissertação", "2020"]),
        ("thesis", "SOUZA, Pedro. Desenvolvimento de sistema web para pequenas empresas. 2021. 75 f. Trabalho de Conclusão de Curso (Bacharelado em Sistemas de Informação) - IFRN, Natal, 2021.", ["Trabalho de Conclusão", "2021"]),
        ("thesis", "ESPÍRITO SANTO, Carla. Educação ambiental e cidadania: estudo em escolas públicas. 2019. 120 f. Dissertação (Mestrado em Educação) - UFES, Vitória, 2019.", ["ESPÍRITO SANTO", "2019"]),

        # Anais
        ("proceedings", "SOUZA, João. Metodologias ativas no ensino fundamental. In: CONGRESSO BRASILEIRO DE EDUCAÇÃO, 3., 2019, Natal. Anais [...]. Natal: IFRN, 2019. p. 10-25.", ["CONGRESSO BRASILEIRO DE EDUCAÇÃO", "10-25"]),
        ("proceedings", "SILVA, Ana. Machine learning aplicado à saúde. In: SIMPÓSIO BRASILEIRO DE INFORMÁTICA, 12., 2022, Recife. Anais [...]. Recife: UFPE, 2022. p. 55-70.", ["SIMPÓSIO BRASILEIRO", "2022"]),
        ("proceedings", "LIMA, José. Sustentabilidade urbana. In: ENCONTRO NACIONAL DE ENGENHARIA, 8., 2021, Curitiba. Anais [...]. Curitiba: UTFPR, 2021. p. 1-12.", ["ENCONTRO NACIONAL", "1-12"]),

        # Legislação
        ("legislation", "BRASIL. Lei nº 11.892, de 29 de dezembro de 2008. Institui a Rede Federal de Educação Profissional. Brasília, DF: Presidência da República, 2008.", ["BRASIL", "11.892", "2008"]),
        ("legislation", "BRASIL. Decreto nº 9.057, de 25 de maio de 2017. Regulamenta a educação a distância. Brasília, DF: Presidência da República, 2017.", ["BRASIL", "2017"]),
        ("legislation", "BRASIL. Resolução nº 510, de 7 de abril de 2016. Dispõe sobre normas aplicáveis a pesquisas em Ciências Humanas. Brasília, DF: Conselho Nacional de Saúde, 2016.", ["BRASIL", "2016"]),
        ("legislation", "SÃO PAULO. Lei nº 17.293, de 15 de outubro de 2020. Estabelece medidas voltadas ao ajuste fiscal. São Paulo: Governo do Estado, 2020.", ["Lei", "2020"]),

        # Jornal
        ("newspaperArticle", "SILVA, Carlos. A inteligência artificial no mercado editorial. Folha de S.Paulo, São Paulo, 15 mar. 2022. Caderno Ilustrada, p. B2.", ["Folha de S.Paulo", "B2"]),
        ("newspaperArticle", "SOUZA, Ana. Universidade amplia bolsas de pesquisa. O Globo, Rio de Janeiro, 10 maio 2023. Educação, p. 12.", ["O Globo", "2023"]),
        ("newspaperArticle", "PEREIRA, João. Mercado de tecnologia cresce no país. Correio Braziliense, Brasília, DF, 5 fev. 2024. Economia, p. 8.", ["Correio Braziliense", "2024"]),

        # Websites
        ("website", "MINISTÉRIO DA EDUCAÇÃO. Reforma do ensino médio: perguntas e respostas. Portal MEC, Brasília, DF, 10 mar. 2022. Disponível em: https://gov.br/mec/reforma. Acesso em: 10 jan. 2023.", ["Portal MEC", "https://gov.br/mec/reforma", "10 jan. 2023"]),
        ("website", "ORGANIZAÇÃO MUNDIAL DA SAÚDE. Saúde mental. Genebra: OMS, 2023. Disponível em: https://www.who.int/health-topics/mental-health. Acesso em: 1 fev. 2024.", ["https://www.who.int", "2024"]),
        ("website", "INSTITUTO BRASILEIRO DE GEOGRAFIA E ESTATÍSTICA. Censo 2022. Rio de Janeiro: IBGE, 2023. Disponível em: https://www.ibge.gov.br/censo2022. Acesso em: 2 mar. 2024.", ["IBGE", "https://www.ibge.gov.br"]),
        ("website", "PYTHON SOFTWARE FOUNDATION. Python documentation. Disponível em: https://docs.python.org/3/. Acesso em: 15 set. 2026.", ["https://docs.python.org", "2026"]),

        # Patentes
        ("patent", "SOUZA, Marcos. Dispositivo de filtragem biológica. BR 10 2012 000000 0 A2. Depósito: 10 jan. 2012. Concessão: 15 out. 2019.", ["BR 10 2012 000000 0 A2", "2012"]),
        ("patent", "SILVA, João; COSTA, Ana; LIMA, Pedro. Sistema automatizado de irrigação. BR 10 2020 012345 6 A2. Depósito: 20 jun. 2020.", ["BR 10 2020 012345 6 A2", "2020"]),

        # Ruídos tipográficos / OCR razoáveis
        ("book", "ALMEIDA,João. Pesquisa científica: métodos e aplicações. São Paulo:Atlas, 2020.", ["ALMEIDA", "2020"]),
        ("book", "CASTELO BRANCO, Carlos. Gestão de projetos:uma abordagem prática. Fortaleza: Premius, 2021.", ["CASTELO BRANCO", "2021"]),
        ("journalArticle", "SILVA, Maria. Educação digital:novos desafios. Revista Educação, São Paulo, v.10,n.2,p.20-35,2022.", ["Revista Educação", "2022"]),
        ("chapter", "LIMA, Paulo. Formação docente. In: SOUZA, Ana (org.). Educação:teoria e prática. Recife:UFPE, 2020. p.30-45.", ["UFPE", "30-45"]),
        ("thesis", "SANTOS,Joana. Inclusão escolar e tecnologia. 2021. 130 f. Dissertação (Mestrado em Educação) - UFC,Fortaleza,2021.", ["Dissertação", "2021"]),
        ("website", "BRASIL. Ministério da Saúde. Vacinação. Portal Gov.br, Brasília, DF, 2024. Disponível em:https://www.gov.br/saude/vacinacao. Acesso em:5 jan. 2025.", ["gov.br", "2025"]),
    ]

    def test_extreme_cases(self):
        failures = []
        for idx, (expected_type, raw, expected_tokens) in enumerate(self.CASES, 1):
            with self.subTest(case=idx, expected_type=expected_type):
                try:
                    meta = parse_raw_citation_text(raw)
                    output = format_abnt(meta)
                    ok_type = meta.get("item_type") == expected_type
                    missing = [token for token in expected_tokens if token.lower() not in output.lower()]
                    if not ok_type or missing:
                        failures.append((idx, expected_type, meta.get("item_type"), missing, raw, output))
                except Exception as exc:
                    failures.append((idx, expected_type, "EXCEPTION", [repr(exc)], raw, ""))

        total = len(self.CASES)
        passed = total - len(failures)
        rate = passed / total * 100
        print(f"\nEXTREME_ABNT_SCORE={passed}/{total} ({rate:.2f}%)")
        for fail in failures:
            print("FAIL_CASE=", fail)
        self.assertGreaterEqual(rate, 90.0, f"Eficácia abaixo de 90%: {rate:.2f}%")


if __name__ == "__main__":
    unittest.main()
