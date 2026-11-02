import copy,unittest
from douban_mobile import verify_payload
from release_identity import regional_date,page_dates,subject_with_dates
NOW='2026-11-02T00:00:00+00:00'
REF={'english_title':'12 Monkeys','year':'1996','kind':'movie','release_date':'1996-01-05','release_region':'US'}
DATA={'id':'1298744','title':'十二猴子','original_title':'Twelve Monkeys','year':'1995','type':'movie','pubdate':['1995-12-08(纽约首映)','1996-01-05(美国)'],'rating':{'value':8.2}}
class ReleaseIdentity(unittest.TestCase):
    def verify(self,ref=None,data=None):return verify_payload(ref or REF,data or DATA,'1298744','movie',NOW)
    def test_numeric_spelling_and_different_first_year_match_exact_us_date(self):
        p=self.verify();self.assertEqual(p['display_name_zh'],'十二猴子');self.assertEqual(p['release_year'],1995);self.assertEqual(p['detailMetadata']['year'],1995);self.assertEqual(p['release_date_evidence']['platformReleaseDate'],'1996-01-05')
    def test_year_neighbour_without_exact_regional_date_does_not_pass(self):
        for dates in [[],['1996-01-06(美国)'],['1996-01-05(英国)'],['1996-01-05(纽约首映)'],['1996-02-30(美国)']]:
            self.assertIsNone(self.verify(data=dict(DATA,pubdate=dates)))
    def test_different_work_id_imdb_type_or_season_is_not_relaxed(self):
        for ref in [dict(REF,douban_id='1234567'),dict(REF,english_title='12 Monkeys 2'),dict(REF,kind='tv',season=2),dict(REF,release_region='GB')]:self.assertIsNone(self.verify(ref=ref))
        self.assertIsNone(self.verify(ref=dict(REF,imdb_id='tt0114746'),data=dict(DATA,imdb_id='tt9999999')))
    def test_numeric_spelling_alone_is_not_identity_evidence(self):
        self.assertIsNone(self.verify(ref={'english_title':'12 Monkeys','year':'1995','kind':'movie'}))
    def test_full_page_dates_must_be_from_same_canonical_subject(self):
        raw='<meta property="og:url" content="https://movie.douban.com/subject/1298744/"><span property="v:initialReleaseDate" content="1996-01-05">1996-01-05(美国)</span><div>2000-01-01(美国)</div>'
        self.assertEqual(page_dates(raw,'1298744'),['1996-01-05(美国)']);self.assertEqual(page_dates(raw,'1234567'),[])
    def test_truncated_payload_supplement_is_bound_to_subject_and_first_date(self):
        e={'subjectId':'1298744','sourceUrl':'https://movie.douban.com/subject/1298744/','confirmedBy':'user','originalTitle':'Twelve Monkeys','originalYear':'1995','officialReleaseDate':'1996-01-05','dates':DATA['pubdate']}
        truncated=dict(DATA,pubdate=DATA['pubdate'][:1]);ref=dict(REF,release_date_evidence=e)
        class NoPages:pass
        out=subject_with_dates(ref,truncated,'1298744',NoPages());self.assertTrue(regional_date(ref,out['_full_pubdate']));self.assertIsNotNone(self.verify(ref,out))
        for change in [{'original_title':'Different'},{'year':'2000'},{'pubdate':['1995-12-09(纽约首映)']}]:
            out=subject_with_dates(ref,dict(truncated,**change),'1298744',NoPages());self.assertFalse(regional_date(ref,out['_full_pubdate']))
