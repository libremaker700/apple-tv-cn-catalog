import copy,hashlib,json,sys,unittest,tempfile,io
from unittest.mock import patch
from PIL import Image
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
    def test_legacy_logo_snapshot_validates_and_republication_removes_only_logos(self):
        from home_pages import image_rows
        from stage_pages import snapshot_files
        from test_home_pages import Fake,collect,image as fixture_image
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'home';(folder/'images').mkdir(parents=True)
            value,_=collect({'entries':[]},Fake(),fixture_image)
            jpegs={}
            for row in image_rows(value):
                size=(row['width'],row['height'])
                if size not in jpegs:
                    encoded=io.BytesIO();Image.new('RGB',size).save(encoded,'JPEG');blob=encoded.getvalue()
                    ref='images/'+hashlib.sha256(blob).hexdigest()+'.jpg';(folder/ref).write_bytes(blob)
                    jpegs[size]=ref
                row['artwork']=h.BASE+jpegs[size]
            for work in value['works']:
                if work.get('landscapeArtwork'):work['landscapeArtwork']=h.BASE+jpegs[(960,540)]
            mark=Image.new('RGBA',(90,30));mark.paste((255,255,255,255),(10,10,80,20))
            encoded=io.BytesIO();mark.save(encoded,'PNG');blob=encoded.getvalue();width,height=mark.size
            logo_ref='images/'+hashlib.sha256(blob).hexdigest()+'.png';(folder/logo_ref).write_bytes(blob)
            value['hero'][0]['titleLogo']={'artwork':h.BASE+logo_ref,'width':width,'height':height}
            inventory=h.image_inventory(value,folder)
            self.assertEqual(set(inventory['images']),set(jpegs.values()))
            self.assertEqual(set(inventory['titleLogos']),{logo_ref})
            raw=h.raw_json(value);sha=hashlib.sha256(raw).hexdigest();path='releases/'+sha+'/home.json'
            (folder/path).parent.mkdir(parents=True);(folder/path).write_bytes(raw)
            manifest=dict(inventory,version=sha,path=path)
            def check():
                (folder/'version.json').write_bytes(h.raw_json(manifest))
                with patch.object(h,'DOCS',Path(tmp)):h.validate_publication()
            check()
            manifest['titleLogos'][logo_ref]['width']=width+1
            with self.assertRaises(AssertionError):check()
            manifest['titleLogos'][logo_ref]['width']=width
            (folder/logo_ref).write_bytes(blob+b'corruption')
            with self.assertRaises(AssertionError):check()
            (folder/logo_ref).write_bytes(blob)
            self.assertIn(logo_ref,snapshot_files(manifest,'home'))
            current=h.publish_home(value,folder,100,manifest)
            self.assertEqual(current['images'],manifest['images'])
            self.assertNotIn('titleLogos',current)
            self.assertNotIn(logo_ref,snapshot_files(current,'home'))
            self.assertEqual((folder/path).read_bytes(),raw)
            expected=json.loads(raw);expected['hero'][0].pop('titleLogo')
            self.assertEqual(h.load(folder/current['path']),expected)
            with patch.object(h,'DOCS',Path(tmp)):h.validate_publication()

    def test_repeated_check_reuses_bytes_and_failed_fetch_keeps_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').mkdir();(root/'docs').mkdir()
            (root/'docs/catalog.json').write_text(json.dumps({'entries':[entry(n)for n in range(3)]}),encoding='utf8')
            buffer=io.BytesIO();Image.new('RGB',(1920,1080)).save(buffer,format='JPEG');blob=buffer.getvalue();calls=[]
            def fetch(url):
                if url in (h.SOURCE,h.ROOM,h.SEARCH):return page([item(n)for n in range(3)]).encode()
                calls.append(url);return blob
            import home_pages,home_titles,official_pages,home_copy
            with patch.object(h,'ROOT',root),patch.object(h,'DOCS',root/'docs'),patch.object(h,'fetch',fetch),patch.object(h.time,'time',return_value=1000000),patch.object(official_pages,'Pages',return_value=None),patch.object(home_pages,'kids_search_room',return_value='edt.item.kids'),patch.object(home_pages,'collect',side_effect=lambda catalog,api,image,**kwargs:h.collect(catalog,page([item(n)for n in range(3)]),image)),patch.object(home_titles,'enrich'),patch.object(home_copy,'process',side_effect=lambda v,*args,**kwargs:(v,{})):
                _,first=h.sync();self.assertEqual(len(calls),3)
                _,second=h.sync();self.assertEqual(len(calls),3);self.assertEqual(first['version'],second['version'])
                changed=io.BytesIO();Image.new('RGB',(1920,1080),'red').save(changed,format='JPEG');blob=changed.getvalue()
                with patch.object(h.time,'time',return_value=1000000+6*3600+1):
                    _,third=h.sync();self.assertEqual(len(calls),6);self.assertNotEqual(second['version'],third['version'])
                prior=(root/'docs/home/version.json').read_bytes()
                with patch.object(h,'fetch',side_effect=ValueError('unavailable')):
                    with self.assertRaises(ValueError):h.sync()
                self.assertEqual((root/'docs/home/version.json').read_bytes(),prior)
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
