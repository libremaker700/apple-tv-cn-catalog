"""Bounded cloud-only upgrades for undersized horizontal library artwork.

The default command is an offline plan. --apply explicitly fetches verified Apple
PR image variants; publish() only reapplies accepted cached bytes and does no I/O
against Apple. Existing 628px and larger originals are never re-encoded.
"""
import argparse, concurrent.futures, copy, hashlib, io, json, re, threading, time
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit,unquote
import requests
from PIL import Image, ImageCms, ImageOps

BASE='https://libremaker700.github.io/apple-tv-cn-catalog/'
WIDTH,HEIGHT,MIN_WIDTH=640,360,600
MAX_BYTES,MAX_PIXELS=8*1024*1024,20_000_000
PROCESSOR='list-640x360-srgb-jpeg90-v1'
TTL,RETRY=7*86400,6*3600

def canonical(url):
    try:
        parsed=urlsplit(str(url))
        if parsed.scheme!='https' or parsed.hostname!='www.apple.com' or parsed.username or parsed.password or parsed.port not in(None,443) or parsed.query or parsed.fragment:return None
        if '\\'in unquote(parsed.path)or any(part in('.', '..')for part in unquote(parsed.path).split('/')):return None
        if not re.fullmatch(r'/tv-pr/shows-and-films/[a-z0-9]/[a-z0-9-]+/images/[^?#]+\.(?:jpg|jpeg|png)',parsed.path,re.I):return None
        return 'https://www.apple.com'+re.sub(r'\.(?:small|medium|large)(?:_2x)?(?=\.(?:jpg|jpeg|png)$)','',parsed.path,flags=re.I)
    except ValueError:return None

def work_season(entry):
    if entry.get('kind')=='movie':return 0
    source=str(entry.get('sourceArtwork')or'');match=re.search(r'/season-(\d+)/',source)
    number=int(match[1])if match else entry.get('artworkSeasonNumber')
    return number if type(number)is int and 1<=number<=100 else None

def source_key(source,entry):
    value=canonical(source)
    if not value or entry.get('kind')not in('movie','series')or work_season(entry)is None:return None
    if re.search(r'/tv-pr/shows-and-films/[^/]+/([^/]+)/images/',value)[1]!=entry.get('slug'):return None
    identity={'source':value,'slug':entry.get('slug'),'kind':entry.get('kind'),'season':work_season(entry),'processor':PROCESSOR}
    return hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def local_path(docs,url):
    ref=str(url or '').removeprefix(BASE)
    if not re.fullmatch(r'images/[a-f0-9]{64}\.(?:jpg|png|webp)',ref):return None
    return Path(docs)/ref

def dimensions(docs,url):
    path=local_path(docs,url)
    if path is None:return None
    try:
        with Image.open(path)as image:return image.size
    except(OSError,ValueError):return None

def small(docs,entry):
    size=dimensions(docs,entry.get('artwork'))
    return bool(size and size[0]<MIN_WIDTH and size[1]>0 and abs(size[0]/size[1]-16/9)<.02)

def index_source(entry,row):
    """Use a PR inventory descriptor only for the same work, type and depicted season."""
    if not isinstance(row,dict)or row.get('url')!='/tv-pr/originals/'+entry.get('slug','')+'/':return None
    if row.get('title')!=entry.get('en')or row.get('showTypeKey')!=('films'if entry.get('kind')=='movie'else'series'):return None
    picture=row.get('image')or{};directory=picture.get('dirpath','');name=picture.get('name','');extension=picture.get('type','')
    if not all(isinstance(x,str)and x for x in(directory,name,extension)):return None
    value='https://www.apple.com'+directory+name
    if not name.lower().endswith('.'+extension.lower()):value+='.'+extension
    value=canonical(value)
    if not value or source_key(value,entry)is None:return None
    if entry.get('kind')=='series':
        depicted=re.search(r'/season-(\d+)/',value)
        if not depicted or int(depicted[1])!=work_season(entry):return None
    return value

def page_candidates(html,entry,source):
    expected=re.search(r'/key-art-([^/]+)/',str(source));found=[]
    for path in re.findall(r'(?:https://www\.apple\.com)?(/tv-pr/shows-and-films/[^\s\"\'<>,()]+)',unescape(html)):
        url='https://www.apple.com'+path
        if source_key(url,entry)is None or any(role in path for role in('/video-posters/','/stills/','/4x1/','/2x3/'))or re.search(r'[_-](?:4[_-]1|2[_-]3)[_.-]',path):continue
        keyart=re.search(r'/key-art-([^/]+)/',path)
        if not keyart:continue
        if expected and(not keyart or expected[1]!=keyart[1]):continue
        depicted=re.search(r'/season-(\d+)/',path)
        if entry['kind']=='series'and(not depicted or int(depicted[1])!=work_season(entry)):continue
        variant=re.search(r'\.(large_2x|large|medium_2x)\.(?:jpg|jpeg|png)$',path,re.I)
        original=not re.search(r'\.(?:small|medium|large|og)(?:_2x)?\.',path,re.I)and'/thumbnail/'not in path
        if(variant or original)and url not in found:found.append(url)
    return sorted(found,key=lambda url:0 if '.large_2x.'in url else 1 if '.large.'in url else 2 if '.medium_2x.'in url else 3)[:2]

def official_image_source(url):
    try:
        value=urlsplit(str(url));return value.scheme=='https'and value.port in(None,443)and not value.username and not value.password and not value.query and not value.fragment and bool(re.fullmatch(r'is\d+-ssl\.mzstatic\.com',value.hostname or''))and value.path.startswith('/image/')
    except ValueError:return False

def cached_original(docs,entry,home=None):
    """Reuse independently verified local wide bytes, with exact season/show binding."""
    watch=str((entry.get('officialIdentity')or{}).get('watchUrl')or'')
    identity=re.fullmatch(r'https://tv\.apple\.com/us/'+('movie'if entry.get('kind')=='movie'else'show')+r'/[^/?#]+/(umc\.cmc\.[a-z0-9]+)',watch)
    if not identity:return None
    candidates=[];number=work_season(entry)
    if entry.get('kind')=='movie'and official_image_source(entry.get('heroSource')):
        candidates.append((entry.get('heroArtwork'),entry.get('heroSource'),'verified-movie-hero-cache',None))
    if entry.get('kind')=='movie'and isinstance(home,dict)and home.get('source')=='https://tv.apple.com/us/channel/apple-tv/tvs.sbd.4000':
        work=next((row for row in home.get('works',[])if row.get('slug')==entry.get('slug')and row.get('kind')=='movie'and row.get('officialId')==identity[1]and row.get('watchUrl')==watch),None)
        if work:
            for page in[home]+home.get('pages',[]):
                refs=list(page.get('hero',[]))+[ref for shelf in page.get('shelves',[])for ref in shelf.get('items',[])]
                for ref in refs:
                    width,height=ref.get('width'),ref.get('height')
                    if ref.get('slug')==entry.get('slug')and ref.get('officialId')==identity[1]and type(width)is int and type(height)is int and width>=WIDTH and height>=HEIGHT and abs(width/height-16/9)<.02:
                        candidates.append((ref.get('artwork'),ref.get('artwork'),'verified-movie-home-cache',(width,height)))
    if entry.get('kind')=='series':
        lists=[entry.get('seasons',[])]
        if isinstance(home,dict):
            for work in home.get('works',[]):
                if work.get('slug')==entry.get('slug')and work.get('kind')=='series'and work.get('officialId')==identity[1]and work.get('watchUrl')==watch:lists.append(work.get('seasons',[]))
        for seasons in lists:
            for row in seasons:
                if row.get('season')==number and row.get('metadataStatus')=='verified'and row.get('showId')==identity[1]and re.fullmatch(r'umc\.cmc\.[a-z0-9]+',str(row.get('officialId')or''))and official_image_source(row.get('sourceArtwork')):
                    candidates.append((row.get('artwork'),row.get('sourceArtwork'),'verified-season-cache',None))
    for address,source,role,expected_size in candidates:
        ref=str(address or'').removeprefix(BASE)
        if not re.fullmatch(r'(?:home/)?images/[a-f0-9]{64}\.(?:jpg|png|webp)',ref):continue
        path=Path(docs)/ref
        try:
            if path.stat().st_size>MAX_BYTES:continue
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=path.stem:continue
            with Image.open(io.BytesIO(raw))as image:
                if image.width<WIDTH or image.height<HEIGHT or abs(image.width/image.height-16/9)>.02 or expected_size and image.size!=expected_size:continue
            return raw,source,role
        except(OSError,ValueError):continue
    return None

def _download(url,deadline,limit):
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('work_budget_exhausted')
    with requests.get(url,headers={'User-Agent':'Mozilla/5.0 AppleTVCatalog/1.0'},timeout=(min(8,remaining),min(12,remaining)),allow_redirects=False,stream=True)as response:
        response.raise_for_status()
        if response.status_code!=200:raise ValueError('unexpected_image_redirect')
        length=response.headers.get('Content-Length')
        if length and int(length)>limit:raise ValueError('response_too_large')
        data=bytearray()
        for chunk in response.iter_content(64*1024):
            if time.monotonic()>deadline:raise TimeoutError('work_budget_exhausted')
            if chunk:data.extend(chunk)
            if len(data)>limit:raise ValueError('response_too_large')
        return bytes(data)

def download(url,deadline):
    if canonical(url)is None:raise ValueError('unsupported_image_source')
    return _download(url,deadline,MAX_BYTES)

def download_page(url,deadline):
    if not re.fullmatch(r'https://www\.apple\.com/tv-pr/originals/[a-z0-9-]{1,150}/',str(url)):raise ValueError('unsupported_pr_page')
    return _download(url,deadline,2*1024*1024)

def derivative(raw):
    if not isinstance(raw,bytes)or not raw or len(raw)>MAX_BYTES:raise ValueError('image_too_large_or_empty')
    with Image.open(io.BytesIO(raw))as probe:
        width,height=probe.size
        if width<WIDTH or height<HEIGHT or width*height>MAX_PIXELS or abs(width/height-16/9)>.02:raise ValueError('not_a_sufficient_wide_original')
        if probe.format not in('JPEG','PNG','WEBP'):raise ValueError('unsupported_image_format')
        probe.verify()
    with Image.open(io.BytesIO(raw))as source:
        image=ImageOps.exif_transpose(source)
        if image.width<WIDTH or image.height<HEIGHT or abs(image.width/image.height-16/9)>.02:raise ValueError('oriented_image_not_wide')
        if source.info.get('icc_profile'):
            profile=ImageCms.ImageCmsProfile(io.BytesIO(source.info['icc_profile']))
            image=ImageCms.profileToProfile(image,profile,ImageCms.createProfile('sRGB'),outputMode='RGB')
        else:image=image.convert('RGB')
        image=ImageOps.fit(image,(WIDTH,HEIGHT),method=Image.Resampling.LANCZOS)
        image.info.clear()
        output=io.BytesIO();image.save(output,format='JPEG',quality=90,optimize=True)
    # No EXIF or source metadata is copied, giving stable bytes for unchanged pixels.
    return output.getvalue()

class Tiers:
    def __init__(self,root,now=None,fetch=None,page_fetch=None):
        self.root=Path(root);self.docs=self.root/'docs';self.now=int(time.time()if now is None else now);self.fetch=fetch or download;self.page_fetch=page_fetch or download_page;self.lock=threading.Lock()
        self.path=self.root/'data/list-artwork-cache.json'
        try:
            if self.path.stat().st_size>2*1024*1024:raise ValueError('artwork_cache_too_large')
            self.cache=json.loads(self.path.read_text(encoding='utf8'))
        except(OSError,ValueError):self.cache={'schema':1,'processor':PROCESSOR,'items':{},'failures':{}}
        if not isinstance(self.cache,dict)or self.cache.get('schema')!=1 or self.cache.get('processor')!=PROCESSOR or not isinstance(self.cache.get('items'),dict)or not isinstance(self.cache.get('failures'),dict):self.cache={'schema':1,'processor':PROCESSOR,'items':{},'failures':{}}
        try:self.home=json.loads((self.docs/'home/home.json').read_text(encoding='utf8'))
        except(OSError,ValueError):self.home=None
    def cached(self,entry):
        key=source_key(entry.get('sourceArtwork'),entry);row=self.cache.get('items',{}).get(key)
        if not isinstance(row,dict)or row.get('width')!=WIDTH or row.get('height')!=HEIGHT or type(row.get('checkedAt'))is not int or row['checkedAt']<=0:return None
        previous=row.get('previousArtworks',[])
        if not isinstance(previous,list)or len(previous)>4 or any(local_path(self.docs,ref)is None for ref in previous):return None
        path=local_path(self.docs,row.get('artwork'))
        try:
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=path.stem or dimensions(self.docs,row['artwork'])!=(WIDTH,HEIGHT):return None
        except(OSError,AttributeError):return None
        return row
    def apply(self,entry):
        row=self.cached(entry)
        if not row:return False
        size=dimensions(self.docs,entry.get('artwork'))
        # A later original may already be 628/944/etc.; never replace it by a smaller tier.
        if size and size[0]>=MIN_WIDTH and entry.get('artwork')not in[row['artwork']]+row.get('previousArtworks',[]):return False
        entry['artwork']=row['artwork'];return True
    def needs(self,entry,force=False):
        row=self.cached(entry)
        if not small(self.docs,entry)and not(row and entry.get('artwork')in[row['artwork']]+row.get('previousArtworks',[])):return False
        if row and not force and self.now-row.get('checkedAt',0)<TTL:return False
        failed=self.cache.get('failures',{}).get(source_key(entry.get('sourceArtwork'),entry),{})
        return force or self.now-failed.get('checkedAt',0)>=RETRY
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.cache,ensure_ascii=False,sort_keys=True,separators=(',',':')),encoding='utf8');temp.replace(self.path)
    def store(self,entry,key,raw,candidate,source,attempts,role):
        raw=derivative(raw);ref='images/'+hashlib.sha256(raw).hexdigest()+'.jpg';path=self.docs/ref;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        row={'artwork':BASE+ref,'width':WIDTH,'height':HEIGHT,'checkedAt':self.now,'source':candidate,'sourceRole':role}
        with self.lock:
            previous=self.cache.setdefault('items',{}).get(key,{})
            row['previousArtworks']=list(dict.fromkeys([previous.get('artwork')]+previous.get('previousArtworks',[])))[:4]
            row['previousArtworks']=[ref for ref in row['previousArtworks']if ref and ref!=row['artwork']]
            self.cache.setdefault('items',{})[key]=row
            alias=source_key(source,entry)
            if alias:self.cache['items'][alias]=copy.deepcopy(row)
            self.cache.setdefault('failures',{}).pop(key,None);self.save()
        return{'slug':entry['slug'],'status':'upgraded','width':WIDTH,'height':HEIGHT,'attempts':attempts,'sourceRole':role,'bytes':len(raw)}
    def upgrade(self,entry,official_row):
        key=source_key(entry.get('sourceArtwork'),entry)
        if not key:return{'slug':entry['slug'],'status':'retained','reason':'unsupported_original_source'}
        cached=cached_original(self.docs,entry,self.home)
        if cached:
            try:return self.store(entry,key,cached[0],cached[1],entry.get('sourceArtwork'),0,cached[2])
            except(OSError,ValueError,Image.DecompressionBombError,ImageCms.PyCMSError):pass
        source=index_source(entry,official_row)
        candidates=[];deadline=time.monotonic()+30;error='pr_identity_or_season_mismatch';attempts=0
        if source:
            try:
                html=self.page_fetch('https://www.apple.com/tv-pr/originals/'+entry['slug']+'/',deadline)
                if not isinstance(html,bytes)or len(html)>2*1024*1024:raise ValueError('invalid_pr_page')
                candidates=page_candidates(html.decode('utf8'),entry,source);error='no_verified_hd_source'
            except(requests.RequestException,OSError,ValueError,TimeoutError)as exc:error=type(exc).__name__
        for candidate in candidates[:2]:
            attempts+=1
            try:
                return self.store(entry,key,self.fetch(candidate,deadline),candidate,source,attempts,'verified-pr-page')
            except(requests.RequestException,OSError,ValueError,TimeoutError,Image.DecompressionBombError,ImageCms.PyCMSError)as exc:
                error=type(exc).__name__
                if time.monotonic()>=deadline:break
        with self.lock:self.cache.setdefault('failures',{})[key]={'checkedAt':self.now,'reason':error};self.save()
        return{'slug':entry['slug'],'status':'retained','reason':error,'attempts':attempts}

def apply_cached(catalog,root):
    tiers=Tiers(root)
    for entry in catalog.get('entries',[]):tiers.apply(entry)
    return catalog

def plan(catalog,root,limit=12,force=False,retry_failed=False):
    tiers=Tiers(root);distribution={};small_count=0;ready=[];unsupported=[]
    for entry in catalog['entries']:
        size=dimensions(tiers.docs,entry.get('artwork'))
        if size:distribution['x'.join(map(str,size))]=distribution.get('x'.join(map(str,size)),0)+1
        if small(tiers.docs,entry):small_count+=1
        key=source_key(entry.get('sourceArtwork'),entry)
        if small(tiers.docs,entry)and key is None:unsupported.append(entry['slug']);continue
        if tiers.needs(entry,force or bool(retry_failed and key in tiers.cache['failures'])):
            failure=tiers.cache['failures'].get(key);cached=tiers.cached(entry)
            rank=(0,0)if not failure and not cached else(1,failure['checkedAt'])if failure else(2,cached['checkedAt'])
            ready.append((rank,entry))
    ready.sort(key=lambda pair:pair[0]);selected=[entry for rank,entry in ready[:limit]]
    return tiers,selected,{'entries':len(catalog['entries']),'smallBelow600':small_count,'due':len(ready),'selected':len(selected),'unsupported':unsupported,'distribution':distribution}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--publish',action='store_true');parser.add_argument('--limit',type=int,default=12);parser.add_argument('--workers',type=int,default=3);parser.add_argument('--force',action='store_true');parser.add_argument('--retry-failed',action='store_true');args=parser.parse_args()
    if not 0<=args.limit<=128 or not 1<=args.workers<=3:parser.error('limit must be 0..128 and workers 1..3')
    if args.publish and not args.apply:parser.error('--publish requires --apply')
    from catalog import ROOT,DOCS,INDEX,get,load,publish,raw_json
    catalog=load(DOCS/'catalog.json');tiers,selected,stats=plan(catalog,ROOT,args.limit,args.force,args.retry_failed)
    report={'schema':1,'processor':PROCESSOR,'checkedAt':tiers.now,'apply':args.apply,**stats,'works':[]}
    if args.apply and selected:
        rows=get(INDEX).json()['results']['originals'];by_slug={row.get('url','').rstrip('/').split('/')[-1]:row for row in rows}
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers)as pool:
            report['works']=list(pool.map(lambda entry:tiers.upgrade(entry,by_slug.get(entry['slug'])),selected))
    else:report['works']=[{'slug':entry['slug'],'status':'planned'}for entry in selected]
    report['upgraded']=sum(row['status']=='upgraded'for row in report['works']);report['retained']=sum(row['status']=='retained'for row in report['works'])
    if args.apply:
        (ROOT/'logs').mkdir(exist_ok=True);(ROOT/'logs/list-artwork.json').write_bytes(raw_json(report))
        if args.publish:publish(catalog,int(time.time()),'verified-list-artwork-tiers')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
