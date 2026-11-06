import unittest,tempfile,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from home_copy import process
class HeadingTranslation(unittest.TestCase):
 def test_heading_translation_is_cached_without_any_hero(self):
  class Translator:
   model='fixture';calls=0
   def __init__(self,*args):pass
   def translate(self,rows):
    Translator.calls+=1;return {r['id']:'新的节日栏目'for r in rows}
  home={'works':[],'hero':[],'shelves':[{'id':'new','officialTitle':'New Holiday Shelf','title':'New Holiday Shelf','items':[{}]}]}
  with tempfile.TemporaryDirectory()as folder,patch('home_copy.Translator',Translator):
   a,_=process(home,Path(folder),'',100)
   b,_=process(home,Path(folder),'',101)
   self.assertEqual(a['shelves'][0]['title'],'新的节日栏目');self.assertEqual(b['shelves'][0]['title'],'新的节日栏目');self.assertEqual(Translator.calls,1)

 def test_copy_only_translates_headings_across_pages_without_refreshing_heroes(self):
  def shelf(title,display=None,layout='portrait'):
   return {'id':title,'officialTitle':title,'title':display or title,'layout':layout,'items':[{}]}

  home={'works':[],'hero':[{'officialId':'umc.cmc.home'}],
        'shelves':[shelf('Playful Learning'),shelf('New Releases'),shelf('Preserved Heading','现有中文栏目')],
        'pages':[{'hero':[{'officialId':'umc.cmc.kids'}],
                  'shelves':[shelf('Playful Learning'),shelf('The Great Outdoors',layout='landscape')]},
                 {'hero':[],'shelves':[shelf('Inspired by Real Life')]}]}
  translations={'Playful Learning':'快乐学习','The Great Outdoors':'探索大自然','Inspired by Real Life':'灵感源自真实生活'}
  with tempfile.TemporaryDirectory() as folder,patch('home_copy.Translator') as factory,patch('home_copy.extract') as extract:
   translator=factory.return_value
   translator.http=200
   translator.model='fixture'
   translator.translate.side_effect=lambda rows:{r['id']:translations[r['text']] for r in rows}
   root=Path(folder)
   first,report=process(home,root,'',100,showcases_only=True)
   second,cached_report=process(home,root,'',101,showcases_only=True)

  self.assertEqual(first,second)
  self.assertEqual([s['title'] for s in first['shelves']],['快乐学习','最新上线','现有中文栏目'])
  self.assertEqual([s['title'] for s in first['pages'][0]['shelves']],['快乐学习','探索大自然'])
  self.assertEqual(first['pages'][1]['shelves'][0]['title'],'灵感源自真实生活')
  self.assertEqual(first['shelves'][0]['officialTitle'],'Playful Learning')
  self.assertEqual(first['hero'],home['hero'])
  self.assertEqual(first['pages'][0]['hero'],home['pages'][0]['hero'])
  self.assertEqual(report['translated'],3)
  self.assertEqual(report['pending'],0)
  self.assertEqual(cached_report['headings'],[])
  translator.translate.assert_called_once()
  self.assertEqual([r['text'] for r in translator.translate.call_args.args[0]],list(translations))
  extract.assert_not_called()
