import copy,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from metadata_policy import POLICY,allowed_source,clean_zh
from title_sources import wiki_patch,Lookup
import catalog

class Policy(unittest.TestCase):
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
        with patch.object(catalog,'get',get),patch.object(catalog,'save_image',lambda raw:'images/test.jpg'):
            value=catalog.collect(previous)
        self.assertEqual(value['metadataPolicy'],POLICY);self.assertTrue(all(e['zh'] is None for e in value['entries']))

if __name__=='__main__':unittest.main()
