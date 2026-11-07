import copy,sys,unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from metadata_policy import POLICY,allowed_source,clean_zh,restore_display_titles
from title_sources import wiki_patch,Lookup
import catalog

class Policy(unittest.TestCase):
    def test_display_punctuation_preserves_identity_and_search_alias(self):
        watch_url='https://tv.apple.com/us/show/example/umc.cmc.example'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'data').mkdir()
            (root/'data/mainland-catalog.json').write_text(json.dumps({'records':{
                'example':{'title':'主标题：副标题','watchUrl':watch_url}
            }}),encoding='utf-8')
            work={'slug':'example','kind':'series','officialIdentity':{'watchUrl':watch_url},
                  'zh':{'title':'主标题副标题','aliases':['另一译名'],'searchSeason':2}}
            other=copy.deepcopy(work)
            other['officialIdentity']['watchUrl']+='2'
            different=copy.deepcopy(work)
            different['zh']['title']='主标题副标题2024'
            restore_display_titles([work,other,different],root)
            self.assertEqual(work['zh'],{'title':'主标题：副标题','aliases':['主标题：副标题','主标题副标题','另一译名'],'searchSeason':2})
            self.assertEqual(other['zh']['title'],'主标题副标题')
            self.assertEqual(different['zh']['title'],'主标题副标题2024')
            restore_display_titles([work],root)
            self.assertEqual(len(work['zh']['aliases']),3)

    def test_redirect_cannot_reopen_region_endpoint(self):
        class Reply:
            status_code=302
            headers={'Location':'https://tv.apple.com/tw/movie/x/id'}
            def close(self):pass
        with patch.object(catalog.requests,'get',return_value=Reply()) as get:
            with self.assertRaises(ValueError):catalog.get('https://www.apple.com/tv-pr/originals/x/')
        self.assertEqual(get.call_count,1);self.assertFalse(get.call_args.kwargs['allow_redirects'])
    def test_region_endpoints_are_rejected(self):
        for url in ('https://tv.apple.com/hk/movie/x/id','https://tv.apple.com/tw/show/x/id','https://www.apple.com/hk/tv-pr/x','https://example.tw/title'):
            self.assertFalse(allowed_source(url),url)
        for url in ('https://tv.apple.com/us/show/x/id','https://www.apple.com/tv-pr/originals/x/','https://movie.douban.com/subject/1/'):
            self.assertTrue(allowed_source(url),url)
    def test_old_metadata_cannot_be_relabelled(self):
        self.assertIsNone(clean_zh({'title':'区域名'}))
        self.assertIsNone(clean_zh({'title':'区域名','metadataPolicy':POLICY,'sources':['https://tv.apple.com/tw/show/x/id']}))
        value={'title':'国内片名','metadataPolicy':POLICY};self.assertEqual(clean_zh(value),value)
    def test_wiki_requires_explicit_mainland_name(self):
        ref={'english_title':'Example','kind':'movie','year':'2024'}
        page={'extract':'《区域片名》（Example）是一部2024年电影。','fullurl':'https://zh.wikipedia.org/wiki/Example'}
        self.assertIsNone(wiki_patch(ref,page,'now'))
        result=wiki_patch(ref,dict(page,mainland_title='国内片名'),'now')
        self.assertEqual(result['display_name_zh'],'国内片名');self.assertEqual(result['aliases_zh'],['国内片名'])
    def test_search_results_cannot_reopen_region_source(self):
        class Session:
            def get(self,*args,**kwargs):raise AssertionError('Forbidden request')
        lookup=Lookup('',Session())
        self.assertIsNone(lookup.verify_results({'english_title':'Example','kind':'movie','year':'2024'},[{'url':'https://tv.apple.com/hk/movie/x/id'}],'now'))
    def test_collector_only_reads_index_and_artwork(self):
        class Reply:
            content=b'image'
            def json(self):return {'results':{'originals':rows}}
        rows=[{'url':f'/tv-pr/originals/test-{i}/','title':f'Test {i}','showTypeKey':'films','releaseDateISOString':'2024-01-01T00:00:00Z','image':{'dirpath':'/tv-pr/shows-and-films/test/','name':str(i),'type':'jpg'}} for i in range(50)]
        previous={'entries':[{'slug':f'test-{i}','en':f'Test {i}','kind':'movie','version':'old','zh':{'title':'旧区域资料'}} for i in range(50)]}
        def get(url):
            self.assertTrue(url==catalog.INDEX or url.startswith('https://www.apple.com/tv-pr/shows-and-films/'),url)
            return Reply()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data').mkdir();(root/'docs').mkdir()
            (root/'data/seed.json').write_text(json.dumps({'entries':[]}));(root/'data/mainland-catalog.json').write_text(json.dumps({'records':{}}))
            with patch.object(catalog,'ROOT',root),patch.object(catalog,'DOCS',root/'docs'),patch.object(catalog,'get',get),patch.object(catalog,'save_image',lambda raw:'images/test.jpg'):
                value=catalog.collect(previous)
        self.assertEqual(value['metadataPolicy'],POLICY);self.assertTrue(all(e['zh'] is None for e in value['entries']))

    def test_optional_hero_timeout_keeps_valid_artwork_and_continues(self):
        from requests import Timeout
        rows=[{'url':f'/tv-pr/originals/test-{i}/','title':f'Test {i}','showTypeKey':'films',
               'image':{'dirpath':'/tv-pr/shows-and-films/test/','name':str(i),'type':'jpg'}} for i in range(50)]
        hero='https://is1-ssl.mzstatic.com/image/fixture.jpg'
        class Reply:
            content=b'fixture image'
            def json(self):return {'results':{'originals':rows}}
        def get(url):
            if url==hero:raise Timeout('fixture')
            return Reply()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data').mkdir();(root/'docs').mkdir()
            (root/'data/seed.json').write_text(json.dumps({'entries':[{'slug':'test-1','heroSource':hero}]}))
            (root/'data/mainland-catalog.json').write_text(json.dumps({'records':{}}))
            with patch.object(catalog,'ROOT',root),patch.object(catalog,'DOCS',root/'docs'),patch.object(catalog,'get',get):
                from io import BytesIO
                from PIL import Image
                image=BytesIO();Image.new('RGB',(8,8)).save(image,format='JPEG');Reply.content=image.getvalue()
                background=BytesIO();Image.new('RGB',(32,18)).save(background,format='JPEG')
                cached=catalog.save_image(background.getvalue())
                previous={'entries':[{'slug':'test-0','heroSource':hero,'heroArtwork':catalog.BASE+cached},
                                     {'slug':'test-2','heroSource':hero,'heroArtwork':catalog.BASE+'images/'+'a'*64+'.jpg'}]}
                entries=catalog.collect(previous)['entries']
        self.assertEqual(len(entries),50)
        self.assertEqual(entries[0]['heroArtwork'],cached)
        self.assertNotIn('heroArtwork',entries[1])
        self.assertNotIn('heroArtwork',entries[2])
        self.assertEqual(entries[1]['heroSource'],hero)
        self.assertEqual(entries[-1]['artwork'],'images/'+catalog.digest(Reply.content)+'.jpg')

if __name__=='__main__':unittest.main()
