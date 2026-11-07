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

 def test_legacy_chinese_is_retranslated_and_only_year_is_shared(self):
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
   main['entries'][0]['zh']['contentRating']='TV-MA'
   self.assertEqual(translator.calls,1);zh=apply_main(main,root)['entries'][0]['zh'];self.assertEqual(zh['summary'],'严格依据官网原文的中文简介。');self.assertNotIn('contentRating',zh);self.assertEqual(zh['officialReleaseYear'],2022)
   self.assertNotIn('contentRating',read(root/'data/work-summary-cache.json',{})['works'][identity])
 def test_official_detail_rating_is_discarded(self):
  from official_pages import slim_item
  self.assertNotIn('contentRating',slim_item({'rating':{'displayName':'TV-MA','value':600}}))
  self.assertNotIn('contentRating',slim_item({'rating':{'displayName':'invented'}}));self.assertNotIn('contentRating',slim_item({'rating':'8.5'}))

 def test_work_pending_counts_current_valid_text_and_retries(self):
  from title_lookup import dump
  from work_summaries import run,apply_home
  class API:
   def get(self,kind,identity):
    if identity=='umc.cmc.new':raise OSError('Temporary Apple failure')
    return {'id':identity,'type':'Movie','description':'Changed official work synopsis'}
  class Translator:
   usage={};model='test';http=503;fail=True
   def __init__(self):self.rows=[]
   def translate(self,rows):
    self.rows.extend(rows)
    if self.fail:raise OSError('Temporary translation failure')
    return {r['id']:'当前作品对应的中文简介。' for r in rows}
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)
   new='umc.cmc.new';old='umc.cmc.old'
   def work(identity):
    return {'en':identity,'kind':'movie','officialId':identity,'watchUrl':'https://tv.apple.com/us/movie/item/'+identity}
   home={'works':[work(old),dict(work(new),summaryEn='Verified home synopsis')]}
   old_translation={'text':'当前已显示的旧版官方简介。','source':work(old)['watchUrl'],'original':'Old original','hash':'old'}
   dump(root/'docs/catalog.json',{'entries':[]})
   dump(root/'docs/home/home.json',home)
   dump(root/'data/work-summary-cache.json',{'records':{},'works':{old:old_translation,new:{'officialReleaseYear':2026},'retired':old_translation}})
   translator=Translator()
   report=run(root,API(),translator,100,limit=1)
   self.assertEqual([row['id'] for row in translator.rows],[new])
   self.assertEqual((report['works'],report['ready'],report['pending'],report['sourceErrors']),(2,1,1,1))
   self.assertEqual(apply_home(home,root)['works'][0]['zh']['summary'],old_translation['text'])
   self.assertEqual(run(root,API(),translator,101,limit=0)['pending'],1)
   translator.fail=False
   report=run(root,API(),translator,100+6*3600,limit=1)
   self.assertEqual((report['ready'],report['pending']),(2,0))
   self.assertEqual(translator.rows[-1]['text'],'Verified home synopsis')
   self.assertIn('中文简介',apply_home(home,root)['works'][1]['zh']['summary'])

 def test_only_exact_season_copy_is_translated_and_published(self):
  from title_lookup import dump
  from work_summaries import run,apply_main
  show='umc.cmc.testshow'
  class API:
   def get(self,kind,identity):return {'id':identity,'type':'Show','description':'Official show synopsis'}
  class Translator:
   usage={};model='test';http=200
   def __init__(self):self.rows=[]
   def translate(self,rows):
    self.rows.extend(rows)
    return {r['id']:'官方本季的中文故事简介。' for r in rows}
  def season(number):
   return {'officialId':f'umc.cmc.season{number}','showId':show,'season':number,'year':'2024',
           'releaseDate':f'2024-0{number}-01','metadataStatus':'verified','summary':'','summaryPending':True}
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)
   official='https://tv.apple.com/us/show/item/'+show
   rows=[season(n) for n in range(1,6)]
   rows[4].update(summary='已核验的豆瓣本季简介。',summarySource='https://movie.douban.com/subject/123456/')
   item={'en':'Item','kind':'series','officialIdentity':{'watchUrl':official},'seasons':rows}
   main={'entries':[item]}
   dump(root/'docs/catalog.json',main)
   dump(root/'docs/home/home.json',{'works':[]})
   cached=[dict(s,summaryOriginal='Official exact seasonal synopsis') for s in rows]
   cached[0]['summaryOriginal']='Official show synopsis'
   cached[2]['releaseDate']='2024-03-02'
   cached[3]['showId']='umc.cmc.wrongshow'
   dump(root/'data/season-cache.json',{'shows':{'item':{'showId':show,'seasons':cached}}})
   translator=Translator()
   report=run(root,API(),translator,100,season_limit=0)
   self.assertEqual((report['seasonCandidates'],report['seasonPending']),(1,1))
   report=run(root,API(),translator,101)
   self.assertEqual([r['id'] for r in translator.rows],[show,rows[1]['officialId']])
   self.assertEqual((report['seasonTranslated'],report['seasonPending']),(1,0))
   published=apply_main(main,root)['entries'][0]['seasons']
   self.assertEqual([row['summary'] for row in published],['','官方本季的中文故事简介。','','','已核验的豆瓣本季简介。'])
   self.assertTrue(published[1]['summarySource'].endswith('/'+rows[1]['officialId']+'?showId='+show))
   self.assertFalse(published[1]['summaryPending'])
   self.assertTrue(published[0]['summaryPending'])
