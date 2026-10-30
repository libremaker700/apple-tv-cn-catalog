import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import home_sync as h

def entry(n):return {'slug':'work-'+str(n),'en':'Work '+str(n),'kind':'series','officialIdentity':{'watchUrl':'https://tv.apple.com/us/show/work/umc.cmc.work'+str(n)}}
def item(n):return {'id':'umc.cmc.work'+str(n),'title':'Work '+str(n),'type':'Show','segue':{'destination':{'id':'umc.cmc.work'+str(n),'$kind':'ShowPageIntent'}},'artwork':{'wide':{'template':'https://is1-ssl.mzstatic.com/image/thumb/'+str(n)+'/{w}x{h}{c}.{f}'},'tall':{'template':'https://is1-ssl.mzstatic.com/image/thumb/wrong/{w}x{h}.{f}'}}}
def page(items,storefront='us'):
    data={'shelves':[{'id':'uts.col.tv-plus-epic-stage','items':[{'title':'Subscribe now'}]+items},{'id':'uts.col.ChartsShows.tvs.sbd.4000','items':items},{'id':'uts.col.tv-plus-newest-releases','items':list(reversed(items))}]}
    return '<script type="application/json" id="serialized-server-data">'+json.dumps({'data':[{'intent':{'$kind':'ChannelPageIntent','id':'tvs.sbd.4000','storefront':storefront},'data':data}]})+'</script>'
def image(url):return {'artwork':h.BASE+'images/'+'a'*64+'.jpg','width':1920,'height':1080}

class Home(unittest.TestCase):
    def test_current_order_and_native_wide_images_only(self):
        queries=[];catalog={'entries':[entry(n) for n in range(3)]}
        value,_=h.collect(catalog,page([item(n)for n in range(3)]),lambda url:queries.append(url) or image(url))
        self.assertEqual([x['slug']for x in value['hero']],['work-0','work-1','work-2'])
        self.assertEqual([x['slug']for x in value['shelves'][1]['items']],['work-2','work-1','work-0'])
        self.assertTrue(all('/1920x1080sr.jpg' in q and '/wrong/'not in q for q in queries))
        changed,_=h.collect(catalog,page([item(2),item(0),item(1)]),image)
        self.assertNotEqual(value['hero'],changed['hero']);self.assertEqual(catalog['entries'][0],entry(0))
    def test_wrong_region_and_partial_page_rejected(self):
        with self.assertRaises(ValueError):h.channel_data(page([],storefront='tw'))
        with self.assertRaises(ValueError):h.collect({'entries':[entry(0)]},page([item(0)]),image)
    def test_unknown_licensed_work_does_not_rebind_original(self):
        items=[item(n)for n in range(4)];catalog={'entries':[entry(n)for n in range(3)]}
        value,report=h.collect(catalog,page(items),image)
        self.assertEqual(len(value['hero']),3);self.assertEqual(report['unmappedChannelWorks'][0]['officialId'],'umc.cmc.work3')
        self.assertEqual(len(catalog['entries']),3)
    def test_duplicate_official_id_requires_exact_work_name(self):
        items=[item(n)for n in range(3)];extra=dict(entry(0),slug='work-zero-other-edition',en='Other Edition')
        value,_=h.collect({'entries':[entry(n)for n in range(3)]+[extra]},page(items),image)
        self.assertEqual(value['hero'][0]['slug'],'work-0')
        poisoned=copy.deepcopy(value);poisoned['hero'][0]['artwork']='https://example.invalid/portrait.jpg'
        with self.assertRaises(AssertionError):h.validate(poisoned)

if __name__=='__main__':unittest.main()
