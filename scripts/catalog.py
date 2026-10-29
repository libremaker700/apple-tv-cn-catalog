"""Public Apple TV metadata + content-addressed image publication. No playback credentials."""
import argparse, concurrent.futures, copy, hashlib, io, json, os, re, time
from pathlib import Path
from datetime import datetime, timezone
import requests
from urllib.parse import urljoin
from PIL import Image
from metadata_policy import POLICY,allowed_source,clean_entry,clean_zh
ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs'
BASE='https://libremaker700.github.io/apple-tv-cn-catalog/'
INDEX='https://www.apple.com/tv-pr/originals.originals.json'
def raw_json(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def digest(raw): return hashlib.sha256(raw).hexdigest()
def load(path): return json.loads(path.read_text(encoding='utf-8'))
def get(url):
    for _ in range(5):
        if not allowed_source(url):raise ValueError("Unsupported metadata endpoint")
        r=requests.get(url,headers={'User-Agent':'Mozilla/5.0 AppleTVCatalog/1.0'},timeout=(15,35),allow_redirects=False)
        if 300<=r.status_code<400:
            target=urljoin(url,r.headers.get('Location',''));r.close()
            if target==url:raise ValueError('Invalid metadata redirect')
            url=target;continue
        r.raise_for_status();return r
    raise ValueError('Too many metadata redirects')
def save_image(raw):
    if len(raw)>8*1024*1024: raise ValueError('image too large')
    with Image.open(io.BytesIO(raw)) as im:
        im.verify(); fmt=im.format
    ext={'JPEG':'jpg','PNG':'png','WEBP':'webp'}.get(fmt)
    if not ext: raise ValueError('unsupported image')
    path='images/'+digest(raw)+'.'+ext
    (DOCS/path).parent.mkdir(parents=True,exist_ok=True);(DOCS/path).write_bytes(raw);return path
def validate(catalog):
    assert catalog.get('metadataPolicy')==POLICY, 'Unsupported Chinese metadata policy'
    entries=catalog['entries'];assert 50<=len(entries)<=2000
    seen=set()
    for e in entries:
        assert re.fullmatch('[a-z0-9-]{1,150}',e['slug']) and e['slug'] not in seen;seen.add(e['slug'])
        assert e['kind'] in ('movie','series') and e['en']
        assert not e.get('zh') or clean_zh(e['zh']) is not None, 'Non-mainland metadata rejected'
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
    manifest={'schema':1,'metadata_policy':POLICY,'version':sha,'catalog_path':path,'catalog_sha256':sha,'item_count':len(value['entries']),
              'image_count':len(images),'images':images,'checked_at':checked_at,'publication_mode':mode}
    # The manifest is written last; only complete data snapshots become active.
    (DOCS/'catalog.json').write_bytes(raw);(DOCS/'version.json').write_bytes(raw_json(manifest))
    print(json.dumps({'version':sha,'entries':len(value['entries']),'images':len(images),'mode':mode}))
def collect(previous):
    rows=get(INDEX).json()['results']['originals'];old={e['slug']:e for e in previous['entries']}
    seeds={e['slug']:e for e in load(ROOT/'data/seed.json')['entries']}
    mainland=load(ROOT/'data/mainland-catalog.json')['records']
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
        # Localized fields come exclusively from mainland policy data.
        e=clean_entry(e)
        if not e.get('zh') and slug in mainland:e['zh']=clean_zh(mainland[slug]);e['chinesePending']=not bool(e['zh'])
        return e
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: entries=list(pool.map(entry,rows))
    return {'entries':entries,'complete':True,'metadataPolicy':POLICY}
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
