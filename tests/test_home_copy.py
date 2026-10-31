import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from home_copy import enrich,fixed,extract,validate_copy
from home_sources import CHANNEL

class Translator:
    def __init__(self,fail=False):self.calls=0;self.model='test';self.http=200;self.usage={'totalTokenCount':12};self.fail=fail
    def translate(self,rows):
        self.calls+=1
        if self.fail:raise ValueError('quota')
        return {r['id']:'和史努比一起庆祝万圣节。'for r in rows}

class CopyTests(unittest.TestCase):
    def setUp(self):
        self.home={'hero':[{'officialId':'umc.cmc.test','slug':'test'}],'works':[{'officialId':'umc.cmc.test','kind':'movie'}]}
        self.raw={'umc.cmc.test':{'descriptionEn':'Celebrate Halloween with Snoopy.','badgeEn':'New','noteEn':'#1 Movie on Apple TV','genresZh':['动画','经典']}}
    def test_cache_and_identity_preserved(self):
        cache={};t=Translator();original=copy.deepcopy(self.home)
        first,r=enrich(self.home,self.raw,cache,t,100);second,s=enrich(self.home,self.raw,cache,t,200)
        self.assertEqual(t.calls,1);self.assertEqual(first,second);self.assertEqual(self.home,original);self.assertEqual(s['cacheHits'],1)
        validate_copy('umc.cmc.test',first['hero'][0]['copy']);self.assertNotIn('zh',first['works'][0])
    def test_missing_variant_preserves_only_the_existing_identity_copy(self):
        cache={};t=Translator();first,_=enrich(self.home,self.raw,cache,t,100)
        second,report=enrich(first,{},cache,t,200)
        self.assertEqual(first,second);self.assertEqual(report['retainedCopy'],1);self.assertEqual(t.calls,1)
        second,report=enrich(self.home,{},cache,t,300);self.assertNotIn('copy',second['hero'][0]);self.assertEqual(report['pending'],1)
    def test_source_change_invalidates_only_changed_description(self):
        cache={};t=Translator();enrich(self.home,self.raw,cache,t,100)
        self.raw['umc.cmc.test']['noteEn']='#2 Movie on Apple TV';v,_=enrich(self.home,self.raw,cache,t,200)
        self.assertEqual(t.calls,1);self.assertEqual(v['hero'][0]['copy']['noteZh'],'Apple TV 电影榜第2名')
        self.raw['umc.cmc.test']['descriptionEn']='A new description.';enrich(self.home,self.raw,cache,t,300);self.assertEqual(t.calls,2)
    def test_failure_backoff_does_not_reuse_stale_copy(self):
        cache={};t=Translator();enrich(self.home,self.raw,cache,t,100)
        self.raw['umc.cmc.test']['descriptionEn']='Changed.';bad=Translator(True)
        a,r=enrich(self.home,self.raw,cache,bad,200);b,s=enrich(self.home,self.raw,cache,bad,300)
        self.assertEqual(bad.calls,1);self.assertEqual(a,b);self.assertEqual(a['hero'][0]['copy']['descriptionZh'],'');self.assertEqual(s['pending'],1)
    def test_badges_and_rank_never_invented(self):
        self.assertEqual(fixed('New Episode Every Wednesday'),'每周三更新')
        self.assertEqual(fixed('Another Season Is Coming'),'新一季即将上线');self.assertEqual(fixed('Popular everywhere'),'')
        v,_=enrich(self.home,self.raw,{},Translator(),100);c=v['hero'][0]['copy'];c['noteZh']='Apple TV 电影榜第9名'
        with self.assertRaises(AssertionError):validate_copy('umc.cmc.test',c)
    def test_extract_whitelists_display_text_and_checks_identity(self):
        item={'description':'Hi Snoopy.','badge':'New','explainabilityLine':'#1 Movie on Apple TV','token':'private','videoUrl':'private','buttons':['private'],'segue':{'destination':{'id':'umc.cmc.test','storefront':'us','$kind':'MoviePageIntent'}}}
        data={'data':[{'intent':{'$kind':'ChannelPageIntent','id':'tvs.sbd.4000','storefront':'us'},'data':{'shelves':[{'id':'uts.col.tv-plus-epic-stage','items':[item]}]}}]}
        html='<script id="serialized-server-data">'+json.dumps(data)+'</script>'
        result=extract(html,self.home);self.assertNotIn('private',json.dumps(result))
        with self.assertRaises(ValueError):extract(html.replace('MoviePageIntent','ShowPageIntent'),self.home)
    def test_official_rating_and_primary_genres_not_inferred(self):
        item={'primaryMetadata':['Movie','Animation','Classics'],'ratingBadges':[{'$type':'rating','fallbackText':'G'}],'segue':{'destination':{'id':'umc.cmc.test','storefront':'us','$kind':'MoviePageIntent'}}}
        def html():return '<script id="serialized-server-data">'+json.dumps({'data':[{'intent':{'$kind':'ChannelPageIntent','id':'tvs.sbd.4000','storefront':'us'},'data':{'shelves':[{'id':'uts.col.tv-plus-epic-stage','items':[item]}]}}]})+'</script>'
        c=extract(html(),self.home)['umc.cmc.test'];self.assertEqual(c['contentRating'],'G');self.assertEqual(c['genresZh'],['动画','经典'])
        item['ratingBadges'][0]['fallbackText']='invented';self.assertEqual(extract(html(),self.home)['umc.cmc.test']['contentRating'],'')
        item.pop('ratingBadges');self.assertEqual(extract(html(),self.home)['umc.cmc.test']['contentRating'],'')

class SharedCopyTests(unittest.TestCase):
    def test_new_hero_never_duplicates_shared_translation(self):
        t=Translator();home={'hero':[{'officialId':'umc.cmc.new'}]};raw={'umc.cmc.new':{'descriptionEn':'New English copy.','badgeEn':'New','noteEn':'','genresZh':['犯罪'],'contentRating':'TV-MA'}}
        result,report=enrich(home,raw,{'records':{}},t,100,{'umc.cmc.new':True})
        self.assertEqual(t.calls,0);self.assertEqual(report['requested'],0);self.assertEqual(result['hero'][0]['copy']['contentRating'],'TV-MA')

class TopicCopyTests(unittest.TestCase):
    def test_topic_copy_is_contextual_and_same_original_translates_once(self):
        import tempfile
        from unittest.mock import patch
        from home_copy import process
        source='https://tv.apple.com/us/room/sci-fi/edt.item.example'
        def html(kind,identity,note):
            item={'description':'The same official description.','explainabilityLine':note,'primaryMetadata':['Movie','Sci-Fi','Adventure'],'segue':{'destination':{'id':'umc.cmc.test','storefront':'us','$kind':'MoviePageIntent'}}}
            stage={'id':'stage','presentation':{'layout':{'kind':'epicStage'}},'items':[item]}
            return '<script id="serialized-server-data">'+json.dumps({'data':[{'intent':{'$kind':kind,'id':identity,'storefront':'us'},'data':{'shelves':[stage]}}]})+'</script>'
        home={'source':CHANNEL,'hero':[{'officialId':'umc.cmc.test'}],'works':[{'officialId':'umc.cmc.test','kind':'movie'}],'pages':[{'source':source,'hero':[{'officialId':'umc.cmc.test'}]}]}
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);root.joinpath('data').mkdir();t=Translator()
            with patch('home_copy.Translator',return_value=t):
                result,report=process(home,root,html('ChannelPageIntent','tvs.sbd.4000','#1 Movie on Apple TV'),100,lambda url:html('RoomPageIntent','edt.item.example','Another Season Is Coming').encode())
            self.assertEqual(t.calls,1)
            self.assertEqual(result['hero'][0]['copy']['noteZh'],'Apple TV 电影榜第1名')
            c=result['pages'][0]['hero'][0]['copy'];self.assertEqual(c['noteZh'],'新一季即将上线');self.assertEqual(c['source'],source);validate_copy('umc.cmc.test',c)
            self.assertEqual(c['descriptionZh'],result['hero'][0]['copy']['descriptionZh'])
    def test_foreign_page_copy_rejected(self):
        h={'hero':[{'officialId':'umc.cmc.test'}]};raw={'umc.cmc.test':{'descriptionEn':'','badgeEn':'','noteEn':'','genresZh':[]}}
        result,_=enrich(h,raw,{},Translator(),1,source_url='https://tv.apple.com/hk/room/test/id')
        with self.assertRaises(ValueError):validate_copy('umc.cmc.test',result['hero'][0]['copy'])
