import copy,json,re,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import home_sources as s
from home_validation import validate_home

def item(n):return {'id':'umc.cmc.work'+str(n),'title':'Work '+str(n),'type':'Movie','segue':{'destination':{'id':'umc.cmc.work'+str(n),'$kind':'MoviePageIntent'},'url':'https://tv.apple.com/us/movie/work-'+str(n)+'/umc.cmc.work'+str(n)},'artwork':{'template':'https://is1-ssl.mzstatic.com/image/thumb/card'+str(n)+'/{w}x{h}.{f}','wide':{'template':'https://is1-ssl.mzstatic.com/image/thumb/hero'+str(n)+'/{w}x{h}{c}.{f}'}}}
def page(kind,identity,labels,rows):
    shelves=[{'id':name,'header':{'title':name},'items':rows}for name in labels]
    if kind=='ChannelPageIntent':shelves.insert(0,{'id':'uts.col.tv-plus-epic-stage','items':rows})
    return '<script id="serialized-server-data">'+json.dumps({'data':[{'intent':{'$kind':kind,'id':identity,'storefront':'us'},'data':{'shelves':shelves}}]})+'</script>'
def image(url,w,h):
    import hashlib
    return {'artwork':'https://libremaker700.github.io/apple-tv-cn-catalog/home/images/'+hashlib.sha256(url.encode()).hexdigest()+'.jpg','width':w,'height':h}
class OfficialHome(unittest.TestCase):
    def collect(self,rows=None,detail=None):
        rows=rows or [item(n)for n in range(4)]
        catalog={'entries':[{'slug':'known-0','en':'Work 0','kind':'movie','officialIdentity':{'watchUrl':'https://tv.apple.com/us/movie/work-0/umc.cmc.work0'}}]}
        main=page('ChannelPageIntent','tvs.sbd.4000',list(s.LABELS)[:5],rows);room=page('RoomPageIntent',s.ROOM_ID,list(s.LABELS)[5:],list(reversed(rows)))
        return s.collect(catalog,main,room,image,detail or (lambda w:dict(w,year='1997',releaseDate='1997-01-01')))
    def test_complete_shelves_preserve_official_order_and_unknown_works(self):
        home,report=self.collect();validate_home(home)
        self.assertEqual(home['schema'],2);self.assertEqual(len(home['shelves']),10);self.assertEqual(len(home['works']),4)
        self.assertEqual(report['additionalWorks'],3)
        self.assertEqual([r['officialId']for r in home['shelves'][0]['items']],['umc.cmc.work'+str(n)for n in range(4)])
        self.assertEqual([r['officialId']for r in home['shelves'][5]['items']],['umc.cmc.work'+str(n)for n in reversed(range(4))])
        self.assertTrue(all((r['width'],r['height'])==(400,600)for shelf in home['shelves']for r in shelf['items']))
    def test_no_twenty_item_truncation(self):
        home,_=self.collect([item(n)for n in range(21)])
        self.assertEqual(len(home['shelves'][-1]['items']),21)
    def test_failed_detail_or_missing_official_art_never_publishes_partial_set(self):
        def failed(w):raise ValueError('offline')
        with self.assertRaises(ValueError):self.collect(detail=failed)
        rows=[item(n)for n in range(4)];rows[1]['artwork'].pop('template')
        with self.assertRaises(ValueError):self.collect(rows)
    def test_feed_rejects_region_and_playback_injection(self):
        home,_=self.collect()
        bad=copy.deepcopy(home);bad['works'][0]['watchUrl']=bad['works'][0]['watchUrl'].replace('/us/','/tw/')
        with self.assertRaises(ValueError):validate_home(bad)
        bad=copy.deepcopy(home);bad['works'][0]['id']='12345'
        with self.assertRaises(AssertionError):validate_home(bad)
        bad=copy.deepcopy(home);bad['shelves'][0]['items'][0]['officialId']='umc.cmc.other'
        with self.assertRaises(AssertionError):validate_home(bad)
if __name__=='__main__':unittest.main()
