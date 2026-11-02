import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from plex_names import verify
from season_sync import parse_show
from home_seasons import bind_display_season
from test_seasons import page,SHOW

def doc(name='The Wonder Pets!',year='2006',typ='TVSeries',actors=('A','B')):
    value={'@graph':[{'@type':typ,'name':name,'actor':[{'name':a}for a in actors]}]}
    return '<title>Watch '+name+' ('+year+')</title><script type="application/ld+json">'+json.dumps(value)+'</script>'
class PlexIdentity(unittest.TestCase):
    def test_locale_pair_proves_name_but_never_douban_rating_or_packet(self):
        ref={'english_title':'Wonder Pets','year':'2006','kind':'tv','season':1};url='https://watch.plex.tv/zh/show/the-wonder-pets'
        result=verify(ref,url,doc('神奇宠物救援队'),doc(),'now')
        self.assertEqual(result['display_name_zh'],'神奇宠物救援队');self.assertNotIn('detailMetadata',result);self.assertNotIn('douban_rating',result)
        for en in [doc(year='2007'),doc(name='Wonder Woman'),doc(typ='Movie'),doc(actors=('A',))]:self.assertIsNone(verify(ref,url,doc('神奇宠物救援队'),en,'now'))
        self.assertIsNone(verify(dict(ref,season=2),url,doc('神奇宠物救援队'),doc(),'now'))
    def test_partial_official_season_list_keeps_eighth_number(self):
        rows,_,_=parse_show(page((8,)),SHOW,allow_partial=True);self.assertEqual([r['season']for r in rows],[8])
        with self.assertRaises(ValueError):parse_show(page((8,)),SHOW)
        work={'year':'2026','releaseDate':'2026-02-27','seasons':[{'season':8,'year':'2026','releaseDate':'2026-02-27','metadataStatus':'verified'}]}
        bind_display_season(work);self.assertEqual(work['artworkSeasonNumber'],8)
