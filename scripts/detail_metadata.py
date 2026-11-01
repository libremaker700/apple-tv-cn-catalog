"""Atomic, season-specific Douban presentation packets; never derived from CMS scores."""
import copy,json,math,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit

def valid(packet,kind=None):
    if not isinstance(packet,dict) or packet.get('schema')!=1 or packet.get('source')!='douban':return False
    sid=packet.get('subjectId');season=packet.get('season');year=packet.get('year')
    if not isinstance(sid,str) or not re.fullmatch(r'[1-9][0-9]{4,9}',sid) or packet.get('sourceUrl')!='https://movie.douban.com/subject/'+sid+'/':return False
    if type(season)is not int or not 0<=season<=100 or kind=='movie' and season!=0 or kind=='series' and season<1:return False
    if type(year)is not int or not 1900<=year<=2099 or not isinstance(packet.get('checkedAt'),str) or not packet['checkedAt']:return False
    try:
        if datetime.fromisoformat(packet['checkedAt']).tzinfo is None:return False
    except ValueError:return False
    if not isinstance(packet.get('title'),str) or not re.search(r'[\u3400-\u9fff]',packet['title']):return False
    summary=packet.get('summary');status=packet.get('summaryStatus')
    if not isinstance(summary,str) or len(summary)>600 or re.search(r'https?://|<[^>]+>',summary):return False
    if status=='AVAILABLE':
        if len(summary)<35 or len(re.findall(r'[\u3400-\u9fff]',summary))<20:return False
    elif status!='PENDING' or summary:return False
    if packet.get('ratingStatus')=='AVAILABLE':
        value=packet.get('rating');count=packet.get('ratingCount')
        if type(value)not in(int,float)or not math.isfinite(value)or not 0<value<=10 or type(count)is not int or count<=0:return False
    elif packet.get('ratingStatus')!='NO_RATING' or 'rating'in packet or 'ratingCount'in packet:return False
    return True

def from_patch(patch,ref):
    sid=str(patch.get('douban_id')or'')
    if not re.fullmatch(r'[1-9][0-9]{4,9}',sid)or patch.get('rating_status')not in('AVAILABLE','NO_RATING'):return None
    number=0 if ref.get('kind')=='movie'else int(ref.get('season')or 1)
    summary=str(patch.get('summary_zh')or'')
    from summary_cache import valid_summary
    if not valid_summary(summary):summary=''
    url='https://movie.douban.com/subject/'+sid+'/'
    if not any(s.get('url')==url for s in patch.get('summary_sources',[])):summary=''
    checked=str(patch.get('name_checked_at')or'')
    if checked.isdigit():checked=datetime.fromtimestamp(int(checked),timezone.utc).isoformat(timespec='seconds')
    packet={'schema':1,'source':'douban','subjectId':sid,'sourceUrl':'https://movie.douban.com/subject/'+sid+'/',
        'title':patch.get('display_name_zh',''),'summary':summary,'summaryStatus':'AVAILABLE'if summary else'PENDING',
        'ratingStatus':patch.get('rating_status','NO_RATING'),'season':number,'year':int(patch.get('release_year')or ref['year']),
        'checkedAt':checked,'originalTitle':ref.get('english_title')or ref.get('original_title','')}
    if packet['ratingStatus']=='AVAILABLE':packet.update(rating=patch.get('douban_rating'),ratingCount=patch.get('douban_rating_count'))
    return packet if valid(packet,'movie'if ref.get('kind')=='movie'else'series')else None

def attach(work,packet):
    if not valid(packet,work['kind']):return False
    expected=next((s.get('year')for s in work.get('seasons',[])if s.get('season')==packet['season']),None)
    if expected and str(expected)!=str(packet['year']):return False
    zh=work.setdefault('zh',{})or{};work['zh']=zh
    if any(p.get('subjectId')==packet['subjectId']and p.get('season')!=packet['season']for p in zh.get('detailSeasons',[])):return False
    rows=[p for p in zh.get('detailSeasons',[])if valid(p,work['kind'])and p['season']!=packet['season']]
    zh['metadataPolicy']='mainland-v1'
    rows.append(copy.deepcopy(packet));zh['detailSeasons']=sorted(rows,key=lambda p:p['season'])
    # This compatibility pointer has its own season; consumers must compare it before use.
    zh['detailMetadata']=copy.deepcopy(packet)
    return True

def work_id(work):
    return work.get('officialId')or urlsplit((work.get('officialIdentity')or{}).get('watchUrl','')).path.rstrip('/').split('/')[-1]or'pr:'+work['slug']

def remember(work,packet,root):
    if not attach(work,packet):return False
    path=root/'data/detail-metadata-cache.json';cache=json.loads(path.read_text(encoding='utf8'))if path.exists()else{'schema':1,'works':{}}
    identity=work_id(work);old=cache['works'].get(identity,{})
    if old and (old.get('en')!=work['en']or old.get('kind')!=work['kind']):raise ValueError('Detail work identity changed')
    if any(p.get('subjectId')==packet['subjectId']and p.get('season')!=packet['season']for p in old.get('details',[])):raise ValueError('A Douban subject cannot label two seasons')
    rows=[p for p in old.get('details',[])if valid(p,work['kind'])and p['season']!=packet['season']]+[packet]
    cache['works'][identity]={'en':work['en'],'kind':work['kind'],'details':sorted(rows,key=lambda p:p['season'])}
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(cache,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(path)
    return True

def apply_cached(value,root,home=False):
    out=copy.deepcopy(value);path=root/'data/detail-metadata-cache.json'
    if not path.exists():return out
    cache=json.loads(path.read_text(encoding='utf8'));assert cache.get('schema')==1
    for work in out.get('works'if home else'entries',[]):
        row=cache['works'].get(work_id(work),{})
        if row.get('en')!=work['en']or row.get('kind')!=work['kind']:continue
        for packet in row.get('details',[]):attach(work,packet)
    return out

def migrate_verified(root):
    """Reuse only already verified complete source patches, never combine loose old fields."""
    main=json.loads((root/'docs/catalog.json').read_text(encoding='utf8'));by_slug={e['slug']:e for e in main['entries']};count=0
    title=root/'data/title-cache.json'
    for old in(json.loads(title.read_text(encoding='utf8')).get('records',{}).values()if title.exists()else[]):
        ident=old.get('identity',{});work=by_slug.get(ident.get('slug'));patch=old.get('patch')or{}
        if not work or old.get('status')!='verified'or ident.get('english_title')!=work['en']or ident.get('kind')!=work['kind']:continue
        if not any(s.get('type')=='douban_mobile_identity'for s in patch.get('sources',[])):continue
        packet=from_patch(patch,{'kind':'movie'if work['kind']=='movie'else'tv','year':ident['year'],'season':1,'english_title':work['en']})
        if packet and remember(work,packet,root):count+=1
    home=json.loads((root/'docs/home/home.json').read_text(encoding='utf8'));home_cache=root/'data/home-title-cache.json'
    rows=json.loads(home_cache.read_text(encoding='utf8')).get('records',{})if home_cache.exists()else{}
    for work in home['works']:
        old=rows.get(work['officialId'],{});patch=old.get('patch')or{}
        if old.get('en')!=work['en']or str(old.get('year'))!=str(work.get('year'))or not any(s.get('type')=='douban_mobile_identity'for s in patch.get('sources',[])):continue
        packet=from_patch(patch,{'kind':'movie'if work['kind']=='movie'else'tv','year':old['year'],'season':1,'english_title':work['en']})
        if packet and remember(work,packet,root):count+=1
    return count
