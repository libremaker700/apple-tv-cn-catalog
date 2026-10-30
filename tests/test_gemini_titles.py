import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gemini_titles import GeminiTitles,extract_titles,redact

class Reply:
    def __init__(self,status,data):self.status_code=status;self.data=data
    def json(self):return self.data
class Session:
    def __init__(self,reply):self.reply=reply;self.calls=[]
    def post(self,url,**kwargs):self.calls.append((url,kwargs));return self.reply

class Gemini(unittest.TestCase):
    def test_extracts_mainland_title_not_other_works_in_answer(self):
        for text in ('大陆片名：《成为休曼》。\n导演拍过《健听女孩》。','大陆片名：《**成为休曼**》','这部电影在中国大陆的常用译名为《成为休曼》。'):
            self.assertEqual(extract_titles(text),['成为休曼'])
        for text in ('大陆片名：未核实。建议直译为《海曼》。','香港片名：《其他片名(港)》','这位导演拍过《健听女孩》。'):
            self.assertEqual(extract_titles(text),[])
    def test_requires_real_search_evidence_and_keeps_key_only_in_header(self):
        payload={'candidates':[{'content':{'parts':[{'text':'大陆片名：《成为休曼》。'}]},'groundingMetadata':{'webSearchQueries':['Being Heumann 中文名'],'groundingChunks':[{'web':{'title':'Being Heumann','uri':'https://www.apple.com/tv-pr/originals/being-heumann/'}}]}}]}
        session=Session(Reply(200,payload));client=GeminiTitles('private-key',session=session)
        result=client.search({'english_title':'Being Heumann','kind':'movie','year':'2026'})
        self.assertEqual(result['candidate_titles'],['成为休曼']);self.assertTrue(result['grounded'])
        self.assertNotIn('private-key',session.calls[0][0]);self.assertEqual(session.calls[0][1]['headers']['x-goog-api-key'],'private-key')
        del payload['candidates'][0]['groundingMetadata'];self.assertEqual(client.search({'english_title':'Being Heumann','kind':'movie','year':'2026'})['candidate_titles'],[])
    def test_errors_are_sanitized_without_retrying_quota_or_auth(self):
        session=Session(Reply(429,{'error':{'status':'RESOURCE_EXHAUSTED','message':'private-key'}}));client=GeminiTitles('private-key',session=session)
        result=client.search({'english_title':'Being Heumann','kind':'movie','year':'2026'})
        self.assertEqual(result['api_http'],429);self.assertNotIn('private-key',str(result));self.assertEqual(len(session.calls),1)
        self.assertEqual(redact({'text':'my-secret'},['my-secret'])['text'],'[REDACTED]')
if __name__=='__main__':unittest.main()
