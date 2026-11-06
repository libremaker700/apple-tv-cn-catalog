import io,tempfile,unittest,hashlib
from pathlib import Path
from PIL import Image
from poster_logos import render,PosterLogos,BASE
class Logos(unittest.TestCase):
    def blob(self,mode,size,color,fmt):
        b=io.BytesIO();Image.new(mode,size,color).save(b,fmt);return b.getvalue()
    def test_composition_preserves_dimensions_top_image_and_visible_logo(self):
        base=self.blob('RGB',(400,600),(180,180,180),'JPEG');logo=Image.new('RGBA',(470,140));logo.paste((255,0,0,255),(30,20,440,120));b=io.BytesIO();logo.save(b,'PNG')
        raw=render(base,b.getvalue())
        with Image.open(io.BytesIO(raw))as im:
            self.assertEqual(im.size,(400,600));self.assertEqual(im.format,'JPEG');self.assertLess(abs(im.getpixel((200,50))[0]-180),3);self.assertGreater(im.getpixel((200,452))[0],220);self.assertLess(im.getpixel((200,452))[1],30)
    def test_wide_showcase_keeps_full_width_and_title_treatment_at_lower_left(self):
        base=self.blob('RGB',(1920,720),(180,180,180),'JPEG')
        logo=Image.new('RGBA',(470,140));logo.paste((255,0,0,255),(30,20,440,120));b=io.BytesIO();logo.save(b,'PNG')
        with Image.open(io.BytesIO(render(base,b.getvalue())))as im:
            self.assertEqual(im.size,(1920,720))
            self.assertLess(abs(im.getpixel((960,100))[0]-180),3)
            self.assertGreater(im.getpixel((170,530))[0],220)
            self.assertLess(im.getpixel((170,530))[1],30)

    def test_opaque_or_non_image_logo_is_rejected(self):
        base=self.blob('RGB',(400,600),'gray','JPEG')
        for logo in [b'not a logo',self.blob('RGB',(470,140),'white','PNG')]:
            with self.assertRaises((ValueError,OSError)):render(base,logo)
    def test_reposition_uses_clean_official_background_and_cache(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);folder=root/'docs/home/images';folder.mkdir(parents=True);(root/'data').mkdir()
            base=self.blob('RGB',(640,800),(180,180,180),'JPEG');name=hashlib.sha256(base).hexdigest()+'.jpg';(folder/name).write_bytes(base)
            logo=Image.new('RGBA',(470,140));logo.paste((255,0,0,255),(30,20,430,120));encoded=io.BytesIO();logo.save(encoded,'PNG')
            calls=[];renderer=PosterLogos(root,lambda url:(calls.append(url)or encoded.getvalue()))
            row={'artwork':BASE+'images/'+name,'officialId':'umc.cmc.test','width':640,'height':800}
            url='https://is1-ssl.mzstatic.com/image/thumb/example/470x140bb.png'
            original=dict(row,**renderer.apply(row,url))
            raised=renderer.reposition(original,True)
            self.assertNotEqual(raised['artwork'],original['artwork'])
            with Image.open(root/'docs/home'/raised['artwork'].removeprefix(BASE))as im:
                self.assertEqual(im.size,(640,800))
                self.assertLess(im.getpixel((100,530))[1],30)
                self.assertGreater(im.getpixel((100,665))[1],160)
            self.assertEqual(renderer.reposition(dict(raised,officialId=row['officialId']),False)['artwork'],original['artwork'])
            self.assertEqual(len(calls),2)
            with self.assertRaises(ValueError):renderer.reposition(dict(original,officialId='umc.cmc.other'),True)
    def test_cache_is_bound_to_background_and_logo_and_not_composited_twice(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);folder=root/'docs/home/images';folder.mkdir(parents=True);(root/'data').mkdir()
            base=self.blob('RGB',(400,600),'gray','JPEG');name=hashlib.sha256(base).hexdigest()+'.jpg';(folder/name).write_bytes(base)
            calls=[];logo=self.blob('RGBA',(470,140),(255,255,255,128),'PNG')
            renderer=PosterLogos(root,lambda url:(calls.append(url)or logo));row={'artwork':BASE+'images/'+name,'officialId':'umc.cmc.abc'};url='https://is1-ssl.mzstatic.com/image/thumb/example/470x140bb.png'
            a=renderer.apply(row,url);b=renderer.apply(row,url);self.assertEqual(a,b);self.assertEqual(len(calls),1);self.assertEqual(a['logoTreatment'],'official-composite-v1');self.assertNotEqual(a['artwork'],row['artwork'])
            with self.assertRaises(ValueError):renderer.apply(row,'https://example.com/logo.png')
