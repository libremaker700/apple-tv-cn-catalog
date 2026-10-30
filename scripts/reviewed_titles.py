"""Reapply audited title identities without replacing seasons, artwork or playback bindings."""
import copy,json,re
from pathlib import Path
from metadata_policy import POLICY

def norm(s):return re.sub(r'[^a-z0-9\u3400-\u9fff]','',str(s or '').casefold())
def base(s):return re.sub(r'\s*(?:第\s*[一1]\s*季|season\s*1)\s*$','',str(s or ''),flags=re.I).strip()
def records(root):
    path=root/'data/reviewed-title-import.json'
    if not path.exists():return []
    data=json.loads(path.read_text(encoding='utf-8'));assert data['schema']==1
    seen=set()
    for r in data['records']:
        assert re.fullmatch(r'[a-z0-9-]{1,150}',r['slug'])and r['slug']not in seen;seen.add(r['slug'])
        assert r['kind']in('movie','series')and re.fullmatch(r'umc\.cmc\.[a-z0-9]+',r['officialId'])
        assert re.fullmatch(r'https://tv\.apple\.com/us/'+('movie'if r['kind']=='movie'else'show')+r'/[^/?#]+/'+re.escape(r['officialId']),r['watchUrl'])
        s=r['subject'];assert re.fullmatch(r'\d{1,12}',s['id'])and s['type']==('movie'if r['kind']=='movie'else'tv')
        assert norm(base(r['en']))in {norm(base(t))for t in [s['original_title']]+s['aka']}
        assert norm(base(r['title']))in {norm(base(t))for t in [s['title']]+s['aka']}
        assert re.search(r'[\u3400-\u9fff]',r['title'])and re.fullmatch(r'(19|20)\d{2}',str(s['year']))
        assert r['year']==int(s['year'])
    return data['records']

def localized(previous,r,checked):
    zh=copy.deepcopy(previous or {})
    # A later independent verified name is kept; this audited title remains searchable.
    keep=zh.get('name_status')=='verified_title_sources'and zh.get('title')and norm(zh['title'])!=norm(r['title'])
    old=zh.get('title','');zh['aliases']=list(dict.fromkeys([r['title'],r['en']]+zh.get('aliases',[])+([old]if old else[])))
    if keep:return zh
    zh.update(metadataPolicy=POLICY,title=r['title'],name_status='verified_title_sources',name_checked_at=checked,provenance='audited_title_import',name_sources=[{'type':'douban_mobile_identity','url':'https://movie.douban.com/subject/'+r['subject']['id']+'/','retrieved_at':checked}])
    if not zh.get('watchUrl'):zh['watchUrl']=r['watchUrl']
    # Film source matching uses original premiere year; official platform dates stay untouched.
    if r['kind']=='movie':zh['searchYear']=r['year']
    return zh

def apply_catalog(catalog,root):
    out=copy.deepcopy(catalog);data=records(root);index={r['slug']:r for r in data}
    checked=json.loads((root/'data/reviewed-title-import.json').read_text(encoding='utf-8'))['checkedAt']if data else''
    for e in out['entries']:
        r=index.get(e['slug'])
        if not r:continue
        if norm(e['en'])!=norm(r['en'])or e['kind']!=r['kind']:raise ValueError('Reviewed title identity changed')
        current=(e.get('officialIdentity')or{}).get('watchUrl','').rstrip('/').split('/')[-1]
        if current!=r['officialId']:raise ValueError('Reviewed official identity changed')
        e['zh']=localized(e.get('zh'),r,checked);e['nameStatus']='verified_title_sources';e['chinesePending']=False
    return out

def apply_home(home,root):
    out=copy.deepcopy(home);data=records(root);index={r['officialId']:r for r in data}
    if not data:return out
    checked=json.loads((root/'data/reviewed-title-import.json').read_text(encoding='utf-8'))['checkedAt']if data else''
    for w in out['works']:
        r=index.get(w['officialId'])
        if not r:continue
        if w['slug']!=r['slug']or norm(w['en'])!=norm(r['en'])or w['kind']!=r['kind']:raise ValueError('Reviewed home identity changed')
        w['zh']=localized(w.get('zh'),r,checked)
    return out

def publish_reviewed(root):
    import hashlib,time
    from catalog import load,publish,raw_json
    from home_sync import validate,validate_publication
    folder=root/'docs';main=load(folder/'catalog.json');manifest=load(folder/'version.json')
    publish(apply_catalog(main,root),manifest.get('checked_at'),'audited-workbook-title-import')
    home=apply_home(load(folder/'home/home.json'),root);validate(home);m=load(folder/'home/version.json');blob=raw_json(home);sha=hashlib.sha256(blob).hexdigest()
    if sha!=m['version']:
        path='releases/'+sha+'/home.json';(folder/'home'/path).parent.mkdir(parents=True,exist_ok=True);(folder/'home'/path).write_bytes(blob)
        m.update(path=path,version=sha,checkedAt=int(time.time()));(folder/'home/home.json').write_bytes(blob);(folder/'home/version.json').write_bytes(raw_json(m))
    validate_publication();print(json.dumps({'importedTitles':len(records(root)),'homeVersion':sha}))

if __name__=='__main__':publish_reviewed(Path(__file__).resolve().parents[1])
