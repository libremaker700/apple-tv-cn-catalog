import copy,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import title_lookup as t
from summary_cache import apply_summary
from title_sources import structured_patch
from test_titles import ENTRY,PATCH,NOW,Fake

SUMMARY='一位警探为了保护家人搬到小镇生活，却发现小镇居民正遭受威胁。他与伙伴展开调查，并在调查过程中逐步揭开事件背后的秘密。'
class Summaries(unittest.TestCase):
    def test_identity_bound_summary_only_patch_preserves_title_and_playback_fields(self):
        entry=copy.deepcopy(ENTRY);entry['zh']=None;ident=t.identity(entry,{})
        record={'identity':ident,'status':'verified','patch':{'metadataPolicy':'mainland-v1','summary_zh':SUMMARY,'summary_sources':[{'url':'https://en.wikipedia.org/wiki/Manhunt_(2024_TV_series)'}]}}
        result=apply_summary(entry,record,ident)
        self.assertEqual(result['zh']['summary'],SUMMARY);self.assertNotIn('title',result['zh'])
        for key in ('slug','en','kind','releaseDate','seasonNumber','artwork','seasons'):self.assertEqual(entry[key],result[key])
        self.assertEqual(apply_summary(entry,dict(record,identity=dict(ident,year='2019')),ident),entry)
        self.assertEqual(apply_summary(ENTRY,record,ident),ENTRY)
        record['patch']['summary_sources']=[{'url':'https://tv.apple.com/tw/show/example/id'}]
        self.assertEqual(apply_summary(entry,record,ident),entry)
    def test_douban_and_baidu_plot_require_full_identity_and_plot_section(self):
        ref={'english_title':'Manhunt','kind':'tv','year':'2024'}
        raw='# 追捕刺客 Manhunt (2024)\n首播: 2024-03-15\n## 追捕刺客的剧情简介\n'+SUMMARY+'\n## 演职员\n无关评论内容'
        # Douban exposes a title-specific heading; both sources use verified plot fields.
        page={'title':'追捕刺客 (豆瓣)','url':'https://movie.douban.com/subject/12345/','identity_text':raw}
        result=structured_patch(ref,page,'now');self.assertEqual(result['summary_zh'],SUMMARY)
        self.assertIsNone(structured_patch(dict(ref,year='2019'),page,'now'))
        raw='# 追捕刺客\n电视剧\n外文名\nManhunt\n首播时间\n2024-03-15\n## 剧情简介\n'+SUMMARY+'\n## 演员表\n无关资料'
        result=structured_patch(ref,{'title':'追捕刺客_百度百科','url':'https://baike.baidu.com/item/追捕刺客/123','identity_text':raw},'now')
        self.assertEqual(result['summary_zh'],SUMMARY)
    def test_verified_name_without_synopsis_still_checks_fallback_and_keeps_name(self):
        for found in (True,False):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);entry=copy.deepcopy(ENTRY);entry['zh']['summary']='';ident=t.identity(entry,{})
                cached={'identity':ident,'query_version':t.QUERY_VERSION,'status':'verified','checked_at':NOW.isoformat(),'patch':PATCH}
                t.dump(root/'data/title-cache.json',{'schema':1,'records':{t.cache_key(ident):cached},'budgets':{}})
                t.dump(root/'docs/catalog.json',{'entries':[entry]});t.dump(root/'docs/version.json',{'checked_at':123})
                client=Fake(False)
                if found:client.direct=lambda *args:dict(PATCH,summary_zh=SUMMARY,summary_sources=[{'url':'https://zh.wikipedia.org/wiki/追捕刺客'}])
                with patch.object(t,'publish') as publish:t.run(root,force=True,clock=NOW,client=client)
                saved=t.read(root/'data/title-cache.json',{})['records'][t.cache_key(ident)]
                self.assertEqual(saved['status'],'verified');self.assertEqual(saved['patch']['display_name_zh'],PATCH['display_name_zh'])
                if found:self.assertEqual(publish.call_args.args[0]['entries'][0]['zh']['summary'],SUMMARY)
                else:self.assertIn('summary_next_retry_at',saved)
if __name__=='__main__':unittest.main()
