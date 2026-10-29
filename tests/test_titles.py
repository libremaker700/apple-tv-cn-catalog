import copy,json,tempfile,unittest,sys
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import catalog,title_lookup as t
from title_sources import wiki_patch

NOW=datetime(2026,10,30,tzinfo=timezone.utc)
ENTRY={'slug':'manhunt','en':'Manhunt','kind':'series','releaseDate':'2024-03-15','seasonNumber':1,
       'zh':{'title':'追捕','summary':'已有简介','date':'2024-03-15','actors':['演员甲','演员乙'],'aliases':['旧译名'],'watchUrl':'https://tv.apple.com/us/show/manhunt/umc.cmc.abc'},
       'artwork':'https://example.invalid/poster.jpg','seasons':[{'season':1,'summary':'本季简介'}]}
PATCH={'display_name_zh':'追捕刺客','aliases_zh':['追捕刺客'],'sources':[{'type':'wikipedia_title','url':'https://zh.wikipedia.org/wiki/追捕刺客'}],'name_checked_at':NOW.isoformat()}
class Fake:
    def __init__(self,verified=True):self.keys=['secret-one'];self.stopped=False;self.calls=0;self.verified=verified
    def direct(self,*args):return None
    def verify(self,*args):return None
    def search(self,ref,when,reserve):
        if not reserve():return None,{'status':'monthly_budget_exhausted','results':[]}
        self.calls+=1;return (PATCH if self.verified else None),{'status':'verified' if self.verified else 'pending_review','results':[]}
class Reply:
    def __init__(self,status):self.status_code=status
    def json(self):return {'results':[],'usage':{'credits':1}}
class Session:
    def __init__(self,statuses):self.statuses=list(statuses);self.auth=[]
    def post(self,url,**kwargs):self.auth.append(kwargs['headers']['Authorization']);return Reply(self.statuses.pop(0))

class Titles(unittest.TestCase):
    def test_identity_requires_original_year_and_type(self):
        ref={'english_title':'Manhunt','kind':'tv','year':'2024','display_name_zh':''}
        page={'extract':'《追捕刺客》（Manhunt）是一部2024年美国电视剧。','fullurl':'https://zh.wikipedia.org/wiki/追捕刺客'}
        self.assertIsNotNone(wiki_patch(ref,page,'now'))
        for bad in ('《同名剧》（Manhunt）是一部2019年美国电视剧。','《同名电影》（Manhunt）是一部2024年电影。','《无关作品》（Other Show）是一部2024年电视剧。'):
            self.assertIsNone(wiki_patch(ref,dict(page,extract=bad),'now'))
    def test_patch_only_title_fields(self):
        ident=t.identity(ENTRY,{});result=t.apply_verified(ENTRY,{'status':'verified','identity':ident,'patch':PATCH},ident)
        self.assertEqual(result['zh']['title'],'追捕刺客');self.assertIn('追捕',result['zh']['aliases'])
        self.assertEqual(result['zh']['summary'],ENTRY['zh']['summary']);self.assertEqual(result['zh']['actors'],ENTRY['zh']['actors'])
        for key in ('slug','en','kind','releaseDate','seasonNumber','artwork','seasons'):self.assertEqual(result[key],ENTRY[key])
        self.assertEqual(t.apply_verified(ENTRY,{'status':'verified','identity':dict(ident,year='2019'),'patch':PATCH},ident),ENTRY)
    def test_key_fallback_auth_but_not_rate_limit(self):
        session=Session([401,200]);client=t.SearchClient(['a','b'],session);reserved=[]
        client.search({'english_title':'Example','kind':'tv','year':'2024'},'now',lambda:reserved.append(1) or True)
        self.assertEqual(session.auth,['Bearer a','Bearer b']);self.assertEqual(len(reserved),2)
        session=Session([429]);client=t.SearchClient(['a','b'],session)
        client.search({'english_title':'Example','kind':'tv','year':'2024'},'now',lambda:True)
        self.assertEqual(session.auth,['Bearer a']);self.assertTrue(client.stopped)
    def test_cache_and_shared_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'docs').mkdir();(root/'data').mkdir()
            t.dump(root/'docs/catalog.json',{'entries':[ENTRY]});t.dump(root/'docs/version.json',{'checked_at':123})
            client=Fake()
            with patch.object(t,'publish') as publish:
                report=t.run(root,force=True,limit=12,monthly_limit=1,clock=NOW,client=client)
                self.assertEqual(client.calls,1);self.assertEqual(report['monthly_reserved'],1);self.assertEqual(len(report['verified_changes']),1)
                saved=publish.call_args.args[0];t.dump(root/'docs/catalog.json',saved)
                report=t.run(root,force=True,limit=12,monthly_limit=1,clock=NOW,client=client)
                self.assertEqual(client.calls,1);self.assertEqual(report['reused_verified'],1)
                self.assertEqual(saved['entries'][0]['seasons'],ENTRY['seasons'])
                self.assertNotIn('secret-one',(root/'data/title-cache.json').read_text(encoding='utf8'))
    def test_budget_zero_and_unverified_snippet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);t.dump(root/'docs/catalog.json',{'entries':[ENTRY]});t.dump(root/'docs/version.json',{'checked_at':123})
            client=Fake(False)
            with patch.object(t,'publish') as pub:
                r=t.run(root,force=True,monthly_limit=0,clock=NOW,client=client);self.assertEqual(client.calls,0);self.assertEqual(r['searched'],0);pub.assert_not_called()
if __name__=='__main__':unittest.main()
