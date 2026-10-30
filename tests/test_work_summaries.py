import sys,tempfile,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from work_summaries import key,attach,apply_home
class Summaries(unittest.TestCase):
 def test_hash_identity_and_changes(self):
  self.assertEqual(key('a','hello  world'),key('a','hello world'))
  self.assertNotEqual(key('a','hello'),key('b','hello'))
  self.assertNotEqual(key('a','hello'),key('a','changed'))
 def test_only_summary_fields(self):
  e={'en':'Fury','zh':{'title':'狂怒','aliases':['Fury']},'id':'kept','season':2};before=copy.deepcopy(e)
  attach(e,{'text':'战争中的坦克小队执行任务。','source':'https://tv.apple.com/us/movie/fury/umc.cmc.test','hash':'hash','original':'English'})
  self.assertEqual(e['id'],before['id']);self.assertEqual(e['zh']['title'],'狂怒');self.assertEqual(e['zh']['aliases'],['Fury']);self.assertEqual(e['season'],2)
 def test_empty_cache_old_schema(self):
  with tempfile.TemporaryDirectory()as t:self.assertEqual(apply_home({'schema':1},Path(t)),{'schema':1})
