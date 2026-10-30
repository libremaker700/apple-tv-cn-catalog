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

 def test_repeated_update_and_shared_identity(self):
  from title_lookup import dump,read
  from work_summaries import run,apply_main,apply_home
  class API:
   def __init__(self):self.text='English synopsis'
   def get(self,kind,identity):return {'id':identity,'type':'Movie','title':'Fury','description':self.text}
  class Translator:
   def __init__(self):self.calls=0;self.usage={};self.model='test'
   def translate(self,rows):self.calls+=1;return {r['id']:'坦克小队在战场上执行危险任务。'for r in rows}
  with tempfile.TemporaryDirectory()as t:
   root=Path(t);identity='umc.cmc.test';url='https://tv.apple.com/us/movie/fury/'+identity
   main={'entries':[{'slug':'fury','en':'Fury','kind':'movie','officialIdentity':{'watchUrl':url}}]}
   home={'works':[{'slug':'fury','en':'Fury','kind':'movie','officialId':identity,'watchUrl':url}]}
   dump(root/'docs/catalog.json',main);dump(root/'docs/home/home.json',home)
   api=API();translator=Translator();a=run(root,api,translator,100);b=run(root,api,translator,101)
   self.assertEqual(translator.calls,1);self.assertEqual(b['cacheHits'],1)
   self.assertEqual(apply_main(main,root)['entries'][0]['zh']['summary'],apply_home(home,root)['works'][0]['zh']['summary'])
   api.text='Changed English synopsis';run(root,api,translator,102);self.assertEqual(translator.calls,2)
