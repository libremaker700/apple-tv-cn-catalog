import copy,unittest
from reconcile_candidate_series import reconcile
class Reconcile(unittest.TestCase):
    def fixture(self):
        m={'entries':[{'slug':'farm','en':'Farm','kind':'series','artwork':'image','releaseDate':'2023-06-16','officialIdentity':{'watchUrl':''}}]}
        h={'works':[{'slug':'farm','en':'Farm','kind':'series','knownCatalog':True,'officialId':'umc.cmc.abc','watchUrl':'https://tv.apple.com/us/show/farm/umc.cmc.abc','year':'2022','seasons':[{'season':1,'year':'2022','releaseDate':'2022-06-10','metadataStatus':'verified','officialId':'umc.cmc.s1'},{'season':2,'year':'2023','releaseDate':'2023-06-16','metadataStatus':'verified','officialId':'umc.cmc.s2'}],'zh':{'title':'农场','name_status':'verified_title_sources','name_sources':[{'url':'https://movie.douban.com/subject/12345/'}],'detailMetadata':{'season':1}}}]};return m,h
    def test_exact_official_release_date_recovers_season_without_borrowing_rating(self):
        m,h=self.fixture();self.assertEqual(reconcile(m,h,['farm']),['farm']);w=m['entries'][0];self.assertEqual(w['artworkSeasonNumber'],2);self.assertEqual(w['zh']['nameOnlyScope'],'series_name_only');self.assertNotIn('detailMetadata',w['zh']);self.assertEqual(w['seasons'][0]['showId'],'umc.cmc.abc')
    def test_date_or_parent_conflict_and_existing_identity_are_not_overwritten(self):
        for change in [{'releaseDate':'2023-01-01'},{'en':'Other'},{'officialIdentity':{'watchUrl':'https://tv.apple.com/us/show/other/umc.cmc.other'}}]:
            m,h=self.fixture();m['entries'][0].update(change);self.assertEqual(reconcile(m,h,['farm']),[])
