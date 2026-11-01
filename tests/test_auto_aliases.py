import json,sys,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from alias_discovery import discover,keywords
from douban_mobile import DoubanMobile
from api_accounts import SearchAccounts

class AutomaticAliases(unittest.TestCase):
    def test_english_only_subject_keeps_identity_without_claiming_chinese_name(self):
        pages=Mock();pages.json.return_value={'id':'37374251','title':'Not a Box','original_title':'','year':'2025','type':'tv','actors':[],'directors':[]}
        mobile=DoubanMobile(pages);self.assertIsNone(mobile.subject({'english_title':'Not a Box','kind':'tv','season':1,'year':'2025'},'37374251','2026-11-01T00:00:00+00:00'))
        self.assertEqual(mobile.identities['37374251']['douban_id'],'37374251')
        pages.json.return_value['year']='2024';other=DoubanMobile(pages);other.subject({'english_title':'Not a Box','kind':'tv','season':1,'year':'2025'},'37374251','now');self.assertEqual(other.identities,{})
    def test_broad_candidates_need_real_identity_and_keep_seasons_separate(self):
        ident={'douban_id':'37374251','url':'https://movie.douban.com/subject/37374251/','actors':[],'directors':[]}
        ref={'english_title':'Not a Box','kind':'tv','year':'2025','season':1};adapter=Mock()
        good={'vod_id':'1','vod_name':'不是一个盒子','vod_year':'2025','type_name':'欧美动漫','vod_douban_id':'37374251','vod_play_url':'x'}
        adapter.request.side_effect=lambda params:[good,dict(good,vod_id='2',vod_douban_id='12345678',vod_name='盒子'),dict(good,vod_id='3',vod_name='不是一个盒子第二季')]if params['pg']==1 else[]
        with patch('alias_discovery.create',return_value=adapter):result,_=discover(ident,ref,[{'id':'cms','url':'https://example.test/api'}],['不是一个盒子'])
        self.assertEqual(result['aliases_zh'],['不是一个盒子']);self.assertNotIn('vod_id',json.dumps(result));self.assertNotIn('detailMetadata',result)
    def test_pagination_resumes_instead_of_repeating_first_pages(self):
        adapter=Mock();calls=[]
        def request(params):calls.append(params['pg']);return[{'vod_id':str(params['pg']),'vod_name':'English'}]
        adapter.request.side_effect=request;state={};ident={'douban_id':'37374251','actors':[],'directors':[]};ref={'english_title':'Not a Box','kind':'tv','year':'2025','season':1}
        with patch('alias_discovery.create',return_value=adapter):
            discover(ident,ref,[{'id':'a'}],state=state);discover(ident,ref,[{'id':'a'}],state=state)
        self.assertEqual(calls,[1,2,3,4,5,6])
    def test_exhausted_account_and_provider_switch_without_logging_error_body(self):
        session=Mock();session.post.side_effect=[Mock(status_code=432,json=lambda:{'error':'Credit limit exceeded PRIVATE'}),Mock(status_code=200,json=lambda:{'results':[]})]
        pool=SearchAccounts(session,{'ydc':[('ydc-one','secret-one')],'tavily':[('tavily-one','secret-two')]})
        self.assertEqual(pool.search('name')[1],'ok');self.assertEqual(pool.events[0]['reason'],'quota_exhausted');self.assertEqual(len(session.post.call_args_list),2);self.assertNotIn('PRIVATE',json.dumps(pool.events))
    def test_keyword_cap(self):
        words=keywords('Not a Box',['不是一个盒子','其他名字','另一个名字']);self.assertLessEqual(len(words),4);self.assertIn('盒子',words)
    def test_search_titles_only_supply_untrusted_locator_terms(self):
        from alias_discovery import search_hints
        hints=search_hints([{'title':'《不是一个盒子》Not a Box 2025 - 豆瓣'}]);self.assertEqual(hints[0],'不是一个盒子');self.assertIn('盒子',keywords('Not a Box',hints))
    def test_title_pipeline_cannot_access_gemini(self):
        root=Path(__file__).resolve().parents[1]
        self.assertNotIn('GEMINI_API_KEY',(root/'.github/workflows/title-update.yml').read_text('utf8'))
        self.assertNotIn('gemini_titles',(root/'scripts/alias_discovery.py').read_text('utf8'))
        self.assertNotIn('model_hints',(root/'scripts/mainland_names.py').read_text('utf8'))
    def test_automatic_alias_is_saved_and_reused_for_source_checks(self):
        import tempfile
        from mainland_names import run
        identity={'douban_id':'37374251','year':'2025','season':1,'actors':[],'directors':[],'url':'https://movie.douban.com/subject/37374251/'}
        alias={'display_name_zh':'不是一个盒子','aliases_zh':['不是一个盒子'],'douban_id':'37374251','sources':[{'type':'douban_identity_cms_alias','url':identity['url']}]}
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);(root/'docs/home').mkdir(parents=True);(root/'data').mkdir()
            work={'slug':'not-a-box','en':'Not a Box','kind':'series','releaseDate':'2025-06-13','artworkSeasonNumber':1,'seasons':[{'season':1,'year':'2025','releaseDate':'2025-06-13'}],'zh':{'_identityYear':2025}}
            for file,value in [('docs/catalog.json',{'entries':[work]}),('docs/home/home.json',{'works':[]}),('docs/version.json',{})]:(root/file).write_text(json.dumps(value),encoding='utf8')
            client=Mock(events=[]);client.search.return_value=([{'title':'《不是一个盒子》','url':'https://example.test/'}],'ok');mobile=Mock(identities={'37374251':identity});mobile.lookup.return_value=None
            probe=Mock(return_value=({'title':'不是一个盒子','routes':2},[]))
            with patch('mainland_names.DoubanMobile',return_value=mobile),patch('alias_discovery.discover',return_value=(alias,[])),patch('mainland_names.publish'),patch('mainland_names.republish_home'):
                result=run(root,client=client,lookup=Mock(),probe=probe)
            self.assertEqual(result['records'][0]['confidence'],'VERIFIED');self.assertEqual(probe.call_args.args[0]['douban_id'],'37374251')
            cached=json.loads((root/'data/mainland-name-cache.json').read_text(encoding='utf8'))['records']['not-a-box'];self.assertEqual(cached['identity']['douban_id'],'37374251');self.assertEqual(cached['discovery']['_hints'],['不是一个盒子'])
    def test_three_day_workflow_gate_crosses_month_boundary_and_allows_manual(self):
        import datetime,os,tempfile,textwrap
        for filename in ('update.yml','title-update.yml','source-update.yml'):
            source=(Path(__file__).resolve().parents[1]/'.github/workflows'/filename).read_text('utf8')
            gate=textwrap.dedent(source.split("python - <<'PY'",1)[1].split('\n          PY',1)[0])
            for date,event,wanted in [(datetime.date(2026,11,1),'schedule',True),(datetime.date(2026,11,2),'schedule',False),(datetime.date(2026,11,4),'schedule',True),(datetime.date(2026,12,1),'schedule',True),(datetime.date(2026,12,2),'schedule',False),(datetime.date(2026,11,2),'workflow_dispatch',True)]:
                class Frozen(datetime.datetime):
                    @classmethod
                    def now(cls,tz=None):return cls(date.year,date.month,date.day,tzinfo=tz)
                with tempfile.TemporaryDirectory()as tmp,patch('datetime.datetime',Frozen),patch.dict(os.environ,{'EVENT':event,'GITHUB_OUTPUT':str(Path(tmp)/'out')}):
                    exec(compile(gate,'workflow gate','exec'),{})
                    self.assertEqual((Path(tmp)/'out').read_text().strip(),'due='+str(wanted).lower())
