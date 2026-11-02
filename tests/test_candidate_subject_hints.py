import copy,unittest,tempfile,json
from pathlib import Path
from douban_mobile import DoubanMobile,verify_payload
NOW='2026-11-02T00:00:00+00:00'
class Candidates(unittest.TestCase):
    def test_direct_subject_id_is_lookup_only_and_keeps_season_guard(self):
        class Pages:
            def json(self,url,**kw):
                if 'subject_suggest'in url:return []
                return {'id':'35599365','type':'tv','title':'中文名 第二季','original_title':'Doug Unplugs Season 2','year':'2021'}
        ref={'english_title':'Doug Unplugs','kind':'tv','year':'2021','season':2,'candidate_subject_ids':['35599365']}
        self.assertEqual(DoubanMobile(Pages()).lookup(ref,NOW)['display_name_zh'],'中文名')
        self.assertIsNone(DoubanMobile(Pages()).lookup(dict(ref,season=1),NOW))
    def test_chinese_alias_is_from_same_verified_response(self):
        ref={'english_title':'Sago Mini Friends','kind':'tv','year':'2024','season':3}
        data={'id':'37112671','type':'tv','title':'Sago Mini Friends Season 3','original_title':'Sago Mini Friends Season 3','year':'2024','aka':['Sago Mini 小小伙伴']}
        patch=verify_payload(ref,data,'37112671','tv',NOW);self.assertEqual(patch['display_name_zh'],'Sago Mini 小小伙伴');self.assertEqual(patch['detailMetadata']['subjectId'],'37112671')
        self.assertIsNone(verify_payload(dict(ref,season=2),data,'37112671','tv',NOW))
    def test_original_title_alias_is_bound_to_specific_candidate_id(self):
        ref={'english_title':'Awkwafina: The Unlikely Cook','kind':'tv','year':'2026','season':1,'candidate_subject_ids':['37862350'],'candidate_original_titles':['The Unlikely Cook with Awkwafina']}
        data={'id':'37862350','type':'tv','title':'奥卡菲娜：意想不到的厨师','original_title':'The Unlikely Cook with Awkwafina','year':'2026'}
        self.assertIsNotNone(verify_payload(ref,data,'37862350','tv',NOW))
        self.assertIsNone(verify_payload(dict(ref,candidate_subject_ids=['1234567']),data,'37862350','tv',NOW))
    def test_english_only_subject_does_not_become_chinese(self):
        ref={'english_title':'Not a Box','kind':'tv','year':'2025','season':1};data={'id':'37374251','type':'tv','title':'Not a Box','original_title':'Not a Box','year':'2025'}
        self.assertIsNone(verify_payload(ref,data,'37374251','tv',NOW));self.assertIsNotNone(verify_payload(ref,data,'37374251','tv',NOW,identity_only=True))
