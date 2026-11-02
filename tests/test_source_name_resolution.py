import sys,unittest,json,tempfile
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from source_name_resolution import resolve
from api_accounts import SearchAccounts

class NameAuthority(unittest.TestCase):
    def setUp(self):
        self.identity={'douban_id':'37374251','title':'Not a Box','year':2025,'season':1,'actors':[],'directors':[],'url':'https://movie.douban.com/subject/37374251/'}
        self.ref={'english_title':'Not a Box','year':'2025','season':1,'kind':'tv'}
        self.client=Mock();self.client.candidate_names.return_value={'names':['不是盒子'],'status':'ok','service':'ydc'}
    def call(self,best=None,**kw):
        probe=Mock(return_value=(best,[]));discover=Mock(return_value=(None,[]))
        result=resolve(self.identity,self.ref,[],self.client,probe=probe,discover=discover,**kw)
        return result,probe
    def test_answer_is_query_only_and_fallback_is_actual_douban_title(self):
        result,probe=self.call()
        self.assertEqual(result['patch']['display_name_zh'],'Not a Box')
        self.assertNotIn('不是盒子',result['patch']['aliases_zh'])
        self.client.candidate_names.assert_called_once()
        self.assertIn('不是盒子',probe.call_args.args[1])
    def test_only_strong_playable_library_vote_renames(self):
        vote={'title':'不是一个盒子第一季','routes':2,'selection':{'libraries':2,'options':[{'title':'不是一个盒子','libraries':2}]}}
        result,_=self.call(vote)
        self.assertEqual(result['patch']['display_name_zh'],'不是一个盒子')
        self.assertEqual(result['patch']['douban_title'],'Not a Box')
        self.assertEqual(result['evidence']['decision'],'verified_playable_source_name')
        result,_=self.call(dict(vote,recallOnly=True))
        self.assertEqual(result['patch']['display_name_zh'],'Not a Box')
        result,_=self.call(dict(vote,routes=0))
        self.assertEqual(result['patch']['display_name_zh'],'Not a Box')
    def test_cached_answer_is_identity_bound_and_user_hint_is_not_approval(self):
        state={};self.call(state=state,hints=['不是一个盒子']);self.call(state=state)
        self.assertEqual(self.client.candidate_names.call_count,1)
        self.identity['douban_id']='12345678';self.call(state=state)
        self.assertEqual(self.client.candidate_names.call_count,2)

class CandidateAccounts(unittest.TestCase):
    def response(self,status,payload):return Mock(status_code=status,json=lambda:payload)
    def test_configuration_failure_moves_service_not_four_identical_keys(self):
        session=Mock();session.post.side_effect=[self.response(404,{}),self.response(200,{'answer':'{"names":["不是一个盒子"]}','results':[]})]
        client=SearchAccounts(session,{'ydc':[('a','secret1'),('b','secret2')],'tavily':[('c','secret3')]})
        self.assertEqual(client.candidate_names('名字')['names'],['不是一个盒子'])
        self.assertEqual(session.post.call_count,2)
        self.assertEqual(session.post.call_args.kwargs['json']['include_answer'],'advanced')
        self.assertNotIn('secret',str(client.events))
    def test_quota_rotates_and_research_response_is_parsed(self):
        session=Mock();session.post.side_effect=[self.response(402,{}),self.response(200,{'output':{'content':'{"names":["不是盒子"]}','sources':[]}})]
        client=SearchAccounts(session,{'ydc':[('a','key1'),('b','key2')]})
        self.assertEqual(client.candidate_names('名字')['names'],['不是盒子'])
        self.assertEqual(session.post.call_args.args[0],'https://api.you.com/v1/research')
        self.assertEqual(session.post.call_args.kwargs['json']['research_effort'],'lite')

class Publication(unittest.TestCase):
    def test_stale_plex_name_is_replaced_and_no_second_source_probe_occurs(self):
        from unittest.mock import patch
        from mainland_names import run
        class Client:
            events=[]
            def candidate_names(self,question):return {'names':['不是盒子'],'status':'ok','service':'ydc'}
            def search(self,query):raise AssertionError('Plex search must not replace Douban fallback')
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);(root/'docs/home').mkdir(parents=True);(root/'data').mkdir()
            work={'slug':'not-a-box','en':'Not a Box','kind':'series','year':2025,'releaseDate':'2025-06-13','zh':{'title':'魔盒','aliases':['魔盒'],'_identityYear':2025}}
            for path,value in [('docs/catalog.json',{'entries':[work]}),('docs/home/home.json',{'works':[]}),('docs/version.json',{})]:
                (root/path).write_text(json.dumps(value),encoding='utf8')
            identity={'douban_id':'37374251','title':'Not a Box','year':2025,'season':1,'url':'https://movie.douban.com/subject/37374251/'}
            probe=Mock(return_value=(None,[]))
            with patch('mainland_names.DoubanMobile')as mobile,patch('alias_discovery.discover',return_value=(None,[])),patch('mainland_names.publish')as publish,patch('mainland_names.republish_home'):
                mobile.return_value.lookup.return_value=None;mobile.return_value.identities={'37374251':identity}
                result=run(root,client=Client(),lookup=Mock(),probe=probe)
            self.assertEqual(result['records'][0]['confidence'],'IDENTITY_ONLY')
            published_zh=publish.call_args.args[0]['entries'][0]['zh']
            self.assertEqual(published_zh['title'],'Not a Box')
            self.assertNotIn('魔盒',published_zh['aliases'])
            cached=json.loads((root/'data/mainland-name-cache.json').read_text())['records']['not-a-box']['result']
            self.assertEqual(cached['title'],'Not a Box');self.assertEqual(probe.call_count,1)
