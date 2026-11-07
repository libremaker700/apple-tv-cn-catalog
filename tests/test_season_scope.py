import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from season_scope import apply,rules,same_family_title

class SeasonScope(unittest.TestCase):
    def setUp(self):
        self.rule=json.loads((ROOT/'data/season-scopes.json').read_text(encoding='utf8'))['works']['prehistoric-planet-ice-age']
        r=self.rule
        self.entry={'slug':'prehistoric-planet-ice-age','en':r['englishTitle'],'kind':'series','officialIdentity':{'watchUrl':'https://tv.apple.com/us/show/old/'+r['showId'],'year':'2022'},'zh':{'sourceCheck':{'season':1,'year':'2022'}},'seasons':[{'season':1},{'season':2},{'season':3,'officialId':r['seasonId'],'showId':r['showId'],'year':'2025','releaseDate':r['releaseDate'],'artwork':'images/third.jpg','metadataStatus':'verified'}]}
    def test_scoped_series_uses_real_third_season_without_relabeling_earlier_ones(self):
        out=apply(self.entry,ROOT)
        self.assertEqual([s['season']for s in out['seasons']],[3])
        self.assertEqual(out['artworkSeasonNumber'],3);self.assertEqual(out['artworkSeasonYear'],'2025')
        self.assertEqual(out['zh']['douban_id'],'37457350');self.assertNotIn('sourceCheck',out['zh'])
        self.assertEqual(out['heroArtwork'],'images/third.jpg')
        self.assertEqual(out['artwork'],'images/third.jpg')
    def test_conflicting_ids_years_or_missing_season_fail_closed(self):
        for field,value in [('officialId','umc.cmc.wrong'),('year','2022'),('releaseDate','2022-05-23'),('showId','umc.cmc.wrong'),('metadataStatus','pending')]:
            row=copy.deepcopy(self.entry);row['seasons'][-1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):apply(row,ROOT)
    def test_parent_series_and_other_works_are_untouched(self):
        self.entry['slug']='prehistoric-planet';old=copy.deepcopy(self.entry)
        self.assertEqual(apply(self.entry,ROOT),old)

    def test_earlier_verified_seasons_use_the_parent_names_and_art(self):
        parent={'slug':self.rule['parentSlug'],'en':self.rule['parentTitle'],'kind':'series',
                'officialIdentity':copy.deepcopy(self.entry['officialIdentity']),'zh':{'title':'史前星球','aliases':['史前星球']},
                'seasons':[{'season':n,'officialId':f'umc.cmc.test{n}','showId':self.rule['showId'],
                            'year':str(2021+n),'releaseDate':f'{2021+n}-05-23','metadataStatus':'verified',
                            'artwork':f'images/season{n}.jpg','summary':f'第{n}季简介'} for n in (1,2)]}
        before=copy.deepcopy(parent)
        self.entry['zh'].update(title='史前星球：冰川时代',aliases=['史前星球'])
        out=apply(self.entry,ROOT,{parent['slug']:parent})
        self.assertEqual(parent,before)
        self.assertEqual([s['title'] for s in out['seasons']],['史前星球 第1季','史前星球 第2季','史前星球：冰川时代 第3季'])
        self.assertEqual([s['originalTitle'] for s in out['seasons']],['Prehistoric Planet','Prehistoric Planet','Prehistoric Planet: Ice Age'])
        self.assertEqual(out['seasons'][0]['aliases'],['史前星球'])
        self.assertNotIn('史前星球',out['seasons'][-1]['aliases'])
        self.assertEqual([s['artwork'] for s in out['seasons']],['images/season1.jpg','images/season2.jpg','images/third.jpg'])
        self.assertEqual(out['seasons'][1]['summary'],'第2季简介')
        self.assertEqual((out['seasonNumber'],out['releaseDate'],out['zh']['douban_id']),(3,'2025-11-26','37457350'))

        parent['seasons'][1]['showId']='umc.cmc.wrong'
        self.assertEqual([s['season'] for s in apply(out,ROOT,{parent['slug']:parent})['seasons']],[1,3])

    def test_only_configured_same_show_titles_share_season_packets(self):
        scopes=rules(ROOT)
        self.assertTrue(same_family_title(self.entry,self.rule['parentTitle'],scopes))
        self.assertFalse(same_family_title(dict(self.entry,slug='other'),self.rule['parentTitle'],scopes))
        self.assertFalse(same_family_title(dict(self.entry,officialId='umc.cmc.wrong'),self.rule['parentTitle'],scopes))
