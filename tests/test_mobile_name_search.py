import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from douban_mobile import DoubanMobile

class MobileSearch(unittest.TestCase):
    def test_empty_suggestions_use_movie_links_and_still_verify_original_year(self):
        class Pages:
            def __init__(self):self.ids=[]
            def get(self,url,**kw):return '<a href="/book/subject/99999/">Book</a><a href="/movie/subject/35883780/">Untrusted label</a>'
            def json(self,url,**kw):
                if 'subject_suggest'in url:return []
                self.ids.append(url)
                return {'id':'35883780','type':'movie','title':'史努比特辑：将爱献给父母','original_title':'To Mom (And Dad), with Love','year':'2022','aka':[],'rating':{'value':0}}
        pages=Pages();ref={'english_title':'To Mom (And Dad), With Love','kind':'movie','year':'2022'}
        result=DoubanMobile(pages).lookup(ref,'2026-11-02T00:00:00+00:00')
        self.assertEqual(result['display_name_zh'],'史努比特辑：将爱献给父母')
        self.assertEqual(len(pages.ids),1);self.assertNotIn('99999',pages.ids[0])
        self.assertEqual(result['rating_status'],'NO_RATING');self.assertNotIn('douban_rating',result)
        self.assertIsNone(DoubanMobile(Pages()).lookup(dict(ref,year='2021'),'2026-11-02T00:00:00+00:00'))
    def test_unavailable_suggestions_do_not_disable_independent_public_mobile_search(self):
        class Pages:
            def json(self,url,**kw):return {}if 'subject_suggest'in url else{'id':'35239017','type':'movie','title':'花生在太空：阿波罗十号的秘密','original_title':'Peanuts in Space: Secrets of Apollo 10','year':'2019','aka':[]}
            def get(self,url,**kw):return '<a href="/movie/subject/35239017/">Candidate</a>'
        ref={'english_title':'Peanuts in Space: Secrets of Apollo 10','kind':'movie','year':'2019'}
        self.assertIsNotNone(DoubanMobile(Pages()).lookup(ref,'2026-11-02T00:00:00+00:00'))
