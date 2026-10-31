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

 def test_canonical_id_and_pr_fallback(self):
  from work_summaries import source_id
  self.assertEqual(source_id({'officialIdentity':{'watchUrl':'https://tv.apple.com/us/movie/fury/umc.cmc.test?ctx_brand=foo'}}),'umc.cmc.test')
  self.assertEqual(source_id({'slug':'test','officialUrl':'https://www.apple.com/tv-pr/originals/test/'}),'pr:test')

 def test_legacy_chinese_is_retranslated_and_official_rating_year_are_shared(self):
  from title_lookup import dump,read
  from work_summaries import run,apply_main
  class API:
   def get(self,kind,identity):return {'id':identity,'type':'Movie','title':'Exact','description':'Official about description','contentRating':'TV-MA','releaseDate':1648771200000}
  class Translator:
   usage={};model='test';calls=0
   def translate(self,rows):self.calls+=1;return {r['id']:'严格依据官网原文的中文简介。'for r in rows}
  with tempfile.TemporaryDirectory()as t:
   root=Path(t);identity='umc.cmc.test';url='https://tv.apple.com/us/movie/exact/'+identity;main={'entries':[{'slug':'exact','en':'Exact','kind':'movie','officialIdentity':{'watchUrl':url},'zh':{'summary':'不对应当前官网的旧中文简介'}}]}
   dump(root/'docs/catalog.json',main);dump(root/'docs/home/home.json',{'works':[]});k=key(identity,'Official about description');dump(root/'data/work-summary-cache.json',{'records':{k:{'text':'不对应的旧中文简介','method':'existing_chinese'}},'works':{}})
   translator=Translator();run(root,API(),translator,100);run(root,API(),translator,101)
   self.assertEqual(translator.calls,1);zh=apply_main(main,root)['entries'][0]['zh'];self.assertEqual(zh['summary'],'严格依据官网原文的中文简介。');self.assertEqual(zh['contentRating'],'TV-MA');self.assertEqual(zh['officialReleaseYear'],2022)
 def test_only_official_display_rating_survives(self):
  from official_pages import slim_item
  self.assertEqual(slim_item({'rating':{'displayName':'TV-MA','value':600}})['contentRating'],'TV-MA')
  self.assertNotIn('contentRating',slim_item({'rating':{'displayName':'invented'}}));self.assertNotIn('contentRating',slim_item({'rating':'8.5'}))
