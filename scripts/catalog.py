"""Public Apple TV metadata + content-addressed image publication. No playback credentials."""
import argparse, concurrent.futures, copy, hashlib, io, json, os, re, time
from pathlib import Path
from datetime import datetime, timezone
import requests
from urllib.parse import urljoin
from PIL import Image
from metadata_policy import POLICY,allowed_source,clean_entry,clean_zh
from season_sync import Collector,label_seasons,public_seasons
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
        from detail_metadata import valid as valid_detail
        zh=e.get('zh')or{}
        assert all(valid_detail(packet,e['kind'])for packet in zh.get('detailSeasons',[])), 'Detail medium/season mismatch'
        assert not zh.get('detailMetadata')or valid_detail(zh['detailMetadata'],e['kind']), 'Detail medium mismatch'
        assert e['officialUrl']=='https://www.apple.com/tv-pr/originals/'+e['slug']+'/'
        assert not any(k in e for k in ('id','sourceIds','playUrl','token','headers'))
        seasons=e.get('seasons') or [];numbers=set()
        for season in seasons:
            number=season.get('season');assert type(number) is int and 1<=number<=100 and number not in numbers,'Invalid or duplicate season';numbers.add(number)
            assert not any(k in season for k in ('id','sourceIds','playUrl','token','headers','utsk','utscf')),'Private season fields'
            if season.get('metadataStatus')=='verified':
                assert re.fullmatch(r'(19|20)\d\d',str(season.get('year',''))) and season.get('artwork'),'Incomplete verified season'
                assert season.get('officialId','').startswith('umc.cmc.') and season.get('showId')==e.get('officialIdentity',{}).get('watchUrl','').rstrip('/').split('/')[-1],'Season/show identity mismatch'
        for url in [e.get('artwork'),e.get('heroArtwork')]+[s.get('artwork') for s in seasons]:
            if not url: continue
            path=url.removeprefix(BASE);assert re.fullmatch(r'images/[a-f0-9]{64}\.(jpg|png|webp)',path)
            b=(DOCS/path).read_bytes();assert digest(b)==Path(path).stem
            with Image.open(io.BytesIO(b)) as im: im.verify()
def publish(catalog,checked_at,mode):
    value=copy.deepcopy(catalog)
    from reviewed_titles import apply_catalog
    value=apply_catalog(value,ROOT)
    from reviewed_names import apply as apply_names
    value=apply_names(value,ROOT)
    from work_summaries import apply_main
    value=apply_main(value,ROOT)
    from detail_metadata import apply_cached as apply_details
    value=apply_details(value,ROOT)
    from list_artwork import apply_cached as apply_list_artwork
    value=apply_list_artwork(value,ROOT)
    from season_scope import apply as apply_season_scope
    for entry in value['entries']:apply_season_scope(entry,ROOT)
    images={}
    for e in value['entries']:
        from source_availability import apply_cached
        apply_cached(e,ROOT)
        e['chinesePending']=not bool(re.search(r'[\u3400-\u9fff]',str((e.get('zh')or{}).get('title',''))))
        e.pop('seasonCheckedAt',None)
        if e.get('seasons'):e['seasons']=public_seasons(e['seasons'])
        label_seasons(e)
        for row,keys in [(e,('artwork','heroArtwork'))]+[(s,('artwork',)) for s in e.get('seasons',[])]:
            for key in keys:
                if row.get(key):
                    p=row[key].removeprefix(BASE);b=(DOCS/p).read_bytes();images[p]={'sha256':digest(b),'bytes':len(b)};row[key]=BASE+p
    if isinstance(value.get('seasonStats'),dict):value['seasonStats'].pop('checkedAt',None)
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
    cache_file=ROOT/'data/season-cache.json'
    preferences_file=ROOT/'data/artwork-preferences.json'
    preferences=load(preferences_file) if preferences_file.exists() else {'schema':1,'seasons':{}}
    assert preferences.get('schema')==1, 'Unsupported artwork preferences'
    collector=Collector(get,save_image,lambda p:bool(p) and (DOCS/p.removeprefix(BASE)).is_file(),load(cache_file) if cache_file.exists() else None,
                        artwork_preferences=preferences['seasons'])
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
        from season_scope import apply as apply_season_scope
        result=apply_season_scope(collector.sync(e,seeds.get(slug,{})),ROOT)
        from candidate_name_rules import apply_kind
        hints=load(ROOT/'data/name-search-hints.json').get('works',{})if(ROOT/'data/name-search-hints.json').exists()else{}
        apply_kind(result,hints.get(slug,{}));return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: entries=list(pool.map(entry,rows))
    cache_file.write_bytes(raw_json(collector.cache))
    report={'checkedAt':collector.now,'verified':sum(r['status']=='verified' for r in collector.report),'pending':sum(r['status']=='pending' for r in collector.report),'works':sorted(collector.report,key=lambda r:r['slug'])}
    (DOCS/'season-sync-report.json').write_bytes(raw_json(report))
    print(json.dumps({'season_sync':{k:v for k,v in report.items() if k!='works'}}))
    return {'entries':entries,'complete':True,'metadataPolicy':POLICY,'seasonSchema':1,'seasonStats':{k:v for k,v in report.items() if k not in ('works','checkedAt')}}
def main():
    p=argparse.ArgumentParser();p.add_argument('--seed',action='store_true');p.add_argument('--force',action='store_true');p.add_argument('--validate',action='store_true');a=p.parse_args()
    if a.validate:
        v=load(DOCS/'version.json');raw=(DOCS/v['catalog_path']).read_bytes();assert digest(raw)==v['catalog_sha256'];validate(json.loads(raw));print('PASS complete catalog and all image hashes');return
    if a.seed: publish(load(ROOT/'data/seed.json'),None,'bundled-reviewed-snapshot');return
    prior=load(DOCS/'catalog.json');manifest=load(DOCS/'version.json');last=manifest.get('checked_at') or 0
    if not a.force and time.time()-last<6*3600: print('Not due; retain verified snapshot');return
    value=collect(prior)
    from title_lookup import reapply_cache
    value=reapply_cache(value);publish(value,int(time.time()),'official-network-collection')
if __name__=='__main__':main()
