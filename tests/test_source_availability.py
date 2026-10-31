import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from source_availability import reference,make_check,applies,run

class CloudChecks(unittest.TestCase):
    def work(self,**kwargs):
        value={'slug':'example','en':'Example','kind':'series','seasonNumber':2,'artworkSeasonNumber':2,'releaseDate':'2026-01-01','seasons':[{'season':2,'year':'2026','releaseDate':'2026-01-01'}],'genres':[],
               'zh':{'metadataPolicy':'mainland-v1','name_status':'verified_title_sources','title':'豆瓣名称','aliases':[],'_identityYear':2024}}
        value.update(kwargs);return value
    def test_check_scoped_to_exact_work_kind_year_and_season(self):
        work=self.work();ref=reference(work);self.assertEqual(ref['year'],'2026');check=make_check(work,ref,{'routes':2},1793440000)
        self.assertTrue(applies(check,work))
        for kwargs in ({'en':'Other'},{'kind':'movie'},{'artworkSeasonNumber':3},{'artworkSeasonYear':'2025'}):self.assertFalse(applies(check,self.work(**kwargs)))
    def test_unknown_later_season_year_is_not_guessed_from_first_season(self):
        work=self.work(seasons=[],seasonNumber=3,releaseDate='2027-01-01');self.assertEqual(reference(work)['year'],'')
    def test_scheduled_checks_reuse_results_and_keep_animation_douban_name(self):
        for animated in (True,False):
            with self.subTest(animated=animated),tempfile.TemporaryDirectory()as folder:
                root=Path(folder);(root/'docs/home').mkdir(parents=True);(root/'data').mkdir();work=self.work(genres=['Animation']if animated else [])
                for file,data in [('docs/catalog.json',{'entries':[work]}),('docs/home/home.json',{'works':[]}),('docs/version.json',{})]:(root/file).write_text(json.dumps(data),encoding='utf8')
                probe=Mock(return_value=({'title':'片源名称第二季','routes':2,'provider':'hn'},[]))
                with patch('source_availability.publish')as publish,patch('mainland_names.republish_home'):
                    result=run(root,probe=probe,now=1793440000);saved=publish.call_args.args[0]['entries'][0]
                    self.assertEqual(saved['zh']['title'],'豆瓣名称'if animated else'片源名称');self.assertTrue(saved['zh']['sourceCheck']['found']);self.assertEqual(saved['zh']['sourceCheck']['season'],2)
                    public=json.dumps(saved['zh']['sourceCheck']);self.assertNotIn('hn',public);self.assertNotIn('playUrl',public)
                    # Replay the resulting publication: no second source query on the next scheduled run.
                    (root/'docs/catalog.json').write_text(json.dumps({'entries':[saved]}),encoding='utf8');run(root,probe=probe,now=1793440100);self.assertEqual(probe.call_count,1)
    def test_future_work_does_not_query_sources(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);(root/'docs/home').mkdir(parents=True);(root/'data').mkdir();work=self.work(releaseDate='2027-01-01',seasons=[{'season':2,'year':'2027','releaseDate':'2027-01-01'}])
            for file,data in [('docs/catalog.json',{'entries':[work]}),('docs/home/home.json',{'works':[]}),('docs/version.json',{})]:(root/file).write_text(json.dumps(data),encoding='utf8')
            probe=Mock();run(root,probe=probe,now=1793440000);probe.assert_not_called()
