import unittest,tempfile,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from reviewed_names import apply
class ReviewedNames(unittest.TestCase):
 def test_idempotent_name_alias_year_keeps_synopsis(self):
  root=Path(__file__).resolve().parents[1];r=json.loads((root/'data/reviewed-name-aliases.json').read_text(encoding='utf-8'))['records'][0]
  w={'officialId':r['officialId'],'en':r['en'],'kind':'movie','slug':'home-test','zh':{'summary':'原有中文简介','summary_status':'translated_official'}}
  a=apply({'works':[w]},root,True);b=apply(a,root,True);self.assertEqual(a,b);self.assertEqual(a['works'][0]['zh']['summary'],'原有中文简介');self.assertEqual(a['works'][0]['zh']['searchYear'],1966);self.assertEqual(a['works'][0]['year'],'1966')
 def test_changed_identity_rejected(self):
  root=Path(__file__).resolve().parents[1];r=json.loads((root/'data/reviewed-name-aliases.json').read_text(encoding='utf-8'))['records'][0]
  with self.assertRaises(AssertionError):apply({'works':[{'officialId':r['officialId'],'en':'Unrelated','kind':'movie'}]},root,True)
