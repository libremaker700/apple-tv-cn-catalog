import io,unittest
from PIL import Image
from home_sync import normalize_image
class Rounding(unittest.TestCase):
    def blob(self,w,h,fmt='JPEG'):
        out=io.BytesIO();Image.new('RGB',(w,h)).save(out,fmt);return out.getvalue()
    def test_exact_bytes_are_preserved(self):
        raw=self.blob(960,540);self.assertEqual(normalize_image(raw,960,540),raw)
    def test_one_pixel_official_rounding_is_normalized(self):
        for size in [(959,540),(960,539),(961,540)]:
            raw=normalize_image(self.blob(*size),960,540)
            with Image.open(io.BytesIO(raw))as im:self.assertEqual(im.size,(960,540));self.assertEqual(im.format,'JPEG')
    def test_arbitrary_or_wrong_format_is_rejected(self):
        for raw in [self.blob(480,270),self.blob(960,540,'PNG'),b'not an image']:
            with self.assertRaises((ValueError,OSError)):normalize_image(raw,960,540)
