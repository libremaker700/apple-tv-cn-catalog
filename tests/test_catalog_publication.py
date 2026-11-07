import io
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import catalog
from stage_pages import snapshot_files


class CatalogPublicationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        encoded = io.BytesIO()
        Image.new('RGB', (8, 8)).save(encoded, 'WEBP')
        image = encoded.getvalue()
        sha = catalog.digest(image)
        self.image_path = f'images/{sha}.webp'
        (self.folder / 'images').mkdir()
        (self.folder / self.image_path).write_bytes(image)

        entries = [{'slug': f'movie-{n}', 'en': f'Movie {n}', 'kind': 'movie',
                    'officialUrl': f'https://www.apple.com/tv-pr/originals/movie-{n}/',
                    'artwork': catalog.BASE + self.image_path} for n in range(50)]
        raw = catalog.raw_json({'metadataPolicy': catalog.POLICY, 'complete': True, 'entries': entries})
        version = catalog.digest(raw)
        release = f'releases/{version}/catalog.json'
        (self.folder / release).parent.mkdir(parents=True)
        (self.folder / release).write_bytes(raw)
        self.manifest = {'schema': 1, 'metadata_policy': catalog.POLICY, 'version': version,
                         'catalog_path': release, 'catalog_sha256': version, 'item_count': 50,
                         'image_count': 1, 'images': {self.image_path: {'sha256': sha, 'bytes': len(image)}}}

    def verify(self):
        (self.folder / 'version.json').write_bytes(catalog.raw_json(self.manifest))
        catalog.validate_publication(self.folder)

    def test_webp_is_validated_and_staged(self):
        self.verify()
        self.assertIn(self.image_path, snapshot_files(self.manifest, 'catalog'))

    def test_rejects_incorrect_inventory(self):
        self.manifest['image_count'] = 2
        with self.assertRaisesRegex(AssertionError, 'Invalid image inventory'):
            self.verify()
        self.manifest['image_count'] = 1
        self.manifest['images'][self.image_path]['sha256'] = '0' * 64
        with self.assertRaisesRegex(AssertionError, 'Invalid image inventory'):
            self.verify()

    def test_rejects_incorrect_item_count(self):
        self.manifest['item_count'] = 49
        with self.assertRaisesRegex(AssertionError, 'Invalid item count'):
            self.verify()
