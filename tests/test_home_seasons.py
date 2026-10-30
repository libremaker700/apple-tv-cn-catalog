import copy, tempfile, unittest, sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import home_seasons

class HomeSeasons(unittest.TestCase):
    def test_new_season_is_added_and_failure_retains_previous_complete_set(self):
        home={'works':[{'officialId':'umc.cmc.show','kind':'series','watchUrl':'https://tv.apple.com/us/show/a/umc.cmc.show'}]}
        options=[{'season':1,'officialId':'umc.cmc.s1','officialEpisodeCount':8}]
        def get(url):
            class Response:
                text='fixture'
                def json(self):
                    number=2 if 's2/' in url else 1
                    return {'data':{'id':'umc.cmc.s'+str(number),'showId':'umc.cmc.show','seasonNumber':number,'releaseDate':('2026' if number==2 else '2025')+'-01-01'}}
            return Response()
        with tempfile.TemporaryDirectory() as directory,patch.object(home_seasons,'parse_show',side_effect=lambda *args:(copy.deepcopy(options),{},'')):
            root=Path(directory);(root/'data').mkdir()
            home_seasons.enrich(home,root,get,100000);self.assertEqual(len(home['works'][0]['seasons']),1)
            options.append({'season':2,'officialId':'umc.cmc.s2','officialEpisodeCount':2})
            home_seasons.enrich(home,root,get,130000);self.assertEqual([s['season']for s in home['works'][0]['seasons']],[1,2])
            home_seasons.enrich(home,root,lambda _:(_ for _ in ()).throw(ValueError()),160000)
            self.assertEqual([s['season']for s in home['works'][0]['seasons']],[1,2])
