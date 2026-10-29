import copy,json,tempfile,unittest,sys
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import catalog,title_lookup as t
from title_sources import wiki_patch,structured_patch,bangumi_patch

NOW=datetime(2026,10,30,tzinfo=timezone.utc)
ENTRY={'slug':'manhunt','en':'Manhunt','kind':'series','releaseDate':'2024-03-15','seasonNumber':1,'chinesePending':False,
       'zh':{'metadataPolicy':'mainland-v1','title':'追捕','summary':'已有简介','date':'2024-03-15','actors':['演员甲','演员乙'],'aliases':['旧译名'],'watchUrl':'https://tv.apple.com/us/show/manhunt/umc.cmc.abc'},
       'artwork':'https://example.invalid/poster.jpg','seasons':[{'season':1,'summary':'本季简介'}]}
PATCH={'metadataPolicy':'mainland-v1','display_name_zh':'追捕刺客','aliases_zh':['追捕刺客'],'sources':[{'type':'wikipedia_title','url':'https://zh.wikipedia.org/wiki/追捕刺客'}],'name_checked_at':NOW.isoformat()}
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
    def test_playable_source_does_not_verify_regional_name(self):
        entry={'en':'Matchbox The Movie','zh':{'title':'Matchbox 电影'}}
        hint={'matchedSource':True,'aliases':['火柴盒','火柴盒大电影']}
        self.assertTrue(t.needs_title_review(entry,hint))
        self.assertFalse(t.needs_title_review(dict(entry,zh={'metadataPolicy':'mainland-v1','title':'火柴盒大电影'}),hint))
        self.assertTrue(t.needs_title_review(dict(entry,zh={'title':'火柴盒大电影'}),dict(hint,matchedSource=False)))
    def test_web_animation_and_exact_season(self):
        ref={'english_title':'WondLa','kind':'anime','year':'2024'}
        subject={'id':497641,'name':'WondLa','name_cn':'寻家','date':'2024-06-28','type':2,'platform':'WEB'}
        self.assertEqual(bangumi_patch(ref,subject,'now')['display_name_zh'],'寻家')
        self.assertIsNone(bangumi_patch(ref,dict(subject,name='WondLa Season 2',date='2025-04-25'),'now'))
        self.assertIsNone(bangumi_patch(ref,dict(subject,type=1),'now'))
        e=dict(ENTRY,genres=['animation','kids & family']);self.assertEqual(t.record(e,{})['kind'],'anime')
    def test_identity_requires_original_year_and_type(self):
        ref={'english_title':'Manhunt','kind':'tv','year':'2024','display_name_zh':''}
        page={'extract':'《追捕刺客》（Manhunt）是一部2024年美国电视剧。','mainland_title':'追捕刺客','fullurl':'https://zh.wikipedia.org/wiki/追捕刺客'}
        self.assertIsNotNone(wiki_patch(ref,page,'now'))
        for bad in ('《同名剧》（Manhunt）是一部2019年美国电视剧。','《同名电影》（Manhunt）是一部2024年电影。','《无关作品》（Other Show）是一部2024年电视剧。'):
            self.assertIsNone(wiki_patch(ref,dict(page,extract=bad),'now'))
    def test_patch_only_title_fields(self):
        ident=t.identity(ENTRY,{});result=t.apply_verified(ENTRY,{'status':'verified','identity':ident,'patch':PATCH},ident)
        self.assertEqual(result['zh']['title'],'追捕刺客');self.assertIn('追捕',result['zh']['aliases'])
        self.assertEqual(result['zh']['summary'],ENTRY['zh']['summary']);self.assertEqual(result['zh']['actors'],ENTRY['zh']['actors'])
        for key in ('slug','en','kind','releaseDate','seasonNumber','artwork','seasons'):self.assertEqual(result[key],ENTRY[key])
        self.assertEqual(t.apply_verified(ENTRY,{'status':'verified','identity':dict(ident,year='2019'),'patch':PATCH},ident),ENTRY)
    def test_chinese_identity_pages_require_fields(self):
        ref={'english_title':'Manhunt','kind':'tv','year':'2024'}
        page={'title':'追捕刺客 (豆瓣)','url':'https://movie.douban.com/subject/12345/','identity_text':'# 追捕刺客 Manhunt (2024)\n类型: 剧情\n首播: 2024-03-15\n又名: 追捕 / 追缉刺客'}
        result=structured_patch(ref,page,'now');self.assertEqual(result['display_name_zh'],'追捕刺客');self.assertIn('追缉刺客',result['aliases_zh'])
        for raw in ('# 追捕刺客 Manhunt (2019)\n首播: 2019-01-01', '# 同名电影 Manhunt (2024)\n上映日期: 2024-01-01', '# 追捕刺客 第二季 Manhunt Season 2 (2024)\n首播: 2024-03-15'):
            self.assertIsNone(structured_patch(ref,dict(page,identity_text=raw),'now'))
        self.assertIsNone(structured_patch(ref,dict(page,identity_text='',content='搜索摘要声称追捕刺客是Manhunt'),'now'))
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
