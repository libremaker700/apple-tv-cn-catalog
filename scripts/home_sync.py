"""Publish the US channel's film/series recommendations and native wide artwork separately from the library."""
import copy,hashlib,io,json,re,time,concurrent.futures,threading
from pathlib import Path
from urllib.parse import urlsplit
import requests
from PIL import Image
from catalog import ROOT,DOCS,load,raw_json

SOURCE='https://tv.apple.com/us/channel/apple-tv/tvs.sbd.4000'
BASE='https://libremaker700.github.io/apple-tv-cn-catalog/home/'
ROOM='https://tv.apple.com/us/room/sci-fi-on-appletv/edt.item.650b3154-accd-4b87-9f89-6bde117cee31'
LABELS={'uts.col.tv-plus-newest-releases':'最新上线','uts.col.ChartsShows.tvs.sbd.4000':'热门剧集','uts.col.ChartsMovies.tvs.sbd.4000':'热门电影','uts.col.free-premieres-on-tv-plus':'首集精选','uts.col.tv-plus-great-movies':'精选电影'}
def fetch(url):
    u=urlsplit(url)
    if not (url in (SOURCE,ROOM) or u.hostname=='tv.apple.com' and re.fullmatch(r'/us/(movie|show)/[^/]+/umc\.cmc\.[a-z0-9]+',u.path) or re.fullmatch(r'is\d+-ssl\.mzstatic\.com',u.hostname or '') and u.path.startswith('/image/')) or u.scheme!='https' or u.username or u.password:
        raise ValueError('Unsupported homepage endpoint')
    r=requests.get(url,headers={'User-Agent':'Mozilla/5.0 AppleTVCatalog/1.0'},timeout=(15,35),allow_redirects=False)
    r.raise_for_status()
    if r.status_code!=200:raise ValueError('Unexpected homepage redirect')
    return r.content

def channel_data(html):
    m=re.search(r'<script[^>]*id=["\']serialized-server-data["\'][^>]*>(.*?)</script>',html,re.S)
    if not m:raise ValueError('Homepage structured data missing')
    for block in json.loads(m[1]).get('data',[]):
        intent=block.get('intent',{})
        if intent.get('$kind')=='ChannelPageIntent' and intent.get('id')=='tvs.sbd.4000' and intent.get('storefront')=='us':return block['data']
    raise ValueError('Wrong homepage identity or storefront')

def collect(catalog,html,image):
    by_id={};by_slug={e['slug']:e for e in catalog['entries']}
    for e in catalog['entries']:
        urls=[(e.get('officialIdentity') or {}).get('watchUrl',''),(e.get('zh') or {}).get('watchUrl','')]
        for url in urls:
            match=re.search(r'umc\.cmc\.[a-z0-9]+',url)
            if match:
                candidates=by_id.setdefault(match[0],[])
                if not any(x['slug']==e['slug'] for x in candidates):candidates.append(e)
    data=channel_data(html);hero=[];shelves=[];skipped=[]
    def match(item):
        dest=(item.get('segue') or {}).get('destination',{});official=dest.get('id') or item.get('id','');candidates=by_id.get(official,[])
        if len(candidates)>1:candidates=[e for e in candidates if e['en'].casefold()==str(item.get('title','')).casefold()]
        entry=candidates[0] if len(candidates)==1 else None
        expected='movie' if dest.get('$kind')=='MoviePageIntent' or item.get('type')=='Movie' else 'series' if dest.get('$kind')=='ShowPageIntent' or item.get('type')=='Show' else ''
        if entry and entry['kind']==expected:return entry,official
        if re.fullmatch(r'umc\.cmc\.[a-z0-9]+',official):skipped.append({'officialId':official,'english':item.get('title','')})
        return None,None
    for shelf in data.get('shelves',[]):
        sid=shelf.get('id','')
        if sid=='uts.col.tv-plus-epic-stage':
            seen=set()
            for item in shelf.get('items',[]):
                e,official=match(item)
                if not e or e['slug'] in seen:continue
                wide=(item.get('artwork') or {}).get('wide',{});template=wide.get('template','')
                if not re.match(r'https://is\d+-ssl\.mzstatic\.com/image/',template):continue
                url=template.replace('{w}','1920').replace('{h}','1080').replace('{c}','sr').replace('{f}','jpg')
                if '{' in url:raise ValueError('Unknown artwork template')
                hero.append({'slug':e['slug'],'officialId':official,'sourceArtwork':url});seen.add(e['slug'])
        elif sid in LABELS:
            items=[];seen=set()
            for position,item in enumerate(shelf.get('items',[]),1):
                e,official=match(item)
                if e and e['slug'] not in seen:items.append({'slug':e['slug'],'officialId':official,'rank':position});seen.add(e['slug'])
            if items:shelves.append({'id':sid,'title':LABELS[sid],'items':items[:40]})
    if not 3<=len(hero)<=12 or len(shelves)<2:raise ValueError('Incomplete channel recommendations')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        arts=list(pool.map(lambda row:image(row['sourceArtwork']),hero))
    for row,art in zip(hero,arts):row.update(art)
    value={'schema':1,'source':SOURCE,'hero':hero,'shelves':shelves}
    validate(value,by_slug)
    return value,{'heroCount':len(hero),'shelfCount':len(shelves),'unmappedChannelWorks':list({x['officialId']:x for x in skipped}.values())}

def validate(value,entries=None):
    if value.get('schema')==3:
        from home_validation import validate_pages
        return validate_pages(value)
    if value.get('schema')==2:
        from home_validation import validate_home
        return validate_home(value)
    assert value.get('schema')==1 and value.get('source')==SOURCE
    assert 3<=len(value['hero'])<=12 and 2<=len(value['shelves'])<=12
    for rows in [value['hero']]+[s['items'] for s in value['shelves']]:
        seen=set()
        for row in rows:
            assert re.fullmatch(r'[a-z0-9-]{1,150}',row['slug']) and row['slug'] not in seen;seen.add(row['slug'])
            assert not entries or row['slug'] in entries
            assert re.fullmatch(r'umc\.cmc\.[a-z0-9]+',row['officialId'])
            assert not any(k in row for k in ('id','sourceIds','headers','token','playUrl'))
    for row in value['hero']:
        assert row['width']==1920 and row['height']==1080
        assert re.fullmatch(r'images/[a-f0-9]{64}\.jpg',row['artwork'].removeprefix(BASE))

def sync():
    folder=DOCS/'home';(folder/'images').mkdir(parents=True,exist_ok=True)
    cache_file=ROOT/'data/home-image-cache.json';cache=load(cache_file) if cache_file.exists() else {};now=int(time.time())
    cache_lock=threading.Lock()
    def image(url,width=1920,height=1080):
        previous=cache.get(url);path=folder/previous['path'] if previous else None
        if previous and now-previous.get('checkedAt',0)<6*3600 and path.is_file():
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()==path.stem:return {'artwork':BASE+previous['path'],'width':width,'height':height}
        raw=fetch(url)
        with Image.open(io.BytesIO(raw)) as im:
            assert im.size==(width,height) and im.format=='JPEG';im.verify()
        ref='images/'+hashlib.sha256(raw).hexdigest()+'.jpg';(folder/ref).write_bytes(raw)
        with cache_lock:
            cache[url]={'path':ref,'checkedAt':now}
            from title_lookup import dump
            dump(cache_file,cache)
        print(json.dumps({'homeImageReady':ref,'bytes':len(raw)}),flush=True)
        return {'artwork':BASE+ref,'width':width,'height':height}
    details_path=ROOT/'data/home-work-cache.json';details=load(details_path) if details_path.exists() else {}
    def detail(work):
        from home_sources import detail_work
        previous=details.get(work['officialId'])
        if previous and previous.get('en')==work['en'] and previous.get('kind')==work['kind'] and now-previous.get('checkedAt',0)<7*86400:return previous
        found=detail_work(work,fetch(work['watchUrl']).decode('utf8'));found['checkedAt']=now;details[work['officialId']]=found
        from title_lookup import dump
        dump(details_path,details);return found
    from official_pages import Pages
    from home_pages import collect as collect_official
    value,report=collect_official(load(DOCS/'catalog.json'),Pages(ROOT,fetch(SOURCE).decode('utf-8')),image)
    from home_titles import enrich
    enrich(value,ROOT,now)
    validate(value)
    raw=raw_json(value);sha=hashlib.sha256(raw).hexdigest();images={}
    from home_pages import image_rows
    rows=image_rows(value)
    for row in rows:
        ref=row['artwork'].removeprefix(BASE);blob=(folder/ref).read_bytes();images[ref]={'sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob),'width':row['width'],'height':row['height']}
    assert sum(x['bytes'] for x in images.values())<=96*1024*1024
    path='releases/'+sha+'/home.json';(folder/path).parent.mkdir(parents=True,exist_ok=True);(folder/path).write_bytes(raw)
    manifest={'schema':1,'version':sha,'path':path,'images':images,'checkedAt':now}
    (folder/'home.json').write_bytes(raw);(folder/'version.json').write_bytes(raw_json(manifest))
    cache_file.write_bytes(raw_json(cache));(folder/'sync-report.json').write_bytes(raw_json(dict(report,checkedAt=now,version=sha)))
    details_path.write_bytes(raw_json(details))
    print(json.dumps(dict(report,version=sha,imageBytes=sum(x['bytes'] for x in images.values()))),flush=True)
    return value,manifest

def validate_publication():
    folder=DOCS/'home';manifest=load(folder/'version.json');raw=(folder/manifest['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==manifest['version']
    value=json.loads(raw);validate(value)
    refs=set()
    from home_pages import image_rows
    rows=image_rows(value)
    for row in rows:
        ref=row['artwork'].removeprefix(BASE);refs.add(ref);blob=(folder/ref).read_bytes();meta=manifest['images'][ref]
        assert hashlib.sha256(blob).hexdigest()==meta['sha256']==Path(ref).stem and len(blob)==meta['bytes']
        with Image.open(io.BytesIO(blob)) as im:assert im.size==(row['width'],row['height']);im.verify()
    assert refs==set(manifest['images']) and sum(x['bytes']for x in manifest['images'].values())<=96*1024*1024
    print('PASS home identities, manifest hash and full HD image files')

if __name__=='__main__':
    import sys
    if '--validate' in sys.argv:validate_publication()
    else:sync()
