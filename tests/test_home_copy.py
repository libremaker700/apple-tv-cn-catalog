import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from home_copy import enrich,fixed,fixed_badge,extract,validate_copy
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
    def test_primary_genres_are_kept_and_classification_ignored(self):
        item={'primaryMetadata':['Movie','Animation','Classics'],'ratingBadges':[{'$type':'rating','fallbackText':'G'}],'segue':{'destination':{'id':'umc.cmc.test','storefront':'us','$kind':'MoviePageIntent'}}}
        def html():return '<script id="serialized-server-data">'+json.dumps({'data':[{'intent':{'$kind':'ChannelPageIntent','id':'tvs.sbd.4000','storefront':'us'},'data':{'shelves':[{'id':'uts.col.tv-plus-epic-stage','items':[item]}]}}]})+'</script>'
        c=extract(html(),self.home)['umc.cmc.test'];self.assertNotIn('contentRating',c);self.assertEqual(c['genresZh'],['动画','经典'])

    def test_legacy_classification_is_removed_without_retranslating(self):
        from home_copy import remove_classifications,digest
        source=dict(self.raw['umc.cmc.test'],contentRating='G')
        original,_=enrich(self.home,self.raw,{},Translator(),100)
        legacy=copy.deepcopy(original)
        legacy['hero'][0]['copy'].update(contentRating='G',sourceHash=digest(['umc.cmc.test',source]))
        validate_copy('umc.cmc.test',legacy['hero'][0]['copy'])
        remove_classifications(legacy)
        self.assertEqual(legacy,original)

class SharedCopyTests(unittest.TestCase):
    def test_new_hero_never_duplicates_shared_translation(self):
        t=Translator();home={'hero':[{'officialId':'umc.cmc.new'}]};raw={'umc.cmc.new':{'descriptionEn':'New English copy.','badgeEn':'New','noteEn':'','genresZh':['犯罪']}}
        result,report=enrich(home,raw,{'records':{}},t,100,{'umc.cmc.new':True})
        self.assertEqual(t.calls,0);self.assertEqual(report['requested'],0);self.assertEqual(result['hero'][0]['copy']['genresZh'],['犯罪'])

class DatedBadgeTests(unittest.TestCase):
    def test_explicit_official_dates_are_localized_and_validated(self):
        self.assertEqual(fixed_badge('New Season Dec\u00a02'),'新一季 12月2日上线')
        self.assertEqual(fixed_badge('Coming Nov 13'),'11月13日上线')
        self.assertEqual(fixed_badge('Coming January 22'),'1月22日上线')
        self.assertEqual(fixed_badge('Coming Sept. 6'),'9月6日上线')
        for text in ('Coming February 30','New Season Foo 2','Coming Dec 0','Coming Dec 32','Coming Friday','New Season Dec 2 teaser'):
            self.assertEqual(fixed_badge(text),'')
        self.assertEqual(fixed_badge('New'),'新上线')

    def test_enrich_and_copy_only_backfill_derive_from_existing_official_date(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from home_copy import process
        identity='umc.cmc.test'
        home={'hero':[{'officialId':identity}],'works':[]}
        raw={identity:{'descriptionEn':'','badgeEn':'New Season Dec 2','noteEn':'','genresZh':[]}}
        translator=Translator()
        new,_=enrich(home,raw,{},translator,1)
        current=new['hero'][0]['copy']
        self.assertEqual(current['badgeZh'],'新一季 12月2日上线')
        validate_copy(identity,current)
        with self.assertRaises(AssertionError):
            validate_copy(identity,dict(current,badgeZh='新一季 12月3日上线'))
        legacy=dict(current,badgeZh='')
        validate_copy(identity,legacy)
        home['hero'][0]['copy']=legacy
        source='https://tv.apple.com/us/room/coming-to-appletv/edt.item.example'
        home['pages']=[{'source':source,'hero':[{'officialId':identity,'copy':dict(legacy,source=source)}]}]
        with TemporaryDirectory()as directory,patch('home_copy.Translator',return_value=translator):
            result,report=process(home,Path(directory),'',2,showcases_only=True)
        self.assertEqual(report['datedBadgesBackfilled'],2)
        self.assertEqual(result['hero'][0]['copy'],current)
        self.assertEqual(result['pages'][0]['hero'][0]['copy'],dict(current,source=source))
        self.assertEqual(home['hero'][0]['copy'],legacy)
        self.assertEqual(translator.calls,0)

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

class LegacyTopicNotes(unittest.TestCase):
    def test_preexisting_empty_rank_note_is_readable_but_wrong_rank_is_rejected(self):
        home={'hero':[{'officialId':'umc.cmc.test'}]};raw={'umc.cmc.test':{'descriptionEn':'','badgeEn':'','noteEn':'#1 in Sci-Fi on Apple TV','genresZh':['科幻']}}
        value,_=enrich(home,raw,{},Translator(),1);c=value['hero'][0]['copy'];self.assertEqual(c['noteZh'],'Apple TV 科幻榜第1名')
        c['noteZh']='';validate_copy('umc.cmc.test',c)
        c['noteZh']='Apple TV 科幻榜第2名'
        with self.assertRaises(AssertionError):validate_copy('umc.cmc.test',c)

class ShowcaseCopyTests(unittest.TestCase):
    def test_featured_copy_uses_the_exact_official_shelf_and_work(self):
        from home_copy import localize_featured,preserve_featured_copy
        source='https://tv.apple.com/us/room/kids--family/uts.room.kids-tv-plus'
        identities=['umc.cmc.kids','umc.cmc.other','umc.cmc.wrongtype','umc.cmc.blank']
        rows=[{'officialId':identity,'logoTreatment':'official-composite-v1','artwork':'original'}for identity in identities]
        shelf={'id':'family','layout':'featured','source':source,'title':'全家共赏','items':rows}
        works={identity:{'kind':'movie'}for identity in identities}
        def item(identity,description='',kind='MoviePageIntent'):
            return {'$kind':'HeroComponent','note':description,'metadataList':{'items':[{'text':'Movie'},{'text':'Animation'},{'text':'Kids & Family'}]},
                    'explainabilityLine':'#1 in Kids & Family on Apple TV' if identity==identities[0]else'',
                    'segue':{'destination':{'id':identity,'storefront':'us','$kind':kind}}}
        page={'shelves':[{'id':'elsewhere','items':[item(identities[1],'Unrelated synopsis.')]},
                         {'id':'family','items':[item(identities[0],'Official card text.'),item(identities[2],'Wrong type.','ShowPageIntent'),item(identities[3])]}]}
        pending=copy.deepcopy(shelf)
        class Poster:
            def reposition(self,row,raised):
                self.raised.append((row['officialId'],raised))
                return {'artwork':'recomposed'}
            raised=[]
        cache={};translator=Translator();poster=Poster();report=localize_featured(shelf,page,works,cache,translator,1,poster)
        self.assertEqual(report['translated'],1)
        self.assertEqual(report['recomposed'],1)
        self.assertEqual(poster.raised,[(identities[0],True)])
        caption=rows[0]['showcaseCopy'];validate_copy(identities[0],caption)
        self.assertEqual(caption['descriptionEn'],'Official card text.')
        self.assertEqual(caption['descriptionZh'],'和史努比一起庆祝万圣节。')
        self.assertEqual(caption['genresZh'],['动画','儿童与家庭'])
        self.assertEqual(caption['noteZh'],'Apple TV 儿童与家庭榜第1名')
        self.assertEqual(rows[0]['showcaseCopyPosition'],'raised-logo-v1')
        self.assertNotIn('showcaseCopy',rows[1]);self.assertNotIn('showcaseCopy',rows[2])
        self.assertEqual(rows[3]['showcaseCopy']['descriptionZh'],'')
        self.assertEqual(rows[3]['artwork'],'original')
        class BrokenPoster:
            def reposition(self,row,raised):raise ValueError('no image')
        failed=localize_featured(pending,page,works,cache,translator,2,BrokenPoster())
        self.assertEqual(failed['artworkPending'],1)
        self.assertNotIn('showcaseCopy',pending['items'][0])
        self.assertEqual(pending['items'][0]['artwork'],'original')
        recovered=localize_featured(pending,page,works,cache,translator,3,poster)
        self.assertEqual(recovered['cacheHits'],1)
        self.assertEqual(translator.calls,1)
        self.assertEqual(pending['items'][0]['showcaseCopyPosition'],'raised-logo-v1')
        refreshed=dict(shelf,items=[{'officialId':identities[0],'logoTreatment':'official-composite-v1','artwork':'new background'}])
        preserve_featured_copy({'shelves':[refreshed]},{'shelves':[shelf]},BrokenPoster())
        self.assertEqual(refreshed['items'][0]['artwork'],rows[0]['artwork'])
        result=localize_featured(refreshed,{},works,cache,translator,2,poster)
        self.assertEqual(result['retainedCopy'],1)
        self.assertEqual(refreshed['items'][0]['showcaseCopy'],caption)
        self.assertEqual(refreshed['items'][0]['showcaseCopyPosition'],'raised-logo-v1')

    def test_featured_heading_uses_verified_franchise_term(self):
        import tempfile
        from unittest.mock import patch
        from home_copy import process

        work={'officialId':'umc.cmc.test','kind':'series','en':'Fraggle Rock','zh':{'title':'布偶奇遇记','name_status':'verified_title_sources'}}
        shelf={'id':'featured','layout':'featured','officialTitle':'The World of Fraggle Rock','title':'旧译文','source':CHANNEL,
               'items':[{'officialId':work['officialId']}]}
        home={'works':[work],'shelves':[shelf],'hero':[]}
        translator=Translator();inputs=[]
        def translate(rows):
            inputs.extend(rows)
            return {rows[0]['id']:'脆莓公园的世界' if len(inputs)==1 else '布偶奇遇记的世界'}
        translator.translate=translate
        with tempfile.TemporaryDirectory()as folder,patch('home_copy.Translator',return_value=translator):
            first,_=process(home,Path(folder),'',1,showcases_only=True)
            second,_=process(first,Path(folder),'',21602,showcases_only=True)
            self.assertEqual(inputs[0]['glossary'],{'Fraggle Rock':'布偶奇遇记'})
            self.assertEqual(first['shelves'][0]['title'],shelf['officialTitle'])
            self.assertEqual(second['shelves'][0]['title'],'布偶奇遇记的世界')

    def test_showcase_heading_and_caption_follow_their_current_official_text(self):
        import tempfile
        from unittest.mock import patch
        from home_copy import process

        work={'officialId':'umc.cmc.test','kind':'movie'}
        item={'description':'Snoopy prepares dinner.','primaryMetadata':['Movie','Animation','Kids & Family'],
              'explainabilityLine':'#1 in Kids & Family on Apple TV',
              'segue':{'destination':{'id':work['officialId'],'storefront':'us','$kind':'MoviePageIntent'}}}
        shelf={'id':'showcase','layout':'showcase','officialTitle':'A Holiday Classic','title':'旧译文','source':CHANNEL,
               'items':[{'officialId':work['officialId']}]}
        page={'data':[{'intent':{'$kind':'ChannelPageIntent','id':'tvs.sbd.4000','storefront':'us'},
                       'data':{'shelves':[{'id':shelf['id'],'items':[item]}]}}]}
        html=lambda: '<script id="serialized-server-data">'+json.dumps(page)+'</script>'
        t=Translator();inputs=[]
        def translate(rows):
            inputs.extend(r['text'] for r in rows)
            return {r['id']:'节日佳作' if r['text']=='A Holiday Classic' else '史努比准备晚餐。' for r in rows}
        t.translate=translate
        with tempfile.TemporaryDirectory()as folder,patch('home_copy.Translator',return_value=t):
            root=Path(folder)
            home={'works':[work],'shelves':[shelf],'hero':[]}
            first,_=process(home,root,html(),1,showcases_only=True)
            second,_=process(first,root,html(),2,showcases_only=True)
            self.assertEqual(first,second)
            self.assertEqual(inputs,['A Holiday Classic','Snoopy prepares dinner.'])
            self.assertEqual(first['shelves'][0]['title'],'节日佳作')
            copy=first['shelves'][0]['items'][0]['showcaseCopy']
            self.assertEqual(copy['descriptionZh'],'史努比准备晚餐。')
            self.assertEqual(copy['noteZh'],'Apple TV 儿童与家庭榜第1名')
            shelf['officialTitle']='A Different Holiday';item['description']='Snoopy greets friends.'
            process(home,root,html(),3,showcases_only=True)
            self.assertEqual(inputs[-2:],['A Different Holiday','Snoopy greets friends.'])
