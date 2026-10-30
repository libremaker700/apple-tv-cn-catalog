import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from title_sources import Lookup,structured_patch
from public_sources import PublicPages
import title_lookup as t
from test_titles import ENTRY,PATCH,NOW,Fake
from test_summaries import SUMMARY

class OrderedLookup(Lookup):
    def __init__(self,douban=None,wiki=None):super().__init__();self.calls=[];self.d=douban;self.w=wiki
    def douban(self,*a):self.calls.append('douban');return self.d
    def wikipedia(self,*a):self.calls.append('wikipedia');return self.w

class Response:
    def __init__(self,status,text=''):self.status_code=status;self.text=text;self.content=text.encode()
class Session:
    def __init__(self,responses):self.responses=iter(responses);self.calls=[]
    def get(self,url,**kwargs):self.calls.append(url);return next(self.responses)

class SourceOrder(unittest.TestCase):
    def test_complete_douban_stops_and_partial_falls_through_to_wikipedia(self):
        full=dict(PATCH,summary_zh=SUMMARY,summary_sources=[{'url':'https://movie.douban.com/subject/12345/'}])
        ref={'want_summary':True}
        client=OrderedLookup(full);self.assertEqual(client.direct(ref,'now')['summary_zh'],SUMMARY);self.assertEqual(client.calls,['douban'])
        client=OrderedLookup(PATCH,full);self.assertEqual(client.direct(ref,'now')['summary_zh'],SUMMARY);self.assertEqual(client.calls,['douban','wikipedia'])
    def test_tavily_runs_only_when_both_direct_sources_leave_a_gap(self):
        for direct_full in (True,False):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);e=copy.deepcopy(ENTRY);e['zh']['summary']=''
                t.dump(root/'docs/catalog.json',{'entries':[e]});t.dump(root/'docs/version.json',{'checked_at':123})
                full=dict(PATCH,summary_zh=SUMMARY,summary_sources=[{'url':'https://zh.wikipedia.org/wiki/追捕刺客'}])
                lookup=OrderedLookup(PATCH,full if direct_full else None);client=Fake();client.direct=lookup.direct
                with patch.object(t,'publish'):t.run(root,force=True,clock=NOW,client=client)
                self.assertEqual(lookup.calls,['douban','wikipedia']);self.assertEqual(client.calls,0 if direct_full else 1)
    def test_access_error_cools_down_whole_host_without_challenge_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'cache.json';session=Session([Response(418),Response(200,'{"ok":true}')]);now=[100]
            reader=PublicPages(session,path,lambda:now[0]);self.assertIsNone(reader.get('https://movie.douban.com/j/subject_suggest',{'q':'first'}))
            self.assertIsNone(reader.get('https://movie.douban.com/j/subject_suggest',{'q':'second'}));self.assertEqual(len(session.calls),1)
            self.assertEqual(reader.json('https://zh.wikipedia.org/w/api.php'),{'ok':True});self.assertEqual(len(session.calls),2)
            saved=json.loads(path.read_text(encoding='utf8'));self.assertNotIn('body',next(iter(saved['pages'].values())))
            self.assertIsNone(PublicPages(session,path,lambda:now[0]).get('https://movie.douban.com/subject/999/'));self.assertEqual(len(session.calls),2)
    def test_delayed_release_year_needs_exact_known_imdb_and_ignores_regional_alias(self):
        raw='# 反仇专家 The Savant (2027)\n首播: 2027(美国)\n又名: 灭仇专员(港) / 慧眼 / 达人 / 行家\nIMDb: tt27304258\n## 剧情简介\n'+SUMMARY
        ref={'english_title':'The Savant','kind':'tv','year':'2025'};item={'url':'https://movie.douban.com/subject/123456/','identity_text':raw}
        self.assertIsNone(structured_patch(ref,item,'now'))
        result=structured_patch(dict(ref,imdb_id='tt27304258'),item,'now');self.assertEqual(result['display_name_zh'],'反仇专家');self.assertEqual(result['aliases_zh'],['反仇专家','慧眼','达人','行家']);self.assertEqual(result['release_year'],2027)
        self.assertIsNone(structured_patch(dict(ref,imdb_id='tt99999999'),item,'now'))
    def test_json_challenge_page_does_not_repeat_requests_for_other_works(self):
        session=Session([Response(200,'<html>verification required</html>')]);reader=PublicPages(session)
        self.assertEqual(reader.json('https://movie.douban.com/j/subject_suggest',params={'q':'first'}),{})
        self.assertEqual(reader.json('https://movie.douban.com/j/subject_suggest',params={'q':'second'}),{})
        self.assertEqual(len(session.calls),1)
if __name__=='__main__':unittest.main()
