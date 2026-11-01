import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from season_scope import apply

class SeasonScope(unittest.TestCase):
    def setUp(self):
        self.rule=json.loads((ROOT/'data/season-scopes.json').read_text())['works']['prehistoric-planet-ice-age']
        r=self.rule
        self.entry={'slug':'prehistoric-planet-ice-age','en':r['englishTitle'],'kind':'series','officialIdentity':{'watchUrl':'https://tv.apple.com/us/show/old/'+r['showId'],'year':'2022'},'zh':{'sourceCheck':{'season':1,'year':'2022'}},'seasons':[{'season':1},{'season':2},{'season':3,'officialId':r['seasonId'],'showId':r['showId'],'year':'2025','releaseDate':r['releaseDate'],'artwork':'images/third.jpg','metadataStatus':'verified'}]}
    def test_scoped_series_uses_real_third_season_without_relabeling_earlier_ones(self):
        out=apply(self.entry,ROOT)
        self.assertEqual([s['season']for s in out['seasons']],[3])
        self.assertEqual(out['artworkSeasonNumber'],3);self.assertEqual(out['artworkSeasonYear'],'2025')
        self.assertEqual(out['zh']['douban_id'],'37457350');self.assertNotIn('sourceCheck',out['zh'])
        self.assertEqual(out['heroArtwork'],'images/third.jpg')
    def test_conflicting_ids_years_or_missing_season_fail_closed(self):
        for field,value in [('officialId','umc.cmc.wrong'),('year','2022'),('releaseDate','2022-05-23'),('showId','umc.cmc.wrong'),('metadataStatus','pending')]:
            row=copy.deepcopy(self.entry);row['seasons'][-1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):apply(row,ROOT)
    def test_parent_series_and_other_works_are_untouched(self):
        self.entry['slug']='prehistoric-planet';old=copy.deepcopy(self.entry)
        self.assertEqual(apply(self.entry,ROOT),old)
