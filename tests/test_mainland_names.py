import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from mainland_names import candidate_matches,source_count,independent_name
class Identity(unittest.TestCase):
    def test_year_season_medium_and_full_name_are_kept(self):
        ref={'kind':'series','year':'2026','season':2};row={'vod_name':'正确剧名第二季','vod_year':'2026','type_name':'欧美剧'}
        self.assertTrue(candidate_matches(ref,row,['正确剧名']));self.assertFalse(candidate_matches(ref,dict(row,vod_name='正确剧名第三季'),['正确剧名']));self.assertFalse(candidate_matches(ref,dict(row,vod_year='2025'),['正确剧名']));self.assertFalse(candidate_matches(ref,dict(row,vod_name='正确剧名的另一部'),['正确剧名']))
    def test_only_nonempty_web_media_groups_count(self):self.assertEqual(source_count({'vod_play_url':'正片$https://example.invalid/a.m3u8$$$正片$javascript:evil$$$'}),1)
    def test_review_links_and_search_headlines_are_not_identity_proof(self):
        class Fake:pass
        self.assertIsNone(independent_name({'english_title':'Now & Then','year':'2022'},[{'title':'过去如今之后','url':'https://movie.douban.com/subject/123/reviews'}],Fake(),0))
