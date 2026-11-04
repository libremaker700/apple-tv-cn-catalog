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
