import copy
from datetime import date, datetime, timezone
import unittest
from unittest.mock import Mock, patch
import requests

from article_enrichment import enrich_article, _jats_metadata, _catalog_location, _period, _xml
from correction import correct_reference, correction_today, reference_report
from sources import LookupFailure, _crossref_metadata, _get, normalize_pages


DOI = '10.36416/1806-3756/e20200590'
TITLE = 'ELMO 1.0: a helmet interface for CPAP and high-flow oxygen delivery'
BASE = {'item_type': 'journalArticle', 'doi': DOI, 'title': TITLE, 'year': '2021',
        'authors': [{'given': 'Marcelo', 'family': 'Alcantara Holanda'}],
        'journal': 'Jornal Brasileiro de Pneumologia', 'page': 'e20200590',
        'url': 'https://example.org/article',
        '_warnings': ['Marcadores de afiliacao removidos da autoria; confira a grafia na publicacao.'],
        '_source': {'name': 'Crossref', 'url': 'https://api.crossref.org/works/example'}}
CORE = {'doi': DOI, 'pmcid': 'PMC8332729', 'title': TITLE, 'language': 'eng',
        'authorList': {'author': [{'firstName': 'Marcelo Alcantara', 'lastName': 'Holanda'}]},
        'pageInfo': 'e20200590',
        'journalInfo': {'volume': '47', 'issue': '3', 'yearOfPublication': 2021, 'monthOfPublication': 5,
                        'journal': {'nlmid': '101222274', 'issn': '1806-3713', 'essn': '1806-3756'}}}
# Compact fixtures transcribe the relevant structured source fields, not a DOI lookup table.
JATS = f'''<article xml:lang="en"><front><journal-meta><journal-title-group>
<journal-title>Jornal Brasileiro de Pneumologia</journal-title></journal-title-group>
<publisher><publisher-name>SBPT</publisher-name></publisher></journal-meta><article-meta>
<article-id pub-id-type="doi">{DOI}</article-id><title-group><article-title>{TITLE}</article-title></title-group>
<contrib-group><contrib contrib-type="author"><name><surname>Holanda</surname>
<given-names>Marcelo Alcantara</given-names></name><xref ref-type="aff"><sup>1</sup></xref></contrib></contrib-group>
<aff>University in Fortaleza, Brazil</aff><pub-date pub-type="epub"><day>31</day><month>5</month><year>2021</year></pub-date>
<pub-date pub-type="ppub"><season>May-Jun</season><year>2021</year></pub-date>
<volume>47</volume><issue>3</issue><elocation-id>e20200590</elocation-id></article-meta></front></article>'''
CATALOG = '''<NLMCatalogRecordSet><NLMCatalogRecord><NlmUniqueID>101222274</NlmUniqueID>
<PublicationInfo><PublicationFirstYear>2004</PublicationFirstYear><PublicationEndYear>2025</PublicationEndYear>
<Imprint FunctionType="Publication"><Place>Brasilia, DF, Brasil :</Place></Imprint></PublicationInfo>
<ISSN IssnType="Electronic">1806-3756</ISSN></NLMCatalogRecord></NLMCatalogRecordSet>'''


def xml_response(value):
    return Mock(content=value.encode())


def corrected(meta, raw=DOI, online=True):
    return correct_reference(raw, online=online, fetch_doi=lambda _: meta, fetch_book=Mock(),
                             search=lambda _: [], fetch_url=Mock())


class EnrichmentTests(unittest.TestCase):
    def enrich(self, base=None, core=None, jats=JATS, catalog=CATALOG):
        record = copy.deepcopy(core if core is not None else CORE)
        with patch('article_enrichment._json', return_value={'resultList': {'result': [record]}}), \
                patch('article_enrichment._get', side_effect=[xml_response(jats), xml_response(catalog)]), \
                patch('article_enrichment.time.sleep'):
            return enrich_article(base or BASE)

    def test_completes_article_with_exact_per_field_sources(self):
        result = self.enrich()
        self.assertEqual((result['volume'], result['issue'], result['start_month'], result['end_month']), ('47', '3', 5, 6))
        self.assertEqual(result['authors'][0], {'family': 'Holanda', 'given': 'Marcelo Alcantara'})
        self.assertEqual(result['city'], '[Brasilia, DF, Brasil]')
        self.assertEqual(result['_warnings'], [])
        self.assertEqual(result['_field_sources']['volume']['name'], 'PMC (XML do artigo)')
        self.assertEqual(result['_field_sources']['city']['name'], 'NLM Catalog')
        self.assertEqual(result['_field_sources']['url']['name'], 'Crossref')
        self.assertEqual(len(result['_sources']), 4)
        output = corrected(result)
        self.assertEqual(output['meta']['city'], '[Bras\u00edlia, DF]')
        self.assertIn('[Bras\u00edlia, DF],', output['abnt'])
        self.assertNotIn(', Brasil]', output['abnt'])
        self.assertEqual(output['provenance']['city']['normalization']['original_value'], '[Brasilia, DF, Brasil]')
        self.assertIn('v. 47, n. 3, e20200590, May/June 2021', output['abnt'])
        self.assertIn('(2021).', output['apa'])
        self.assertNotIn('May/June', output['apa'])
        self.assertTrue(output['approved'])
        self.assertEqual(output['provenance']['end_month']['source'], 'PMC (XML do artigo)')
        self.assertTrue(BASE['_warnings'])
        self.assertNotIn('volume', BASE)

    def test_different_doi_from_search_is_never_merged(self):
        core = dict(CORE, doi='10.1234/another')
        result = self.enrich(core=core)
        self.assertNotIn('volume', result)
        self.assertNotIn('city', result)

    def test_same_doi_with_unrelated_title_is_rejected(self):
        result = self.enrich(core=dict(CORE, title='Entirely different work'))
        self.assertNotIn('volume', result)
        self.assertIn('SOURCE_IDENTITY_CONFLICT', [i['code'] for i in result['_issues']])

    def test_jats_must_match_both_doi_and_title(self):
        for xml in (JATS.replace(DOI, '10.1234/other'), JATS.replace(TITLE, 'Unrelated title')):
            result = self.enrich(jats=xml)
            self.assertEqual(result['volume'], '47')
            self.assertNotIn('end_month', result)
            self.assertIn('SOURCE_IDENTITY_CONFLICT', [i['code'] for i in result['_issues']])

    def test_source_conflict_keeps_value_and_blocks_approval(self):
        result = self.enrich(base=dict(BASE, volume='99'))
        self.assertEqual(result['volume'], '99')
        report = corrected(result)
        self.assertFalse(report['approved'])
        self.assertFalse(report['provenance']['volume']['verified'])
        self.assertTrue(report['provenance']['volume']['conflicted'])

    def test_explicit_issue_period_resolves_online_month_difference(self):
        output = corrected(self.enrich(base=dict(BASE, start_month=6)))
        self.assertTrue(output['approved'])
        self.assertTrue(output['provenance']['start_month']['verified'])
        self.assertEqual(output['meta']['start_month'], 5)
        conflicts = [i for i in output['issues'] if i['code'] == 'SOURCE_CONFLICT']
        self.assertTrue(conflicts)
        self.assertTrue(all(i.get('resolved') for i in conflicts))
        self.assertIn('Usado o periodo explicito do fasciculo', reference_report(output))
        self.assertNotIn("'family':", reference_report(output))

    def test_verified_period_replaces_stale_parsed_month(self):
        parsed = {'doi': DOI, 'item_type': 'journalArticle', 'month_str': 'Dec.', 'day': 31, 'end_month': 12}
        with patch('correction.parse_raw_citation_text', return_value=parsed):
            result = corrected(self.enrich())
        self.assertIn('May/June 2021', result['abnt'])
        self.assertNotIn('month_str', result['meta'])
        self.assertNotIn('day', result['meta'])
        self.assertTrue(any(c['field'] == 'month_str' and c['after'] is None for c in result['corrections']))

    def test_electronic_only_date_does_not_resolve_an_issue_month_conflict(self):
        xml = JATS.replace('<pub-date pub-type="ppub"><season>May-Jun</season><year>2021</year></pub-date>', '')
        result = corrected(self.enrich(base=dict(BASE, start_month=6), jats=xml))
        self.assertFalse(result['approved'])
        self.assertEqual(result['meta']['start_month'], 6)

    def test_localizer_with_identical_endpoints_is_not_a_conflict(self):
        self.assertEqual(normalize_pages('e20200282-e20200282'), 'e20200282')
        self.assertEqual(normalize_pages('34-39'), '34-39')
        self.assertEqual(normalize_pages('13-13'), '13')

    def test_authors_are_not_silently_changed_to_different_people(self):
        core = copy.deepcopy(CORE)
        core['authorList']['author'][0]['firstName'] = 'Manuel'
        report = corrected(self.enrich(core=core))
        self.assertFalse(report['approved'])
        self.assertIn('SOURCE_CONFLICT', [i['code'] for i in report['issues']])

    def test_secondary_service_failure_keeps_crossref_record(self):
        with patch('article_enrichment._json', side_effect=LookupFailure('unavailable')):
            result = enrich_article(BASE)
        self.assertEqual(result['title'], TITLE)
        self.assertIn('ENRICHMENT_UNAVAILABLE', [i['code'] for i in result['_issues']])

    def test_malformed_secondary_json_keeps_previous_metadata(self):
        with patch('article_enrichment._json', return_value={'resultList': None}):
            self.assertEqual(enrich_article(BASE)['title'], TITLE)

    def test_fulltext_failure_keeps_core_and_catalog(self):
        with patch('article_enrichment._json', return_value={'resultList': {'result': [CORE]}}), \
                patch('article_enrichment._get', side_effect=[LookupFailure('403'), xml_response(CATALOG)]), \
                patch('article_enrichment.time.sleep'):
            result = enrich_article(BASE)
        self.assertEqual(result['volume'], '47')
        self.assertIn('city', result)
        self.assertNotIn('end_month', result)
        self.assertFalse(corrected(result)['approved'])

    def test_duplicate_records_are_ambiguous(self):
        with patch('article_enrichment._json', return_value={'resultList': {'result': [CORE, CORE]}}):
            result = enrich_article(BASE)
        self.assertIn('AMBIGUOUS_SOURCE', [i['code'] for i in result['_issues']])

    def test_identifiers_cannot_be_used_to_fetch_arbitrary_urls(self):
        core = dict(CORE, pmcid='../../private')
        core['journalInfo'] = dict(CORE['journalInfo'], journal={'nlmid': 'https://localhost/private'})
        with patch('article_enrichment._json', return_value={'resultList': {'result': [core]}}), \
                patch('article_enrichment._get') as request:
            enrich_article(BASE)
        request.assert_not_called()

    def test_xml_does_not_read_external_entities(self):
        xml = '<!DOCTYPE article [<!ENTITY x SYSTEM "file:///etc/passwd">]><article>&x;</article>'
        with self.assertRaises(LookupFailure):
            _xml(xml_response(xml))

    def test_month_period_comes_from_issue_not_publication_day(self):
        meta = _jats_metadata(_xml(xml_response(JATS)), 'https://example.org/xml')
        self.assertEqual((meta['start_month'], meta['end_month']), (5, 6))
        self.assertNotIn('day', meta)
        self.assertFalse(meta['city'])
        self.assertEqual(_period('11-12'), {'start_month': 11, 'end_month': 12})
        self.assertEqual(_period('31'), {})
        self.assertEqual(_period('junk'), {})
        self.assertEqual(_period('Spring'), {})
        crossref = _crossref_metadata({'title': ['Example article'], 'published-print': {'date-parts': [[2021, 5, 31]]}})
        self.assertEqual(crossref['start_month'], 5)
        self.assertNotIn('end_month', crossref)

    def test_parser_is_not_tied_to_elmo(self):
        xml = JATS.replace(DOI, '10.1234/other').replace(TITLE, 'Another journal article')
        xml = xml.replace('<volume>47', '<volume>12').replace('May-Jun', 'September-October')
        meta = _jats_metadata(_xml(xml_response(xml)), 'https://example.org/other')
        self.assertEqual((meta['volume'], meta['start_month'], meta['end_month']), ('12', 9, 10))
        self.assertEqual(meta['doi'], '10.1234/other')

    def test_official_translated_title_can_identify_the_same_article(self):
        xml = JATS.replace('xml:lang="en"', 'xml:lang="pt"').replace(TITLE, 'Titulo em portugues')
        xml = xml.replace('</title-group>', f'<trans-title-group xml:lang="en"><trans-title>{TITLE}</trans-title></trans-title-group></title-group>')
        meta = _jats_metadata(_xml(xml_response(xml)), 'https://example.org/xml', TITLE)
        self.assertEqual(meta['title'], TITLE)
        self.assertEqual(meta['language'], 'en')

    def test_author_role_can_be_declared_on_group_without_including_editors(self):
        xml = JATS.replace('<contrib-group>', '<contrib-group content-type="author">')
        xml = xml.replace('<contrib contrib-type="author">', '<contrib>')
        xml = xml.replace('</contrib-group>', '<contrib contrib-type="editor"><name><surname>Editor</surname></name></contrib></contrib-group>')
        meta = _jats_metadata(_xml(xml_response(xml)), 'xml')
        self.assertEqual(meta['authors'], [{'family': 'Holanda', 'given': 'Marcelo Alcantara'}])

    def test_catalog_location_requires_identity_and_year(self):
        root = _xml(xml_response(CATALOG))
        for nlmid, issns, year in [('999999999', ['1806-3756'], '2021'),
                                    ('101222274', ['9999-9999'], '2021'),
                                    ('101222274', ['1806-3756'], '1999'),
                                    ('101222274', ['1806-3756'], '2026')]:
            self.assertEqual(_catalog_location(root, nlmid, issns, year, 'catalog'), {})

    def test_catalog_with_historical_moves_is_not_guessed(self):
        xml = CATALOG.replace('</PublicationInfo>', '<Imprint FunctionType="Publication"><Place>Elsewhere :</Place></Imprint></PublicationInfo>')
        root = _xml(xml_response(xml))
        self.assertEqual(_catalog_location(root, '101222274', ['1806-3756'], '2021', 'catalog'), {})

    def test_catalog_dated_move_supports_historical_place(self):
        xml = CATALOG.replace('<Imprint FunctionType="Publication"><Place>Brasilia, DF, Brasil :</Place></Imprint>',
            '<Imprint ImprintType="Original" FunctionType="Publication"><Place>New York, NY :</Place></Imprint>'
            '<Imprint ImprintType="Current" FunctionType="Publication"><Place>Oxford :</Place><ImprintFull>2026- : Oxford : Oxford University Press</ImprintFull></Imprint>')
        root = _xml(xml_response(xml.replace('<PublicationEndYear>2025</PublicationEndYear>', '<PublicationEndYear>9999</PublicationEndYear>')))
        self.assertEqual(_catalog_location(root, '101222274', ['1806-3756'], '2017', 'catalog')['city'], '[New York, NY]')
        self.assertEqual(_catalog_location(root, '101222274', ['1806-3756'], '2026', 'catalog')['city'], '[Oxford]')

    def test_crossref_issn_finds_catalog_when_europe_pmc_is_unavailable(self):
        base = dict(BASE, volume='195', issue='4', page='438-442', start_month=2, year='2017',
                    _issns=['1073-449X'])
        xml = CATALOG.replace('101222274', '9421642').replace('1806-3756', '1073-449X')
        with patch('article_enrichment._json', side_effect=[LookupFailure('offline'),
                 {'esearchresult': {'count': '1', 'idlist': ['9421642']}}]), \
                patch('article_enrichment._get', return_value=xml_response(xml)), \
                patch('article_enrichment.time.sleep'):
            result = enrich_article(base)
        self.assertEqual(result['city'], '[Brasilia, DF, Brasil]')
        outage = next(i for i in result['_issues'] if i['code'] == 'ENRICHMENT_UNAVAILABLE')
        self.assertEqual(outage['severity'], 'info')

    def test_non_article_never_calls_supplemental_services(self):
        with patch('article_enrichment._json') as request:
            self.assertEqual(enrich_article({'item_type': 'book'}), {'item_type': 'book'})
        request.assert_not_called()


class AccessDateTests(unittest.TestCase):
    def test_missing_date_uses_correction_day_and_labels_generated_value(self):
        with patch('correction.correction_today', return_value=date(2026, 9, 28)):
            output = corrected(BASE)
        self.assertEqual(output['meta']['access_date'], '28 set. 2026')
        self.assertTrue(output['provenance']['access_date']['generated'])
        self.assertFalse(output['provenance']['access_date']['verified'])
        self.assertIn('Acesso em: 28 set. 2026.', output['abnt'])

    def test_date_also_appears_when_only_doi_is_available(self):
        meta = dict(BASE, url='')
        output = corrected(meta)
        self.assertIn('Acesso em:', output['abnt'])
        output = corrected(dict(BASE, url='https://doi.org/' + DOI))
        self.assertEqual(output['abnt'].count('Acesso em:'), 1)

    def test_supplied_date_is_preserved(self):
        output = corrected(BASE, DOI + '. Acesso em: 12 set. 2026.')
        self.assertEqual(output['meta']['access_date'], '12 set. 2026')
        self.assertNotIn('generated', output['provenance']['access_date'])

    def test_offline_or_failed_lookup_does_not_fabricate_access(self):
        self.assertFalse(corrected(BASE, online=False)['meta'].get('access_date'))
        self.assertFalse(corrected({})['meta'].get('access_date'))

    def test_clock_respects_brazil_midnight_not_docker_utc_date(self):
        instant = datetime(2026, 9, 29, 1, 30, tzinfo=timezone.utc)
        with patch('correction.datetime') as clock:
            clock.now.side_effect = lambda zone: instant.astimezone(zone)
            self.assertEqual(correction_today(), date(2026, 9, 28))


class SourceRetryTests(unittest.TestCase):
    def test_temporary_read_failure_has_one_retry(self):
        response = Mock(status_code=200, content=b'{}')
        with patch('sources.requests.get', side_effect=[requests.Timeout(), response]) as request, patch('sources.time.sleep'):
            self.assertIs(_get('https://example.org'), response)
        self.assertEqual(request.call_count, 2)

    def test_http_transient_failure_and_retry_after(self):
        busy = Mock(status_code=503, headers={})
        response = Mock(status_code=200, content=b'{}')
        with patch('sources.requests.get', side_effect=[busy, response]) as request, patch('sources.time.sleep'):
            self.assertIs(_get('https://example.org'), response)
        self.assertEqual(request.call_count, 2)
        busy = Mock(status_code=429, headers={'Retry-After': '60'})
        busy.raise_for_status.side_effect = requests.HTTPError()
        with patch('sources.requests.get', return_value=busy) as request:
            with self.assertRaises(LookupFailure):
                _get('https://example.org')
        request.assert_called_once()

    def test_retry_is_bounded_and_certificate_failures_are_not_retried(self):
        with patch('sources.requests.get', side_effect=requests.Timeout()) as request, patch('sources.time.sleep'):
            with self.assertRaises(LookupFailure):
                _get('https://example.org')
        self.assertEqual(request.call_count, 2)
        with patch('sources.requests.get', side_effect=requests.exceptions.SSLError()) as request:
            with self.assertRaises(LookupFailure):
                _get('https://example.org')
        request.assert_called_once()


if __name__ == '__main__':
    unittest.main()
