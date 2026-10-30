import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from douban_mobile import verify_payload,DoubanMobile
from minimax_agent import redact,AgentError
from public_sources import PublicPages
from source_candidate import verify_candidate
import resolve_titles as resolver
from test_titles import ENTRY,NOW,Fake,PATCH
from test_summaries import SUMMARY

REF={'english_title':'Manhunt','kind':'tv','year':'2024'}
SUBJECT={'id':'12345','title':'追捕刺客 第一季','original_title':'Manhunt','aka':['Manhunt Season 1','追缉刺客(港)'],
    'type':'tv','year':'2024','intro':SUMMARY,'rating':{'value':7.9,'count':1234}}
class Pages:
    def __init__(self,data):self.data=data;self.events=[];self.urls=[]
    def json(self,url,**kw):self.urls.append(url);return [{'id':'12345','type':'movie'}] if 'subject_suggest' in url else self.data
class Lookup:
    def __init__(self,direct=None,payload=None):self.patch=direct;self.pages=Pages(payload);self.stages=[]
    def direct(self,*a):return copy.deepcopy(self.patch)
class Agent:
    def __init__(self,error=None,wrong=False):self.calls=0;self.error=error;self.wrong=wrong
    def search(self,records):
        self.calls+=1
        if self.error:raise AgentError(self.error)
        return {'status':'ok','records':[{'slug':r['slug'],'english_title':r['english_title'],'chinese_title':'同名错片' if self.wrong else '追捕刺客',
            'sources':['https://movie.douban.com/subject/12345/'],'identity_text':'模型编造的正文不能用于核验'} for r in records],
            'usage':{'total_tokens':99},'tools':['web_search']}
class NoSearch:
    stopped=False
    def search(self,*a):return None,{'status':'monthly_budget_exhausted'}
class ResolverTests(unittest.TestCase):
    def test_mobile_ignores_suggest_type_and_checks_original_year_kind(self):
        pages=Pages(SUBJECT);result=DoubanMobile(pages).lookup(REF,'now')
        self.assertEqual(result['display_name_zh'],'追捕刺客');self.assertTrue(pages.urls[-1].endswith('/tv/12345'))
        self.assertEqual(result['douban_rating_count'],1234);self.assertNotIn('追缉刺客(港)',result['aliases_zh'])
        for changed in ({'original_title':'Other film','aka':[]},{'year':'2019'},{'type':'movie'},{'id':'98765'},{'title':'追捕刺客 第二季'}):
            self.assertIsNone(verify_payload(REF,dict(SUBJECT,**changed),'12345','tv','now'))
    def test_delayed_year_only_with_known_matching_imdb(self):
        changed=dict(SUBJECT,year='2027',attrs={'imdb':'tt27304258'})
        self.assertIsNone(verify_payload(REF,changed,'12345','tv','now'))
        self.assertEqual(verify_payload(dict(REF,imdb_id='tt27304258'),changed,'12345','tv','now')['release_year'],2027)
    def test_rating_absence_never_fabricates_rating_or_blocks_verified_title(self):
        for rating in ({},{'value':8,'count':0},{'value':float('nan'),'count':10}):
            patch=verify_payload(REF,dict(SUBJECT,rating=rating),'12345','tv','now')
            self.assertEqual(patch['rating_status'],'NO_RATING');self.assertNotIn('douban_rating',patch)
    def test_model_cannot_verify_itself_or_change_name(self):
        candidate=Agent().search([dict(REF,slug='manhunt')])['records'][0]
        self.assertEqual(verify_candidate(Lookup(payload=None),REF,candidate,'now'),(None,'UNVERIFIED'))
        self.assertEqual(verify_candidate(Lookup(payload=SUBJECT),REF,dict(candidate,chinese_title='模型乱译'),'now'),(None,'DISPUTED'))
        self.assertEqual(verify_candidate(Lookup(payload=SUBJECT),REF,dict(candidate,english_title='The Office'),'now'),(None,'POSSIBLE_FALSE_POSITIVE'))
        self.assertEqual(verify_candidate(Lookup(payload=SUBJECT),REF,candidate,'now')[1],'VERIFIED')
    def test_empty_suggest_is_retryable_not_not_found(self):
        pages=Pages(None);pages.json=lambda *a,**kw:[];lookup=DoubanMobile(pages)
        self.assertIsNone(lookup.lookup(REF,'now'));self.assertEqual(lookup.diagnostics[0]['status'],'EMPTY_RESPONSE')
    def test_douban_headers_and_throttle_shared_across_hosts(self):
        class Session:
            def __init__(self):self.calls=[]
            def get(self,url,**kw):
                self.calls.append(kw['headers']);return type('R',(),{'status_code':200,'content':b'[]','text':'[]'})()
        session=Session();pages=PublicPages(session)
        with patch('public_sources.time.monotonic',side_effect=[100,100,100,101.8]),patch('public_sources.time.sleep') as sleep:
            pages.get('https://movie.douban.com/j/subject_suggest',{'q':'x'});pages.get('https://m.douban.com/rexxar/api/v2/tv/12345')
        self.assertEqual(session.calls[0]['X-Requested-With'],'XMLHttpRequest');self.assertIn('Referer',session.calls[1]);sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0],1.8)
    def fixture(self,root):
        entry=copy.deepcopy(ENTRY);entry['zh']['summary']=''
        resolver.dump(root/'docs/catalog.json',{'entries':[entry]});resolver.dump(root/'docs/version.json',{'checked_at':123})
    def test_verified_source_publishes_aliases_once_and_preserves_state_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root);agent=Agent()
            with patch.object(resolver,'publish') as publish:
                report=resolver.run(root,agent=agent,lookup=Lookup(payload=SUBJECT),search=NoSearch(),clock=NOW)
                self.assertEqual(agent.calls,1);self.assertEqual(report['records'][0]['confidence'],'VERIFIED')
                fresh=publish.call_args.args[0];e=fresh['entries'][0];self.assertEqual(e['zh']['title'],'追捕刺客')
                for key in ('slug','en','kind','seasons','artwork'):self.assertEqual(e[key],ENTRY[key])
                resolver.dump(root/'docs/catalog.json',fresh);publish.reset_mock()
                resolver.run(root,agent=agent,lookup=Lookup(),search=NoSearch(),clock=NOW)
                self.assertEqual(agent.calls,1);publish.assert_not_called()
                data=json.loads((root/'docs/title-map.json').read_text(encoding='utf8'))['records'][0]
                self.assertEqual(data['provider_status'],'NATIVE_CHECK_ON_OPEN');self.assertEqual(data['rating_count'],1234)
                self.assertNotIn(b'\r\r\n',(root/'docs/title-map.csv').read_bytes())
    def test_auth_failure_reserves_once_and_never_replaces_existing_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root);agent=Agent(error='HTTP_401')
            with patch.object(resolver,'publish') as publish:
                first=resolver.run(root,agent=agent,lookup=Lookup(),search=NoSearch(),clock=NOW)
                second=resolver.run(root,agent=agent,lookup=Lookup(),search=NoSearch(),clock=NOW)
                self.assertEqual(first['agent']['status'],'HTTP_401');self.assertEqual(agent.calls,1);publish.assert_not_called()
                state=json.loads((root/'data/agent-title-cache.json').read_text());self.assertEqual(state['budgets']['2026-10'],1)
    def test_monthly_budget_blocks_agent_and_usage_redacts_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root);resolver.dump(root/'data/agent-title-cache.json',{'schema':1,'records':{},'budgets':{'2026-10':20}})
            agent=Agent();report=resolver.run(root,agent=agent,lookup=Lookup(),search=NoSearch(),clock=NOW)
            self.assertEqual(agent.calls,0);self.assertEqual(report['agent']['status'],'monthly_budget_exhausted')
        self.assertEqual(redact({'text':'secret 12345'}, {'token':'secret','user_id':'12345'}),{'text':'[REDACTED] [REDACTED]'})
if __name__=='__main__':unittest.main()
