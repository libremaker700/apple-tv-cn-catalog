import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from api_accounts import accounts,SearchAccounts
from home_copy import Translator
class Response:
    def __init__(self,status,rows=()):self.status_code=status;self.rows=rows
    def json(self):return {'results':{'web':list(self.rows)}}
class Session:
    def __init__(self,statuses):self.statuses=iter(statuses);self.calls=[]
    def post(self,*args,**kwargs):self.calls.append(kwargs);return Response(next(self.statuses))
class Accounts(unittest.TestCase):
    def test_typo_names_are_supported_and_duplicate_values_are_not_retried(self):
        with patch.dict('os.environ',{'YDC_API_KEYI_1':'first','YDC_API_KEY_2':'first','YDC_API_KEY_3':'third'},clear=True):self.assertEqual(len(accounts('YDC')),2)
    def test_auth_quota_rate_and_temporary_failures_move_to_another_account(self):
        for status in (401,402,403,429,500):
            session=Session([status,200]);pool=SearchAccounts(session,{'ydc':[('one','a'),('two','b')]})
            self.assertEqual(pool.search('title')[1],'ok');self.assertEqual(len(session.calls),2)
    def test_empty_success_does_not_rotate_and_parameter_failure_is_not_a_bad_key(self):
        for status in (200,400,404,422):
            session=Session([status]);pool=SearchAccounts(session,{'ydc':[('one','a'),('two','b')]});pool.search('title');self.assertEqual(len(session.calls),1);self.assertEqual(pool.disabled,set())
    def test_budget_stops_before_network(self):
        session=Session([]);pool=SearchAccounts(session,{'ydc':[('one','a')]},lambda:False);self.assertEqual(pool.search('x')[1],'budget_exhausted');self.assertEqual(session.calls,[])
    def test_translation_uses_its_own_accounts_and_rejects_bad_output(self):
        class Fake(Translator):
            def _translate_once(self,rows):
                self.http=403 if self.key=='first' else 200
                if self.http==403:raise ValueError('translation_http_403')
                return {'test':'中文'}
        with patch.dict('os.environ',{'GEMINI_API_KEY_1':'first','GEMINI_API_KEY_2':'second','YDC_API_KEY_1':'search-key'},clear=True):
            client=Fake('');self.assertEqual(client.translate([]),{'test':'中文'});self.assertEqual(len(client.account_attempts),2)
class GenreTranslation(unittest.TestCase):
    def test_new_genres_translate_once_and_do_not_change_title(self):
        import tempfile
        from genre_translation import apply
        class Fake:
            calls=0
            def translate(self,rows):self.calls+=1;return {r['id']:'实验题材'for r in rows}
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);main={'entries':[{'en':'Exact Original','genres':['Crime','NewExperimentalGenre']}]};home={'works':[]};fake=Fake()
            apply(main,home,root,fake);apply(main,home,root,fake);self.assertEqual(fake.calls,1);self.assertEqual(main['entries'][0]['genresZh'],['犯罪','实验题材']);self.assertEqual(main['entries'][0]['en'],'Exact Original')
