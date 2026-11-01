import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from mainland_names import run
from pending_name_review import review

class NameOnlyReview(unittest.TestCase):
    def setup_root(self,root,entries):
        for folder in ['docs/home','data','logs']:(root/folder).mkdir(parents=True,exist_ok=True)
        for filename,value in [('docs/catalog.json',{'entries':entries}),('docs/home/home.json',{'works':[]}),('docs/version.json',{})]:
            (root/filename).write_text(json.dumps(value),encoding='utf8')
    def test_names_only_never_queries_or_writes_negative_source_check(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);self.setup_root(root,[{'slug':'test','en':'Test','kind':'movie','year':'2020','releaseDate':'2020-01-01'}])
            client=Mock(events=[]);probe=Mock(side_effect=AssertionError('source probing forbidden'))
            verified={'display_name_zh':'测试电影','aliases_zh':[],'sources':[{'url':'https://movie.douban.com/subject/12345678/'}]}
            with patch('mainland_names.DoubanMobile')as mobile,patch('mainland_names.publish'),patch('mainland_names.republish_home'):
                mobile.return_value.lookup.return_value=verified
                report=run(root,limit=1,force=True,client=client,lookup=Mock(),probe=probe,names_only=True)
            probe.assert_not_called();client.search.assert_not_called()
            self.assertEqual(report['records'][0]['sourcePolicy'],'not_checked_name_review')
            self.assertNotIn('sourceCheck',json.loads((root/'docs/catalog.json').read_text())['entries'][0].get('zh',{}))
    def test_review_reports_network_and_future_separately_without_using_hint_as_approval(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp)
            rows=[{'slug':'to-mom-and-dad-with-love','en':'To Mom (And Dad), With Love','kind':'movie','year':'2022','releaseDate':'2022-05-06'}, {'slug':'future','en':'Future','kind':'movie','year':'2099','releaseDate':'2099-01-01'}]
            self.setup_root(root,rows)
            with patch('pending_name_review.run',return_value={'records':[{'slug':rows[0]['slug'],'confidence':'UNVERIFIED','verificationEvents':[{'host':'movie.douban.com','status':418}]}]})as work:
                result=review(root)
            self.assertEqual(result['summary'],{'future_release':1,'network_incomplete':1})
            self.assertTrue(work.call_args.kwargs['names_only']);self.assertEqual(work.call_count,1)
            self.assertNotIn('title',result['records'][0]['result'])
            self.assertTrue((root/'docs/pending-name-review.md').exists())
    def test_original_movie_year_override_requires_exact_known_official_identity(self):
        for official in ['umc.cmc.known','umc.cmc.wrong']:
            with self.subTest(official=official),tempfile.TemporaryDirectory()as tmp:
                root=Path(tmp);self.setup_root(root,[{'slug':'test','en':'Exact Title','kind':'movie','officialId':official,'year':'2021','releaseDate':'2021-06-22'}])
                hint={'englishTitle':'Exact Title','officialId':'umc.cmc.known','expectedPlatformYear':'2021','releaseYear':'2019','releaseYearEvidence':'https://www.imdb.com/title/tt10238966/','policy':'verified_original_movie_year_not_platform_date'}
                (root/'data/name-search-hints.json').write_text(json.dumps({'works':{'test':hint}}),encoding='utf8')
                client=Mock(events=[]);client.search.return_value=([],'ok');lookup=Mock();lookup.pages.events=[]
                with patch('mainland_names.DoubanMobile')as mobile:
                    mobile.return_value.lookup.return_value=None
                    run(root,limit=1,force=True,client=client,lookup=lookup,names_only=True)
                self.assertEqual(mobile.return_value.lookup.call_args.args[0]['year'],'2019'if official=='umc.cmc.known'else'2021')
