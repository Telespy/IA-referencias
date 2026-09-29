import unittest
from unittest.mock import Mock, patch

from article_enrichment import _comparable
from correction import correct_reference
from formatters import format_abnt
from publication_places import normalize_place, _authority


class PlaceNormalizationTests(unittest.TestCase):
    def test_brasilia_country_is_removed_state_and_brackets_are_kept(self):
        place = normalize_place('[Brasilia, DF, Brasil]')
        self.assertEqual(place.value, '[Bras\u00edlia, DF]')
        self.assertFalse(place.warnings)
        self.assertEqual(place.details['original_value'], '[Brasilia, DF, Brasil]')
        self.assertTrue(place.details['qualification_required'])

    def test_general_city_cases_not_specific_to_a_journal(self):
        examples = {
            'Sao Paulo, SP, Brasil': 'S\u00e3o Paulo',
            '[Florianopolis, SC, Brazil]': '[Florian\u00f3polis]',
            'Recife, PE, Brasil': 'Recife',
            'Rio de Janeiro, RJ, Brazil': 'Rio de Janeiro',
            'Vicosa, Minas Gerais, Brasil': 'Vi\u00e7osa, MG',
            '[Vicosa, RN, Brazil]': '[Vi\u00e7osa, RN]',
            'Vicosa, AL, Brasil': 'Vi\u00e7osa, AL',
            'Toledo, PR, Brasil': 'Toledo, PR',
            'Toledo, MG, Brasil': 'Toledo, MG',
            'Santa Maria, RS, Brasil': 'Santa Maria, RS',
            'Santa Maria, RN, Brasil': 'Santa Maria, RN',
            'Brasilia (Distrito Federal), Brazil': 'Bras\u00edlia, DF',
            'Sao Paulo/SP, Brasil': 'S\u00e3o Paulo',
            'Vi\u00e7osa-MG': 'Vi\u00e7osa, MG',
            'N\u00e3o-Me-Toque, RS, Brasil': 'N\u00e3o-Me-Toque',
        }
        for original, expected in examples.items():
            with self.subTest(original=original):
                result = normalize_place(original)
                self.assertEqual(result.value, expected)
                self.assertFalse(result.warnings)

    def test_ambiguous_city_is_not_assigned_a_state_from_a_popularity_guess(self):
        for value in ('Vi\u00e7osa', '[Brasilia]', 'Santa Maria, Brasil', 'Toledo'):
            with self.subTest(value=value):
                result = normalize_place(value)
                self.assertEqual(result.value, value)
                self.assertIn('AMBIGUOUS_PLACE', [code for code, _ in result.warnings])

    def test_city_state_mismatch_and_historical_names_stay_for_review(self):
        for value in ('Brasilia, MG', 'Sao Paulo, RJ, Brasil', 'Cidade Antiga, SP, Brasil'):
            with self.subTest(value=value):
                result = normalize_place(value)
                self.assertEqual(result.value, value)
                self.assertTrue(result.warnings)

    def test_foreign_disambiguation_is_not_destroyed(self):
        for value in ('Cambridge, MA, USA', 'Cambridge, United Kingdom', 'Toledo, Espanha',
                      'London, UK', '[Coimbra, Portugal]', 'Paris, France'):
            with self.subTest(value=value):
                self.assertEqual(normalize_place(value).value, value)

    def test_contradictory_country_or_multiple_ufs_is_reported(self):
        for value in ('Sao Paulo, SP, USA', 'Brasilia, DF, MG, Brasil'):
            result = normalize_place(value)
            self.assertEqual(result.value, value)
            self.assertIn('PLACE_QUALIFIER_CONFLICT', [code for code, _ in result.warnings])

    def test_unknown_country_only_uncertain_and_multiple_places_are_not_invented(self):
        for value in ('', '[S. l.]', 'Brasil', 'New York; London', '[Sao Paulo?]', 'Cidade Antiga'):
            self.assertEqual(normalize_place(value).value, value)

    def test_no_state_is_added_to_a_bare_unambiguous_city(self):
        self.assertEqual(normalize_place('Recife').value, 'Recife')
        self.assertEqual(normalize_place('Sao Paulo').value, 'Sao Paulo')

    def test_missing_authority_preserves_original_and_signals_review(self):
        with patch('publication_places._authority', return_value=None):
            result = normalize_place('[Brasilia, DF, Brasil]')
        self.assertEqual(result.value, '[Brasilia, DF, Brasil]')
        self.assertEqual(result.warnings[0][0], 'PLACE_AUTHORITY_UNAVAILABLE')

    def test_idempotent_and_does_not_remove_inferred_brackets(self):
        for value in ('[Brasilia, DF, Brasil]', 'Sao Paulo, SP, Brasil', 'Vi\u00e7osa, MG, Brasil'):
            result = normalize_place(value)
            self.assertEqual(normalize_place(result.value).value, result.value)

    def test_equivalent_places_do_not_create_a_false_source_conflict(self):
        self.assertEqual(_comparable('city', '[Brasilia, DF, Brasil]'), _comparable('city', '[Bras\u00edlia, DF]'))
        self.assertEqual(_comparable('city', 'Sao Paulo'), _comparable('city', 'Sao Paulo, SP, Brasil'))
        self.assertNotEqual(_comparable('city', 'Vi\u00e7osa, MG'), _comparable('city', 'Vi\u00e7osa, RN'))

    def test_local_authority_has_distinct_municipalities_and_source_date(self):
        data, cities, _ = _authority()
        self.assertGreaterEqual(len(data['cities']), 5500)
        self.assertEqual(len({row[0] for row in data['cities']}), len(data['cities']))
        self.assertEqual({row['uf'] for row in cities['vicosa']}, {'AL', 'MG', 'RN'})
        self.assertTrue(data['retrieved_at'])


class PlacePipelineTests(unittest.TestCase):
    def book(self, city):
        return {'item_type': 'book', 'title': 'Livro de teste', 'year': '2020',
                'authors': [{'family': 'Silva', 'given': 'Maria'}], 'city': city,
                'publisher': 'Editora de teste', 'isbn': '9780451524935',
                '_source': {'name': 'Catalogo da edicao', 'url': 'https://example.org/edition'}}

    def correct(self, source):
        return correct_reference('9780451524935', online=True, fetch_book=lambda _: source,
                                 fetch_doi=Mock(), fetch_url=Mock(), search=Mock())

    def test_book_city_is_normalized_without_using_publishers_headquarters(self):
        result = self.correct(self.book('Sao Paulo, SP, Brasil'))
        self.assertIn('S\u00e3o Paulo: Editora de teste', result['abnt'])
        self.assertNotIn('Bras', result['abnt'])
        self.assertEqual(result['provenance']['city']['source'], 'Catalogo da edicao')
        self.assertEqual(result['provenance']['city']['normalization']['original_value'], 'Sao Paulo, SP, Brasil')
        self.assertTrue(result['approved'])
        self.assertTrue(any(c['field'] == 'city' for c in result['corrections']))

    def test_ambiguous_catalog_city_cannot_be_approved(self):
        result = self.correct(self.book('Vi\u00e7osa'))
        self.assertFalse(result['approved'])
        self.assertFalse(result['provenance']['city']['verified'])
        self.assertIn('AMBIGUOUS_PLACE', [issue['code'] for issue in result['issues']])

    def test_city_is_not_filled_when_publisher_is_known(self):
        source = self.book('')
        source['publisher'] = 'Editora da Universidade de S\u00e3o Paulo'
        result = self.correct(source)
        self.assertFalse(result['meta'].get('city'))
        self.assertIn('[S. l.]', result['abnt'])

    def test_offline_normalization_is_not_bibliographic_verification(self):
        meta = self.book('Vicosa, Minas Gerais, Brasil')
        with patch('correction.parse_raw_citation_text', return_value=meta), patch('sources.requests.get') as request:
            result = correct_reference('Livro de teste', online=False, fetch_doi=Mock(), fetch_book=Mock(), fetch_url=Mock(), search=Mock())
        request.assert_not_called()
        self.assertEqual(result['meta']['city'], 'Vi\u00e7osa, MG')
        self.assertFalse(result['approved'])
        self.assertFalse(result['provenance']['city']['verified'])

    def test_standalone_formatter_uses_same_rule_for_several_document_types(self):
        for kind in ('book', 'journalArticle', 'thesis', 'website', 'proceedings'):
            with self.subTest(kind=kind):
                meta = dict(self.book('[Brasilia, DF, Brasil]'), item_type=kind,
                            journal='Periodico Teste', institution='Instituicao Teste')
                text = format_abnt(meta)
                self.assertIn('[Bras\u00edlia, DF]', text)
                self.assertNotIn(', Brasil]', text)


if __name__ == '__main__':
    unittest.main()
