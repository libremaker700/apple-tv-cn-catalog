import copy,sys,time,unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from mainland_names import public_sources,candidate_matches,recall_matches,source_count
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
        self.assertEqual(best['title'],'乙名称');self.assertEqual(best['libraries'],3);self.assertEqual(best['selection']['libraries'],2);self.assertEqual(best['selection']['requestedLibraries'],3);self.assertEqual({r['title']:r['libraries']for r in best['selection']['options']},{'乙名称':2,'甲名称':1})
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
    def test_year_suffix_needs_real_identity_and_same_season(self):
        ref={'kind':'series','year':'2026','season':1,'directors':'导演甲','actors':'演员甲,演员乙'}
        row=self.row('夜曲2026',vod_year='2026',vod_douban_id='',type_name='欧美剧',vod_director='导演甲',vod_actor='演员甲,演员乙')
        self.assertTrue(candidate_matches(ref,row,['夜曲']));self.assertFalse(candidate_matches(dict(ref,actors='演员甲'),row,['夜曲']));self.assertFalse(candidate_matches(dict(ref,season=2),row,['夜曲']))
    def test_movie_same_number_can_cross_one_release_year_but_conflicts_cannot(self):
        ref={'kind':'movie','year':'2018','douban_id':'27060077'};row=self.row('绿皮书',vod_year='2019',vod_douban_id='27060077')
        self.assertTrue(candidate_matches(ref,row,['绿皮书']));self.assertFalse(candidate_matches(ref,dict(row,vod_douban_id='27060078'),['绿皮书']));self.assertFalse(candidate_matches(ref,dict(row,vod_year='2021'),['绿皮书']))
    def test_recall_keeps_season_year_type_and_id_boundaries(self):
        ref={'kind':'series','year':'2026','season':2,'douban_id':'12345678'};row=self.row('甲名称第二季',type_name='欧美剧',vod_year='2026',vod_douban_id='')
        self.assertTrue(recall_matches(ref,row,['甲名称']))
        for change in ({'vod_name':'甲名称第一季'},{'vod_name':'甲名称'},{'vod_year':'2025'},{'type_name':''},{'type_name':'电影解说'},{'vod_douban_id':'87654321'},{'vod_name':'甲名称2026第二季'}):
            self.assertFalse(recall_matches(ref,dict(row,**change),['甲名称']),change)
    def test_documentary_series_can_be_recalled_without_cast_or_new_name_votes(self):
        ref={'kind':'series','year':'2025','season':1};row=self.row('越南：改变美国的战争',type_name='纪录片',vod_year='2025',vod_douban_id='')
        self.assertTrue(recall_matches(ref,row,['越南 改变美国的战争']));self.assertFalse(candidate_matches(ref,row,['越南 改变美国的战争']))
    def test_weak_alias_recall_cannot_outvote_strong_title(self):
        session=Mock()
        def get(url,**kw):
            row=self.row('已核验名称'if 'strong.'in url else'已核验别名',vod_douban_id='12345678'if 'strong.'in url else'')
            return Mock(status_code=200,json=lambda:{'list':[row]})
        session.get.side_effect=get
        best,_=public_sources({'kind':'movie','year':'2020','douban_id':'12345678'},['已核验名称','已核验别名'],[{'id':s,'url':'https://'+s+'.test/api'}for s in('strong','weak1','weak2')],session=session)
        self.assertEqual(best['libraries'],3);self.assertEqual(best['title'],'已核验名称');self.assertEqual(best['selection']['options'],[{'title':'已核验名称','libraries':1}])
