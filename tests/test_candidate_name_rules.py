import copy,json,unittest
from candidate_name_rules import apply_kind,name_only
from douban_mobile import norm,mainland_name
class Rules(unittest.TestCase):
    def test_ampersand_and_combined_region_tags(self):
        self.assertEqual(norm('Now & Then'),norm('Now and Then'));self.assertFalse(mainland_name('中文名(港/台)'));self.assertTrue(mainland_name('中文名'))
    def test_single_special_matches_exact_date_but_has_no_score_or_douban_binding(self):
        ref={'kind':'movie','english_title':'A Carpool Karaoke Christmas','year':'2024','release_region':'US','release_date':'2024-12-15','candidate_subject_ids':['37161992'],'candidate_name_rule':{'policy':'single_episode_special'}}
        data={'type':'tv','episodes_count':1,'title':'兜风 KTV 过圣诞','original_title':ref['english_title'],'year':'2024','pubdate':['2024-12-15(美国)']}
        p=name_only(ref,data,'37161992','2026-11-02');self.assertEqual(p['name_only_scope'],'single_episode_special');self.assertNotIn('douban_id',p);self.assertNotIn('detailMetadata',p)
        self.assertIsNone(name_only(ref,dict(data,episodes_count=8),'37161992','now'));self.assertIsNone(name_only(ref,dict(data,pubdate=['2024-12-16(美国)']),'37161992','now'))
    def test_edition_requires_official_added_footage_and_matching_runtime(self):
        ref={'kind':'movie','english_title':'Napoleon: The Director’s Cut','year':'2024','candidate_subject_ids':['35224919'],'candidate_name_rule':{'policy':'director_cut','originalYear':2023,'platformYear':2024,'editionMinutes':206},'edition_added_minutes':48}
        data={'type':'movie','title':'拿破仑','original_title':'Napoleon','year':'2023','durations':['158分钟','206分钟(导演剪辑版)']}
        p=name_only(ref,data,'35224919','now');self.assertEqual(p['display_name_zh'],'拿破仑：导演剪辑版');self.assertEqual(p['aliases_zh'],['拿破仑：导演剪辑版']);self.assertNotIn('detailMetadata',p)
        self.assertIsNone(name_only(dict(ref,edition_added_minutes=5),data,'35224919','now'));self.assertIsNone(name_only(ref,dict(data,durations=['158分钟']),'35224919','now'))
    def test_movie_kind_binding_keeps_verified_series_untouched(self):
        url='https://tv.apple.com/us/movie/a/umc.cmc.abc';hint={'englishTitle':'Special','officialId':'umc.cmc.abc','candidateSubjectIds':['12345'],'canonicalKindEvidence':{'kind':'movie','officialUrl':url,'releaseDate':'2026-07-31','subjectId':'12345'}}
        work={'en':'Special','kind':'series','officialIdentity':{'watchUrl':url},'releaseDate':'2026-07-31','seasons':[{'season':1,'metadataStatus':'pending'}]};self.assertTrue(apply_kind(work,hint));self.assertEqual(work['kind'],'movie');self.assertEqual(work['seasons'],[])
        work.update(kind='series',seasons=[{'season':1,'metadataStatus':'verified'}]);self.assertFalse(apply_kind(work,hint))
