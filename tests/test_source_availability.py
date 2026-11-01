import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from source_availability import reference,make_check,applies,run,apply_cached,sync_home_zh

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
    def test_scheduled_checks_reuse_results_and_use_cloud_selected_name(self):
        for animated in (True,False):
            with self.subTest(animated=animated),tempfile.TemporaryDirectory()as folder:
                root=Path(folder);(root/'docs/home').mkdir(parents=True);(root/'data').mkdir();work=self.work(genres=['Animation']if animated else [])
                for file,data in [('docs/catalog.json',{'entries':[work]}),('docs/home/home.json',{'works':[]}),('docs/version.json',{})]:(root/file).write_text(json.dumps(data),encoding='utf8')
                probe=Mock(return_value=({'title':'片源名称第二季','routes':2,'provider':'hn'},[]))
                with patch('source_availability.publish')as publish,patch('mainland_names.republish_home'):
                    result=run(root,probe=probe,now=1793440000);saved=publish.call_args.args[0]['entries'][0]
                    self.assertEqual(saved['zh']['title'],'片源名称');self.assertTrue(saved['zh']['sourceCheck']['found']);self.assertEqual(saved['zh']['sourceCheck']['season'],2)
                    public=json.dumps(saved['zh']['sourceCheck']);self.assertNotIn('hn',public);self.assertNotIn('playUrl',public)
                    # Replay the resulting publication: no second source query on the next scheduled run.
                    (root/'docs/catalog.json').write_text(json.dumps({'entries':[saved]}),encoding='utf8');run(root,probe=probe,now=1793440100);self.assertEqual(probe.call_count,1)
    def test_future_work_does_not_query_sources(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);(root/'docs/home').mkdir(parents=True);(root/'data').mkdir();work=self.work(releaseDate='2027-01-01',seasons=[{'season':2,'year':'2027','releaseDate':'2027-01-01'}])
            for file,data in [('docs/catalog.json',{'entries':[work]}),('docs/home/home.json',{'works':[]}),('docs/version.json',{})]:(root/file).write_text(json.dumps(data),encoding='utf8')
            probe=Mock();run(root,probe=probe,now=1793440000);probe.assert_not_called()
    def test_recall_only_result_preserves_reviewed_title_and_evidence_status(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);work=self.work();work['zh'].pop('name_status');work['zh']['provenance']='reviewed_mainland_catalog';self.fixture(root,[work])
            probe=Mock(return_value=({'title':'片库别名','routes':2,'libraries':1,'recallOnly':True,'complete':False},[]))
            with patch('source_availability.publish')as publish,patch('mainland_names.republish_home'):
                result=run(root,probe=probe,now=1793440000);zh=publish.call_args.args[0]['entries'][0]['zh']
            self.assertEqual(zh['title'],'豆瓣名称');self.assertNotIn('name_status',zh);self.assertNotIn('name_sources',zh);self.assertNotIn('nameSelection',zh);self.assertTrue(zh['sourceCheck']['found'])
            record=json.loads((root/'data/cloud-source-cache.json').read_text())['records']['example'];self.assertEqual(record['nextRetry']-record['checkedAt'],3600);self.assertTrue(result['records'][0]['recallOnly'])
    def test_old_negative_check_is_retried_with_season_query_policy(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);(root/'docs/home').mkdir(parents=True);(root/'data').mkdir();work=self.work();now=1793440000
            work['zh']['sourceCheck']=make_check(work,reference(work),None,now-10)
            for file,data in [('docs/catalog.json',{'entries':[work]}),('docs/home/home.json',{'works':[]}),('docs/version.json',{}),('data/cloud-source-cache.json',{'records':{'example':{'checkedAt':now-10,'nextRetry':now+86400,'check':work['zh']['sourceCheck'],'fingerprint':'legacy'}}})]:(root/file).write_text(json.dumps(data),encoding='utf8')
            probe=Mock(return_value=({'title':'豆瓣名称第二季','routes':2},[]))
            with patch('source_availability.publish'),patch('mainland_names.republish_home'):run(root,probe=probe,now=now)
            probe.assert_called_once()

    def fixture(self,root,works,cache=None):
        (root/'docs/home').mkdir(parents=True);(root/'data').mkdir()
        for file,data in [('docs/catalog.json',{'entries':works}),('docs/home/home.json',{'works':[]}),('docs/version.json',{}),('data/cloud-source-cache.json',cache or {'records':{}}),('data/public-source-providers.json',[])]:
            (root/file).write_text(json.dumps(data),encoding='utf8')

    def test_incomplete_new_scope_does_not_republish_old_negative(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);work=self.work();now=1793440000
            work['zh']['sourceCheck']=make_check(work,reference(work),None,now-10)
            self.fixture(root,[work],{'records':{'example':{'check':work['zh']['sourceCheck'],'queryPolicy':'old-29','scopeHash':'old'}}})
            probe=Mock(return_value=(None,[{'reason':'needs_configuration','http':0}]))
            with patch('source_availability.publish')as publish,patch('mainland_names.republish_home'):
                result=run(root,probe=probe,now=now)
                self.assertEqual(result['records'][0]['status'],'incomplete')
                saved=publish.call_args.args[0]['entries'][0]
                self.assertNotIn('sourceCheck',saved['zh'])
            cache=json.loads((root/'data/cloud-source-cache.json').read_text())['records']['example']
            self.assertTrue(cache['pending']);self.assertNotIn('check',cache)
            self.assertNotIn('sourceCheck',apply_cached(saved,root)['zh'])

    def test_retry_moves_failed_work_behind_unattempted_works(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);a=self.work(slug='a');b=self.work(slug='b');now=1793440000
            self.fixture(root,[a,b]);probe=Mock(return_value=(None,[{'reason':'network','http':0}]))
            with patch('source_availability.publish'),patch('mainland_names.republish_home'):
                first=run(root,limit=1,probe=probe,now=now)
                second=run(root,limit=1,probe=probe,now=now+4000)
            self.assertEqual(first['records'][0]['slug'],'a');self.assertEqual(second['records'][0]['slug'],'b')

    def test_old_scope_negative_is_removed_but_positive_survives(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);work=self.work();self.fixture(root,[work])
            for found in (False,True):
                copy_work=copy.deepcopy(work);copy_work['zh']['sourceCheck']=make_check(work,reference(work),{'routes':1}if found else None,1793440000)
                copy_work['zh']['nameSelection']={'complete':True}
                value=apply_cached(copy_work,root)
                self.assertEqual('sourceCheck'in value['zh'],found);self.assertFalse(value['zh']['nameSelection']['complete'])

    def test_reviewed_baseline_title_also_enters_source_queue(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);work=self.work();work['zh'].pop('name_status');work['zh']['provenance']='reviewed_mainland_catalog'
            self.fixture(root,[work]);probe=Mock(return_value=(None,[]))
            with patch('source_availability.publish'),patch('mainland_names.republish_home'):
                self.assertEqual(run(root,probe=probe,now=1793440000)['eligible'],1)
            probe.assert_called_once()

    def test_unreviewed_chinese_label_does_not_enter_source_queue(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);work=self.work();work['zh'].pop('name_status')
            self.fixture(root,[work]);probe=Mock()
            self.assertEqual(run(root,probe=probe,now=1793440000)['eligible'],0);probe.assert_not_called()

    def test_home_source_sync_preserves_official_copy_and_evidence_boundary(self):
        home={'zh':{'metadataPolicy':'mainland-v1','summary':'首页官方文案'}}
        main={'zh':{'title':'已审核名称','provenance':'reviewed_mainland_catalog','sourceCheck':{'found':True},'summary':'主目录文案'}}
        sync_home_zh(home,main)
        self.assertEqual(home['zh']['summary'],'首页官方文案');self.assertNotIn('title',home['zh']);self.assertTrue(home['zh']['sourceCheck']['found'])
        main['zh'].update(name_status='verified_title_sources',name_sources=[{'url':'https://movie.douban.com/subject/36229588/'}])
        sync_home_zh(home,main);self.assertEqual(home['zh']['title'],'已审核名称');self.assertEqual(home['zh']['summary'],'首页官方文案')
