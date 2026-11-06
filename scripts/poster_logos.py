"""Render Apple's separate title treatment into public, backwards-compatible JPEGs."""
import hashlib,io,json,re
from pathlib import Path
from PIL import Image,ImageOps
from title_lookup import read,dump
from home_pages import FEATURE_SIZE
BASE='https://libremaker700.github.io/apple-tv-cn-catalog/home/'
def render(base,logo,raised=False):
    with Image.open(io.BytesIO(base))as im:
        if im.format!='JPEG'or im.size not in((400,600),(1920,720),FEATURE_SIZE):raise ValueError('Invalid poster background')
        canvas=im.convert('RGBA');banner=im.size==(1920,720);featured=im.size==FEATURE_SIZE
    with Image.open(io.BytesIO(logo))as im:
        if im.format!='PNG'or im.width*im.height>2_000_000:raise ValueError('Invalid title treatment')
        mark=im.convert('RGBA');alpha=mark.getchannel('A')
        if not alpha.getbbox()or alpha.getextrema()[0]==255:raise ValueError('Title treatment must be transparent')
        if featured:mark=mark.crop(alpha.getbbox())
        mark=ImageOps.contain(mark,(280,90)if banner else(310,76)if featured else(235,70),Image.Resampling.LANCZOS)
    if banner or featured:
        x,bottom=(34,232 if raised else 88)if featured else(34,145)
        canvas.alpha_composite(mark,(x,canvas.height-bottom-mark.height))
        out=io.BytesIO();canvas.convert('RGB').save(out,'JPEG',quality=95,subsampling=0)
        return out.getvalue()
    # Official portrait treatment: bottom legibility gradient and centred 100x30 logo box.
    stops=[(0,0),(.54,0),(.70,.35),(.85,.58),(1,.70)]
    shade=Image.new('RGBA',canvas.size);pixels=shade.load()
    for y in range(600):
        t=y/599
        for (p,a),(q,b)in zip(stops,stops[1:]):
            if p<=t<=q:
                opacity=round(255*(a+(b-a)*(t-p)/(q-p)));break
        for x in range(400):pixels[x,y]=(0,0,0,opacity)
    canvas=Image.alpha_composite(canvas,shade)
    canvas.alpha_composite(mark,((400-mark.width)//2,417+(70-mark.height)//2))
    out=io.BytesIO();canvas.convert('RGB').save(out,'JPEG',quality=95,subsampling=0)
    return out.getvalue()
class PosterLogos:
    def __init__(self,root,fetch):
        self.root=Path(root);self.folder=self.root/'docs/home';self.path=self.root/'data/home-logo-cache.json';self.cache=read(self.path,{'schema':1,'records':{}});self.fetch=fetch;self.count=0
    def apply(self,row,source,raised=False):
        if not re.fullmatch(r'https://is\d+-ssl\.mzstatic\.com/image/[^\s{}]+\.png',source):raise ValueError('Invalid logo origin')
        ref=row['artwork'].removeprefix(BASE)
        if not re.fullmatch(r'images/[a-f0-9]{64}\.jpg',ref):raise ValueError('Invalid poster origin')
        width,height=row.get('width',400),row.get('height',600)
        treatment={(1920,720):'official-banner-logo-v1',FEATURE_SIZE:'official-featured-raised-v1'if raised else'official-featured-logo-v1'}.get((width,height),'official-logo-v1')
        key=hashlib.sha256((treatment+'|'+ref+'|'+source).encode()).hexdigest();old=self.cache['records'].get(key,{})
        path=self.folder/old.get('path','missing')
        if old and path.is_file()and hashlib.sha256(path.read_bytes()).hexdigest()==path.stem:
            self.count+=1;return dict(artwork=BASE+old['path'],width=width,height=height,logoTreatment='official-composite-v1')
        logo=self.fetch(source)
        if len(logo)>4*1024*1024:raise ValueError('Logo is too large')
        raw=render((self.folder/ref).read_bytes(),logo,raised);dest='images/'+hashlib.sha256(raw).hexdigest()+'.jpg';(self.folder/dest).write_bytes(raw)
        self.cache['records'][key]={'path':dest,'background':ref,'logoSource':source,'logoSha256':hashlib.sha256(logo).hexdigest(),'officialId':row['officialId']};dump(self.path,self.cache);self.count+=1
        return dict(artwork=BASE+dest,width=width,height=height,logoTreatment='official-composite-v1')

    def reposition(self,row,raised):
        ref=row['artwork'].removeprefix(BASE)
        original=next((r for r in self.cache['records'].values()if r.get('path')==ref and r.get('officialId')==row['officialId']),None)
        if original is None or (row.get('width'),row.get('height'))!=FEATURE_SIZE:
            raise ValueError('Missing verified featured logo composition')
        return self.apply(dict(row,artwork=BASE+original['background']),original['logoSource'],raised)
