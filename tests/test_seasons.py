import copy,hashlib,json,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from season_sync import Collector,SeasonError,parse_show

SHOW='umc.cmc.testshow';NOW=int(datetime(2026,10,30,tzinfo=timezone.utc).timestamp())
def metadata(number):
    return {'id':'umc.cmc.season'+str(number),'showId':SHOW,'seasonNumber':number,'type':'Season',
            'releaseDate':int(datetime(2024 if number==1 else 2026,1,1,tzinfo=timezone.utc).timestamp()*1000),
            'images':{'coverArt16X9':{'url':'https://is1-ssl.mzstatic.com/image/season'+str(number)+'/{w}x{h}.{f}'}}}
def page(numbers=(1,2)):
    data={'data':[{'intent':{'$kind':'UtsConfigureIntent'},'data':{'configuration':{'applicationProps':{'requiredParamsMap':{'Default':{'sf':'143441','locale':'en-US','utsk':'public-web-session','v':'101','pfm':'web','caller':'web'}}}}}},
                  {'intent':{'$kind':'ShowPageIntent','id':SHOW},'data':{'shelves':[{'header':{'seasons':[{'id':'umc.cmc.season'+str(n),'seasonNumber':n,'episodeCount':8} for n in numbers]}}]}}]}
    return '<script id="serialized-server-data" type="application/json">'+json.dumps(data)+'</script>'
class Reply:
    def __init__(self,value=None,text='',raw=b'picture'):self.value=value;self.text=text;self.content=raw
    def json(self):return self.value

class Seasons(unittest.TestCase):
    def setUp(self):
        self.files=set();self.calls=[];self.bad_season=None;self.bad_show=False;self.missing_images=None;self.html=page()
        self.entry={'slug':'example','en':'Example','kind':'series','seasonNumber':2,'releaseDate':'2026-01-01','officialUrl':'https://www.apple.com/tv-pr/originals/example/',
                    'officialIdentity':{'watchUrl':'https://tv.apple.com/us/show/example/'+SHOW},'sourceArtwork':'https://www.apple.com/tv-pr/shows-and-films/e/example/images/season-02/key.jpg',
                    'artwork':'images/old.jpg','zh':{'title':'国内片名'},'seasons':[{'season':1,'year':'2024','summary':'已核验第一季中文简介'}]}
    def get(self,url):
        self.calls.append(url)
        if url.startswith('https://tv.apple.com/us/show/'):return Reply(text=self.html)
        if url.startswith('https://uts-api.itunes.apple.com/'):
            n=int(url.split('/seasons/umc.cmc.season')[1].split('/')[0])
            if n==self.bad_season:raise IOError('Unavailable')
            data=metadata(n)
            if self.missing_images==n:data['images']={}
            if self.bad_show:data['showId']='umc.cmc.other'
            return Reply({'data':data})
        if url.startswith('https://is1-ssl.mzstatic.com/'):return Reply(raw=url.encode())
        raise AssertionError('Unexpected or regional request')
    def save(self,raw):
        path='images/'+hashlib.sha256(raw).hexdigest()+'.jpg';self.files.add(path);return path
    def collector(self,cache=None,now=NOW,preferences=None):return Collector(self.get,self.save,lambda p:p in self.files,cache,now,preferences)
    def test_hd_preference_only_upgrades_requested_season_and_reuses_bytes(self):
        base=self.collector();old=base.sync(copy.deepcopy(self.entry),{});self.calls=[]
        preferences={'example':{'2':'1080p'}}
        hd=self.collector(base.cache,NOW+3600,preferences);out=hd.sync(copy.deepcopy(old),{})
        self.assertEqual(out['seasons'][0]['artwork'],old['seasons'][0]['artwork'])
        self.assertNotEqual(out['seasons'][1]['artwork'],old['seasons'][1]['artwork'])
        self.assertTrue(out['seasons'][1]['sourceArtwork'].endswith('/1920x1080.jpg'))
        self.assertEqual(out['heroArtwork'],out['seasons'][1]['artwork'])
        self.assertEqual([u for u in self.calls if u.startswith('https://is1-ssl.mzstatic.com/')],['https://is1-ssl.mzstatic.com/image/season2/1920x1080.jpg'])
        self.calls=[];again=self.collector(hd.cache,NOW+7200,preferences).sync(out,{})
        self.assertEqual(again,out);self.assertEqual(len(self.calls),1)
        self.calls=[];later=self.collector(hd.cache,NOW+8*86400,preferences).sync(out,{})
        self.assertTrue(later['seasons'][1]['sourceArtwork'].endswith('/1920x1080.jpg'))
        self.assertFalse(any('season2/960x540.jpg' in u for u in self.calls))
    def test_complete_seasons_and_no_private_browser_parameters(self):
        c=self.collector();out=c.sync(copy.deepcopy(self.entry),{})
        self.assertEqual(out['seasonStatus'],'verified');self.assertEqual([s['season'] for s in out['seasons']],[1,2])
        self.assertEqual([s['year'] for s in out['seasons']],['2024','2026']);self.assertEqual(out['officialIdentity']['year'],'2024')
        self.assertEqual(out['seasons'][0]['summary'],'已核验第一季中文简介');self.assertTrue(out['seasons'][1]['summaryPending'])
        self.assertEqual(out['seasons'][1]['title'],'国内片名 第2季')
        for raw in (json.dumps(out),json.dumps(c.cache)):
            for name in ('utsk','utscf','developerToken','configuration','public-web-session'):self.assertNotIn(name,raw)
    def test_announced_latest_does_not_relabel_old_artwork(self):
        entry=copy.deepcopy(self.entry);entry['seasonNumber']=3;entry['releaseDate']='2027-07-09'
        out=self.collector().sync(entry,{})
        self.assertEqual(out['artworkSeasonNumber'],2);self.assertEqual(out['artworkSeasonYear'],'2026')
        self.assertEqual(out['seasons'][-1]['season'],3);self.assertEqual(out['seasons'][-1]['metadataStatus'],'announced')
    def test_identity_mismatch_never_activates_other_show(self):
        self.bad_show=True;out=self.collector().sync(copy.deepcopy(self.entry),{})
        self.assertEqual(out['seasonStatus'],'pending');self.assertEqual(out['seasonError'],'season_identity_mismatch')
        self.assertTrue(all(s.get('showId')!='umc.cmc.other' for s in out['seasons']))
    def test_partial_failure_keeps_complete_last_valid_seasons(self):
        c=self.collector();out=c.sync(copy.deepcopy(self.entry),{});self.bad_season=2
        result=self.collector(c.cache,NOW+8*86400).sync(out,{})
        self.assertEqual(result['seasonStatus'],'pending');self.assertEqual([s['season'] for s in result['seasons']],[1,2])
        self.assertEqual([s['artwork'] for s in result['seasons']],[s['artwork'] for s in out['seasons']])
    def test_reuse_unchanged_artwork_and_metadata(self):
        c=self.collector();out=c.sync(copy.deepcopy(self.entry),{});self.calls=[]
        again=self.collector(c.cache,NOW+3600).sync(out,{})
        self.assertEqual(len(self.calls),1);self.assertEqual(out,again)
    def test_first_collection_failure_marks_explicit_pending_season(self):
        self.html='No data';entry=copy.deepcopy(self.entry);entry['seasons']=[]
        out=self.collector().sync(entry,{})
        self.assertEqual(out['seasonStatus'],'pending');self.assertEqual([s['season'] for s in out['seasons']],[2])
        self.assertEqual(out['seasons'][0]['metadataStatus'],'pending')
    def test_missing_api_image_uses_same_season_official_pr_art(self):
        self.missing_images=2;self.files.add(self.entry['artwork'])
        out=self.collector().sync(copy.deepcopy(self.entry),{})
        self.assertEqual(out['seasonStatus'],'verified');self.assertEqual(out['seasons'][1]['artwork'],self.entry['artwork'])
        self.assertEqual(out['seasons'][1]['officialId'],'umc.cmc.season2')
    def test_missing_api_image_must_not_borrow_another_season_or_year(self):
        self.missing_images=2;self.files.add(self.entry['artwork'])
        for field,value in [('sourceArtwork','https://www.apple.com/tv-pr/images/season-01/art.jpg'),('releaseDate','2025-01-01')]:
            entry=copy.deepcopy(self.entry);entry[field]=value
            out=self.collector().sync(entry,{})
            self.assertEqual(out['seasonStatus'],'pending');self.assertEqual(out['seasonError'],'season_artwork_missing')
    def test_missing_or_duplicate_seasons_rejected(self):
        for numbers in ((2,),(1,1)):
            with self.assertRaises(SeasonError):parse_show(page(numbers),SHOW)
    def test_us_storefront_required(self):
        with self.assertRaises(SeasonError):parse_show(page().replace('143441','143470'),SHOW)
    def test_wrong_selected_show_page_rejected(self):
        with self.assertRaises(SeasonError):parse_show(page(),'umc.cmc.other')

if __name__=='__main__':unittest.main()
