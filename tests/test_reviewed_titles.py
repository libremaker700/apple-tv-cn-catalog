import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from reviewed_titles import records,apply_catalog,apply_home

class ReviewedTitles(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'data').mkdir()
        self.record={'slug':'work','en':'A Film','officialId':'umc.cmc.work','watchUrl':'https://tv.apple.com/us/movie/work/umc.cmc.work','kind':'movie','title':'测试电影','year':2002,'subject':{'id':'123','title':'测试电影','original_title':'A Film','year':'2002','type':'movie','aka':[]}}
        self.data={'schema':1,'checkedAt':'2026-10-31','records':[self.record]};self.save()
        self.catalog={'entries':[{'slug':'work','en':'A Film','kind':'movie','releaseDate':'2022-02-14','officialIdentity':{'watchUrl':self.record['watchUrl']},'seasons':[],'artwork':'original'}]}
        self.home={'works':[{'slug':'work','en':'A Film','kind':'movie','officialId':'umc.cmc.work','year':'2022','releaseDate':'2022-02-14'}]}
    def save(self):(self.root/'data/reviewed-title-import.json').write_text(json.dumps(self.data,ensure_ascii=False),encoding='utf-8')
    def tearDown(self):self.tmp.cleanup()
    def test_only_names_and_search_year_change_idempotently(self):
        original=copy.deepcopy(self.catalog);out=apply_catalog(self.catalog,self.root);e=out['entries'][0]
        self.assertEqual(e['zh']['title'],'测试电影');self.assertEqual(e['zh']['searchYear'],2002)
        self.assertEqual(e['releaseDate'],'2022-02-14');self.assertEqual(e['artwork'],'original');self.assertEqual(self.catalog,original)
        self.assertEqual(apply_catalog(out,self.root),out);self.assertNotIn('_identityYear',e['zh'])
        self.assertEqual(apply_home(self.home,self.root)['works'][0]['year'],'2022')
    def test_rejects_wrong_source_year_original_or_type(self):
        for key,value in [('year','2003'),('original_title','Another Film'),('type','tv')]:
            old=self.record['subject'][key];self.record['subject'][key]=value;self.save()
            with self.assertRaises(AssertionError):records(self.root)
            self.record['subject'][key]=old
    def test_official_identity_changes_cannot_rebind(self):
        self.catalog['entries'][0]['officialIdentity']['watchUrl']='https://tv.apple.com/us/movie/other/umc.cmc.other'
        with self.assertRaises(ValueError):apply_catalog(self.catalog,self.root)
        self.home['works'][0]['slug']='other'
        with self.assertRaises(ValueError):apply_home(self.home,self.root)
    def test_existing_verified_name_summary_and_aliases_survive(self):
        self.catalog['entries'][0]['zh']={'metadataPolicy':'mainland-v1','name_status':'verified_title_sources','title':'另一已核验译名','summary':'原有简介','aliases':['旧别名']}
        out=apply_catalog(self.catalog,self.root)['entries'][0]['zh'];self.assertEqual(out['title'],'另一已核验译名');self.assertEqual(out['summary'],'原有简介');self.assertIn('测试电影',out['aliases']);self.assertIn('A Film',out['aliases'])
