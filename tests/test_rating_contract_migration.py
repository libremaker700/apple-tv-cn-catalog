import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from migrate_detail_contract import clean,run

class RatingMigration(unittest.TestCase):
    def test_removes_only_rating_counts_recursively(self):
        original={'title':'作品','rating':8.5,'ratingCount':123,'detailSeasons':[{'rating':7.2,'douban_rating_count':9}],'libraries':3,'routes':4}
        value=clean(original)
        self.assertEqual(value,{'title':'作品','rating':8.5,'detailSeasons':[{'rating':7.2}],'libraries':3,'routes':4})
        self.assertIn('ratingCount',original)
    def test_active_files_migrate_without_rewriting_immutable_release(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);(root/'data').mkdir();(root/'docs/releases').mkdir(parents=True)
            old='{"rating":8.5,"ratingCount":10}'
            (root/'data/detail-metadata-cache.json').write_text(old)
            (root/'docs/releases/old.json').write_text(old)
            run(root,publish_changes=False)
            self.assertEqual(json.loads((root/'data/detail-metadata-cache.json').read_text()),{'rating':8.5})
            self.assertEqual((root/'docs/releases/old.json').read_text(),old)
