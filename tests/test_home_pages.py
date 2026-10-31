import sys,copy,unittest,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from home_pages import collect
from home_validation import validate_pages
from official_pages import slim_item,Pages

def item(n):
    return {'id':'umc.cmc.work'+str(n),'type':'Movie','title':'Work '+str(n),'url':'https://tv.apple.com/us/movie/work/umc.cmc.work'+str(n),'releaseDate':1704067200000,'images':{'posterArt':{'url':'https://is1-ssl.mzstatic.com/image/thumb/p'+str(n)+'/{w}x{h}.{f}','width':2000,'height':3000},'shelfImageBackground':{'url':'https://is1-ssl.mzstatic.com/image/thumb/w'+str(n)+'/{w}x{h}.{f}','width':3840,'height':2160}}}
def shelf(name,items,kind='lockup'):return {'id':'shelf-'+str(len(name))+'-'+name.replace(' ','-'),'header':{'title':name},'items':items,'displayType':kind,'url':'https://tv.apple.com/us/shelf/works/uts.col.test'}
class Fake:
    def __init__(self):self.rows=[item(n)for n in range(25)]
    def canvas(self,kind,identity):
        if kind=='room':return {'shelves':[shelf('All Movies',self.rows)]}
        topic=lambda n,t:{'id':'uts.room.'+n,'type':'Room','title':t,'url':'https://tv.apple.com/us/room/'+n+'/uts.room.'+n,'images':item(0)['images']}
        return {'shelves':[shelf('Featured',self.rows[:3],'epicStageWithUpsell'),shelf('Top 10 TV Shows',self.rows[:10]),shelf('Top 10 Movies',self.rows[:10]),shelf('Watch Premieres for Free',self.rows[:4]),shelf('New Releases',self.rows),shelf('Dark Destinations',self.rows[:5],'epicShowcase'),dict(shelf('Browse All Apple Originals',[topic('coming','Coming to Apple TV'),topic('kids','Kids & Family')]),id='uts.col.tv-plus-browse-by-category'),shelf('Must-See Hits',self.rows)]}
    def shelf(self,s):return s
    def get(self,kind,identity):return next(x for x in self.rows if x['id']==identity)
def image(url,w,h):
    import hashlib
    return {'artwork':'https://libremaker700.github.io/apple-tv-cn-catalog/home/images/'+hashlib.sha256(url.encode()).hexdigest()+'.jpg','width':w,'height':h}
class HomePages(unittest.TestCase):
    def test_shelf_art_precedes_generic_poster_and_detail_genres_win(self):
        api=Fake()
        for row in api.rows:
            row['images']['shelfItemImage']={'url':'https://is1-ssl.mzstatic.com/image/thumb/shelf/{w}x{h}.{f}','width':1680,'height':3636}
            row['genres']=[{'name':'Animation'},{'name':'Holiday'}]
        urls=[]
        value,_=collect({'entries':[]},api,lambda url,w,h:(urls.append((url,w,h))or image(url,w,h)))
        self.assertTrue(all(row['artwork']==image('https://is1-ssl.mzstatic.com/image/thumb/shelf/400x600.jpg',400,600)['artwork'] for row in value['shelves'][1]['items']))
        self.assertEqual(value['works'][0]['genres'],['Animation','Holiday'])

    def test_stage_background_is_used_even_when_its_native_ratio_is_four_by_three(self):
        api=Fake();calls=[]
        for row in api.rows:
            row['images']['shelfImageBackground']['width']=4320
            row['images']['shelfImageBackground']['height']=3240
            row['images']['contentImage16X9']={'url':'https://is1-ssl.mzstatic.com/image/thumb/generic/{w}x{h}.{f}','width':1920,'height':1080}
        def capture(url,w,h):
            calls.append((url,w,h));return image(url,w,h)
        collect({'entries':[]},api,capture)
        self.assertIn(('https://is1-ssl.mzstatic.com/image/thumb/w0/1920x1080.jpg',1920,1080),calls)
        self.assertNotIn(('https://is1-ssl.mzstatic.com/image/thumb/generic/1920x1080.jpg',1920,1080),calls)
    def value(self):return collect({'entries':[]},Fake(),image)[0]
    def test_seven_sections_and_complete_destination_counts(self):
        v=self.value();validate_pages(v)
        self.assertEqual([s['title']for s in v['shelves']],['Top 10 电视剧','Top 10 电影','最新上线','暗黑秘境','浏览全部 Apple 原创作品','必看热门影视','即将上线'])
        self.assertEqual(len(v['shelves'][5]['items']),25);self.assertEqual(len(v['shelves'][4]['items']),1)
        self.assertEqual(v['shelves'][3]['layout'],'landscape');self.assertTrue(v['pages']);self.assertEqual(len(v['works']),25)
    def test_home_follows_changed_canvas_order_and_includes_new_film_shelf(self):
        api=Fake();original=api.canvas
        def canvas(kind,identity):
            value=original(kind,identity)
            if kind=='channel':
                shelves=value['shelves'];tv=next(x for x in shelves if x['header']['title']=='Top 10 TV Shows');movies=next(x for x in shelves if x['header']['title']=='Top 10 Movies')
                shelves.remove(tv);shelves.remove(movies)
                shelves.insert(1,movies);shelves.insert(4,tv)
                shelves.insert(1,shelf('Great Movies Now on Apple TV',list(reversed(api.rows[:7]))))
                shelves.insert(2,shelf('Sporting Event',[dict(item(1),type='SportingEvent')]))
            return value
        api.canvas=canvas;value,report=collect({'entries':[]},api,image);validate_pages(value)
        actual=[s['officialTitle']for s in value['shelves']]
        self.assertEqual(actual[:2],['Great Movies Now on Apple TV','Top 10 Movies'])
        self.assertGreater(actual.index('Top 10 TV Shows'),actual.index('New Releases'))
        self.assertNotIn('Sporting Event',actual);self.assertNotIn('Watch Premieres for Free',actual)
        self.assertEqual(len(actual),8);self.assertEqual(actual[-1],'Coming to Apple TV')
        self.assertEqual([r['officialId']for r in value['shelves'][0]['items']],[x['id']for x in reversed(api.rows[:7])])

    def test_rejects_dangling_topic_region_and_playback_injection(self):
        v=self.value()
        for change in [lambda x:x['shelves'][4]['items'][0].update(pageId='missing'),lambda x:x['pages'][0].update(source='https://tv.apple.com/tw/room/x/y'),lambda x:x['works'][0].update(id='123')]:
            b=copy.deepcopy(v);change(b)
            with self.assertRaises((AssertionError,ValueError)):validate_pages(b)
    def test_only_display_metadata_is_retained(self):
        raw=dict(item(1),videos={'hlsUrl':'private'},playables=['temporary'],token='secret')
        self.assertEqual(set(slim_item(raw))-set(item(1)),set())
    def test_exact_name_type_and_year_reuses_original_without_replacing_known_identity(self):
        e={'slug':'known-one','en':'Work 1','kind':'movie','releaseDate':'2024-01-01','officialIdentity':{'watchUrl':''}}
        v,_=collect({'entries':[e]},Fake(),image);self.assertEqual(next(w for w in v['works']if w['officialId']=='umc.cmc.work1')['slug'],'known-one')
        e['releaseDate']='2023-01-01';v,_=collect({'entries':[e]},Fake(),image);self.assertFalse(next(w for w in v['works']if w['officialId']=='umc.cmc.work1').get('knownCatalog'))
        e['releaseDate']='2024-01-01';e['officialIdentity']['watchUrl']='https://tv.apple.com/us/movie/other/umc.cmc.other';v,_=collect({'entries':[e]},Fake(),image);self.assertFalse(next(w for w in v['works']if w['officialId']=='umc.cmc.work1').get('knownCatalog'))
    def test_pagination_follows_until_end_and_detects_cycles(self):
        api=object.__new__(Pages);calls=[]
        def get(kind,identity,token=None):calls.append(token);return {'id':'canvas','source':'https://tv.apple.com/us/room/a/uts.room.a','shelves':[{'id':str(token)}],'nextToken':'10'if token is None else None}
        api.get=get;self.assertEqual(len(api.canvas('room','uts.room.a')['shelves']),2);self.assertEqual(calls,[None,'10'])
        api.get=lambda *a,**k:{'id':'canvas','shelves':[],'nextToken':'10'}
        with self.assertRaises(ValueError):api.canvas('room','uts.room.a')
if __name__=='__main__':unittest.main()
