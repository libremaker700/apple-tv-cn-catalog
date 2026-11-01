import copy,sys,time,unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from mainland_names import public_sources,candidate_matches,source_count
from source_votes import apply_selection

class Votes(unittest.TestCase):
    def row(self,title='甲名称',**fields):
        return dict({'vod_id':'1','vod_name':title,'vod_year':'2020','type_name':'剧情片','vod_douban_id':'12345678','vod_play_from':'ffm3u8','vod_play_url':'正片$https://example.test/a.m3u8'},**fields)
    def test_unique_libraries_beat_many_lines_and_same_library_records(self):
        providers=[{'id':'a','url':'https://a.test/api'},{'id':'b','url':'https://b.test/api'},{'id':'c','url':'https://c.test/api'},{'id':'mirror','url':'https://a.test/api/'}];session=Mock()
        def get(url,params,**kw):
            many=self.row(vod_play_from='$$$'.join(['ffm3u8']*12),vod_play_url='$$$'.join(['正片$https://example.test/a.m3u8']*12))
            rows=[many,self.row(vod_id='2')]if url.startswith('https://a.')else[self.row('乙名称')]
            return Mock(status_code=200,json=lambda:{'list':rows})
        session.get.side_effect=get
        best,_=public_sources({'kind':'movie','year':'2020','douban_id':'12345678'},['甲名称','乙名称'],providers,session=session)
        self.assertEqual(best['title'],'乙名称');self.assertEqual(best['libraries'],2);self.assertEqual(best['selection']['requestedLibraries'],3);self.assertEqual({r['title']:r['libraries']for r in best['selection']['options']},{'乙名称':2,'甲名称':1})
    def test_conflict_season_year_and_unknown_medium_are_not_votes(self):
        ref={'kind':'series','year':'2020','season':1,'douban_id':'12345678'};good=self.row('甲名称第一季',type_name='欧美剧');self.assertTrue(candidate_matches(ref,good,['甲名称']))
        for field,value in [('vod_name','甲名称第二季'),('vod_year','2021'),('vod_douban_id','87654321'),('type_name','')]:self.assertFalse(candidate_matches(ref,dict(good,**{field:value}),['甲名称']))
    def test_web_and_trailer_do_not_count(self):
        self.assertEqual(source_count(self.row(vod_play_from='ruyi',vod_play_url='正片$https://example.test/share.mp4')),0)
        self.assertEqual(source_count(self.row(vod_play_url='预告$https://example.test/1.m3u8#正片$https://example.test/page')),0)
    def test_cache_selection_preserves_aliases_and_public_evidence_has_no_provider(self):
        work={'zh':{'title':'豆瓣旧名称','aliases':['别名']}};selection={'policy':'library-votes-v1','title':'片库常用名称','libraries':3,'options':[{'title':'片库常用名称','libraries':3}]};apply_selection(work,selection)
        self.assertEqual(work['zh']['title'],'片库常用名称');self.assertIn('豆瓣旧名称',work['zh']['aliases']);self.assertNotIn('provider',str(work['zh']['nameSelection']))
    def test_animation_movie_needs_verified_subject_when_source_type_is_ambiguous(self):
        row=self.row('动画别名',type_name='欧美动漫');ref={'kind':'movie','year':'2020','douban_id':'12345678'};self.assertTrue(candidate_matches(ref,row,['豆瓣名称']));self.assertFalse(candidate_matches(dict(ref,douban_id='87654321'),row,['动画别名']))
