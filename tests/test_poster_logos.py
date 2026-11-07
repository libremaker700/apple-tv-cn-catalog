import io,tempfile,unittest,hashlib
from pathlib import Path
from PIL import Image,PngImagePlugin
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
            legacy=render(base,encoded.getvalue(),featured_bottom=88)
            legacy_name=hashlib.sha256(legacy).hexdigest()+'.jpg';(folder/legacy_name).write_bytes(legacy)
            row={'artwork':BASE+'images/'+legacy_name,'officialId':'umc.cmc.test','width':640,'height':800}
            url='https://is1-ssl.mzstatic.com/image/thumb/example/470x140bb.png'
            archive=io.BytesIO();png_info=PngImagePlugin.PngInfo();png_info.add_text('archive','fixture');logo.save(archive,'PNG',pnginfo=png_info)
            self.assertNotEqual(encoded.getvalue(),archive.getvalue())
            renderer.cache['records']['legacy']={'path':'images/'+legacy_name,'background':'images/'+name,'logoSource':url,'logoSha256':hashlib.sha256(archive.getvalue()).hexdigest(),'officialId':row['officialId']}
            raised=renderer.reposition(row)
            self.assertNotEqual(raised['artwork'],row['artwork'])
            self.assertEqual(raised['featuredLogoLayout'],'aligned-31-v1')
            self.assertEqual(raised['showcaseCopyPosition'],'raised-logo-v1')
            with Image.open(root/'docs/home'/raised['artwork'].removeprefix(BASE))as im:
                self.assertEqual(im.size,(640,800))
                self.assertLess(im.getpixel((100,530))[1],30)
                self.assertLess(im.getpixel((100,550))[1],30)
                self.assertGreater(im.getpixel((100,554))[1],160)
                self.assertGreater(im.getpixel((100,665))[1],160)
            self.assertEqual(renderer.reposition(row),raised)
            self.assertEqual(len(calls),1)
            with self.assertRaises(ValueError):renderer.reposition(dict(row,officialId='umc.cmc.other'))
            renderer.cache['records']['legacy']['logoSha256']='0'*64
            wrong=Image.new('RGBA',(470,140));wrong.paste((0,0,255,255),(30,20,430,120));wrong_bytes=io.BytesIO();wrong.save(wrong_bytes,'PNG')
            renderer.fetch=lambda url:wrong_bytes.getvalue()
            with self.assertRaisesRegex(ValueError,'Official title logo changed'):renderer.reposition(row)
    def test_cache_is_bound_to_background_and_logo_and_not_composited_twice(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);folder=root/'docs/home/images';folder.mkdir(parents=True);(root/'data').mkdir()
            base=self.blob('RGB',(400,600),'gray','JPEG');name=hashlib.sha256(base).hexdigest()+'.jpg';(folder/name).write_bytes(base)
            calls=[];logo=self.blob('RGBA',(470,140),(255,255,255,128),'PNG')
            renderer=PosterLogos(root,lambda url:(calls.append(url)or logo));row={'artwork':BASE+'images/'+name,'officialId':'umc.cmc.abc'};url='https://is1-ssl.mzstatic.com/image/thumb/example/470x140bb.png'
            a=renderer.apply(row,url);b=renderer.apply(row,url);self.assertEqual(a,b);self.assertEqual(len(calls),1);self.assertEqual(a['logoTreatment'],'official-composite-v1');self.assertNotEqual(a['artwork'],row['artwork'])
            with self.assertRaises(ValueError):renderer.apply(row,'https://example.com/logo.png')

    def test_editorial_logo_preserves_proportions_and_reserves_space_for_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'docs/home/images';folder.mkdir(parents=True)
            base=self.blob('RGB',(640,800),(180,180,180),'JPEG')
            ref=hashlib.sha256(base).hexdigest()+'.jpg';(folder/ref).write_bytes(base)
            logo=Image.new('RGBA',(470,140));logo.paste((255,0,0,255),(35,20,435,120))
            encoded=io.BytesIO();logo.save(encoded,'PNG')
            calls=[]
            renderer=PosterLogos(root,lambda url:(calls.append(url)or encoded.getvalue()))
            row={'artwork':BASE+'images/'+ref,'officialId':'umc.cmc.test','width':640,'height':800}
            url='https://is1-ssl.mzstatic.com/image/thumb/example/470x140bb.png'
            with_copy=dict(row,showcaseCopy={'descriptionEn':'Official text'})
            treatment=renderer.apply(with_copy,url,editorial=True)
            self.assertEqual(treatment['featuredCopyTop'],866)
            self.assertNotIn('featuredLogoLayout',treatment)
            self.assertNotIn('showcaseCopyPosition',treatment)
            with Image.open(root/'docs/home'/treatment['artwork'].removeprefix(BASE)) as image:
                # The logo's 4:1 content fits in 296x74 at x=34, y=606.
                self.assertLess(image.getpixel((40,610))[1],30)
                self.assertLess(image.getpixel((320,676))[1],30)
                self.assertGreater(image.getpixel((350,620))[1],160)
                self.assertGreater(image.getpixel((100,690))[1],160)
            self.assertEqual(renderer.apply(with_copy,url,editorial=True),treatment)
            self.assertEqual(len(calls),1)
            without_copy=renderer.apply(row,url,editorial=True)
            self.assertEqual(without_copy['featuredCopyTop'],909)
            self.assertNotEqual(without_copy['artwork'],treatment['artwork'])
            self.assertEqual(len(calls),2)
            self.assertEqual(renderer.apply(row,url)['featuredLogoLayout'],'aligned-31-v1')
            with self.assertRaisesRegex(ValueError,'4:5 poster'):
                renderer.apply(dict(row,width=400,height=600),url,editorial=True)
