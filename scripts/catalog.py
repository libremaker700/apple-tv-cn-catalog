"""Public Apple TV metadata + content-addressed image publication. No playback credentials."""
import argparse, concurrent.futures, copy, hashlib, io, json, os, re, time
from pathlib import Path
from datetime import datetime, timezone
import requests
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs'
BASE='https://libremaker700.github.io/apple-tv-cn-catalog/'
INDEX='https://www.apple.com/tv-pr/originals.originals.json'
def raw_json(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def digest(raw): return hashlib.sha256(raw).hexdigest()
def load(path): return json.loads(path.read_text(encoding='utf-8'))
def get(url):
    r=requests.get(url,headers={'User-Agent':'Mozilla/5.0 AppleTVCatalog/1.0'},timeout=(15,35));r.raise_for_status();return r
def save_image(raw):
    if len(raw)>8*1024*1024: raise ValueError('image too large')
    with Image.open(io.BytesIO(raw)) as im:
        im.verify(); fmt=im.format
    ext={'JPEG':'jpg','PNG':'png','WEBP':'webp'}.get(fmt)
    if not ext: raise ValueError('unsupported image')
    path='images/'+digest(raw)+'.'+ext
    (DOCS/path).parent.mkdir(parents=True,exist_ok=True);(DOCS/path).write_bytes(raw);return path
def validate(catalog):
    entries=catalog['entries'];assert 50<=len(entries)<=2000
    seen=set()
    for e in entries:
        assert re.fullmatch('[a-z0-9-]{1,150}',e['slug']) and e['slug'] not in seen;seen.add(e['slug'])
        assert e['kind'] in ('movie','series') and e['en']
        assert e['officialUrl']=='https://www.apple.com/tv-pr/originals/'+e['slug']+'/'
        assert not any(k in e for k in ('id','sourceIds','playUrl','token','headers'))
        for field in ('artwork','heroArtwork'):
            if not e.get(field): continue
            path=e[field].removeprefix(BASE);assert re.fullmatch(r'images/[a-f0-9]{64}\.(jpg|png|webp)',path)
            b=(DOCS/path).read_bytes();assert digest(b)==Path(path).stem
            with Image.open(io.BytesIO(b)) as im: im.verify()
def publish(catalog,checked_at,mode):
    value=copy.deepcopy(catalog)
    images={}
    for e in value['entries']:
        for key in ('artwork','heroArtwork'):
            if e.get(key):
                p=e[key].removeprefix(BASE);b=(DOCS/p).read_bytes();images[p]={'sha256':digest(b),'bytes':len(b)};e[key]=BASE+p
    value['complete']=True;validate(value)
    raw=raw_json(value);sha=digest(raw);path='releases/'+sha+'/catalog.json'
    (DOCS/path).parent.mkdir(parents=True,exist_ok=True);(DOCS/path).write_bytes(raw)
    manifest={'schema':1,'version':sha,'catalog_path':path,'catalog_sha256':sha,'item_count':len(value['entries']),
              'image_count':len(images),'images':images,'checked_at':checked_at,'publication_mode':mode}
    # The manifest is written last; only complete data snapshots become active.
    (DOCS/'catalog.json').write_bytes(raw);(DOCS/'version.json').write_bytes(raw_json(manifest))
    print(json.dumps({'version':sha,'entries':len(value['entries']),'images':len(images),'mode':mode}))
def collect(previous):
    rows=get(INDEX).json()['results']['originals'];old={e['slug']:e for e in previous['entries']}
    seeds={e['slug']:e for e in load(ROOT/'data/seed.json')['entries']}
    rows=[r for r in rows if r.get('showTypeKey') in ('films','series')]
    assert len(rows)>=max(50,int(len(old)*0.9)), 'incomplete source inventory'
    def entry(r):
        slug=r['url'].split('/')[3];e=copy.deepcopy(old.get(slug,{}));prior=e.get('version')
        e.update(slug=slug,en=r['title'],kind='movie' if r['showTypeKey']=='films' else 'series',officialUrl='https://www.apple.com'+r['url'],
                 releaseDate=r.get('releaseDateISOString','')[:10],genres=r.get('genres',[]),
                 seasonNumber=int(re.search(r'\d+',r.get('seasonDisplay','')).group()) if re.search(r'\d+',r.get('seasonDisplay','')) else 1,
                 version=r.get('releaseDateISOString','')+'|'+r.get('seasonDisplay',''))
        im=r['image'];source='https://www.apple.com'+im['dirpath']+im['name']+'.medium.'+im['type']
        assert re.match(r'https://www\.apple\.com/(?:[a-z]{2}/)?tv-pr/shows-and-films/',source)
        candidates=[source]
        # Apple's regional Napoleon record includes a filename extension in `name`.
        if im['name'].endswith('.'+im['type']):
            candidates=[source.rsplit('.'+im['type']+'.medium.',1)[0]+'.medium.'+im['type'],'https://www.apple.com'+im['dirpath']+im['name'],source]
        error=None
        for candidate in candidates:
            try:e['artwork']=save_image(get(candidate).content);source=candidate;error=None;break
            except Exception as exc:error=exc
        if error:raise RuntimeError('Official artwork failed: '+slug) from error
        e['sourceArtwork']=source
        hero_source=e.get('heroSource') or seeds.get(slug,{}).get('heroSource')
        if hero_source:
            assert re.match(r'https://is[0-9]+-ssl\.mzstatic\.com/image/',hero_source)
            # Keep hero imagery large and landscape instead of upscaling small PR thumbnails.
            with Image.open(io.BytesIO(get(hero_source).content)) as im:
                from PIL import ImageOps
                im=ImageOps.fit(im.convert('RGB'),(1280,720));out=io.BytesIO();im.save(out,format='JPEG',quality=88)
            e['heroArtwork']=save_image(out.getvalue());e['heroSource']=hero_source
        if not e.get('zh') or prior!=e['version']:
            # Identity is the official UMC id, shared by the US and Chinese storefronts.
            try:
                from opencc import OpenCC
                page=get(e['officialUrl']).text
                links=re.findall(r'https://tv\.apple\.com/(?:us/)?(?:show|movie)/[^"\s<>]+',page)
                watch=next(x.replace('&amp;','&') for x in links if '/umc.cmc.' in x)
                zh=None
                for region in ('hk','tw'):
                    try:
                        url=re.sub(r'https://tv\.apple\.com/(?:us/)?','https://tv.apple.com/'+region+'/',watch)
                        html=get(url).text
                        from html import unescape
                        title=re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',html)
                        desc=re.search(r'<meta[^>]+(?:name="description"|property="og:description")[^>]+content="([^"]+)"',html)
                        name=unescape(title.group(1)).split(' - Apple TV')[0].strip('《》 ')
                        if not re.search('[\u4e00-\u9fff]',name):continue
                        cc=OpenCC('t2s');zh={'slug':slug,'title':cc.convert(name),'summary':cc.convert(unescape(desc.group(1))) if desc else '',
                              'aliases':list(dict.fromkeys([name,cc.convert(name)])),'sources':[url],'watchUrl':watch,'version':e['version']};break
                    except Exception:continue
                if zh:e['zh']=zh
            except Exception:pass
        e['chinesePending']=not bool(e.get('zh'))
        return e
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: entries=list(pool.map(entry,rows))
    return {'entries':entries,'complete':True}
def main():
    p=argparse.ArgumentParser();p.add_argument('--seed',action='store_true');p.add_argument('--force',action='store_true');p.add_argument('--validate',action='store_true');a=p.parse_args()
    if a.validate:
        v=load(DOCS/'version.json');raw=(DOCS/v['catalog_path']).read_bytes();assert digest(raw)==v['catalog_sha256'];validate(json.loads(raw));print('PASS complete catalog and all image hashes');return
    if a.seed: publish(load(ROOT/'data/seed.json'),None,'bundled-reviewed-snapshot');return
    prior=load(DOCS/'catalog.json');manifest=load(DOCS/'version.json');last=manifest.get('checked_at') or 0
    if not a.force and time.time()-last<604800: print('Not due; retain verified snapshot');return
    value=collect(prior)
    from title_lookup import reapply_cache
    value=reapply_cache(value);publish(value,int(time.time()),'official-network-collection')
if __name__=='__main__':main()
