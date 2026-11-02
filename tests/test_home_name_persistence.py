import copy,tempfile,unittest
from pathlib import Path
from home_titles import remember,enrich
class Persistence(unittest.TestCase):
    def test_verified_home_name_survives_refresh_with_identity_guards(self):
        w={'officialId':'umc.cmc.abc','en':'Example','year':'2026','kind':'series','zh':{'metadataPolicy':'mainland-v1','title':'中文名','name_status':'verified_title_sources','name_sources':[{'type':'douban_mobile_identity','url':'https://movie.douban.com/subject/12345/'}]}}
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);(root/'data').mkdir();remember({'works':[w]},root)
            for change,expected in [({},True),({'year':'2025'},False),({'kind':'movie'},False),({'en':'Other'},False),({'officialId':'umc.cmc.other'},False)]:
                fresh={k:copy.deepcopy(v)for k,v in w.items()if k!='zh'};fresh.update(change);enrich({'works':[fresh]},root,0)
                self.assertEqual(fresh.get('zh',{}).get('title')=='中文名',expected)
