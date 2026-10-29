"""Bounded Chinese title calibration. Only source-verified names become searchable aliases."""
import argparse, copy, hashlib, json, os, re
from datetime import datetime,timedelta,timezone
from pathlib import Path
from catalog import ROOT,DOCS,load,publish,validate
from title_sources import Lookup,chinese,norm
QUERY_VERSION='zh-cn-v2'

def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(path)
def read(path,default):return load(path) if path.exists() else copy.deepcopy(default)
def keys_from_env():
    return list(dict.fromkeys(v for name in ('TAVILY_API_KEY_1','TAVILY_API_KEY_2','TAVILY_API_KEY') if (v:=os.getenv(name,'').strip())))
def clean(value,keys):
    raw=json.dumps(value,ensure_ascii=False)
    for key in keys:raw=raw.replace(key,'[REDACTED]')
    return json.loads(re.sub(r'tvly-[A-Za-z0-9_-]{12,}','[REDACTED]',raw))
def identity(entry,hint):
    zh=entry.get('zh') or {};date=zh.get('date') or hint.get('year') or entry.get('releaseDate','')
    year=str(date)[:4];year=year if re.fullmatch(r'(19|20)\d{2}',year) else ''
    umc=re.search(r'umc\.cmc\.[a-z0-9]+',zh.get('watchUrl',''))
    return {'slug':entry['slug'],'english_title':entry['en'],'kind':entry['kind'],'year':year,'official_id':umc.group() if umc else ''}
def cache_key(ident):return hashlib.sha256(json.dumps(ident,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def record(entry,hint):
    ident=identity(entry,hint)
    # An existing regional name must not prevent verifying a different mainland alias.
    return {'english_title':entry['en'],'original_title':entry['en'],'kind':'movie' if entry['kind']=='movie' else 'tv','year':ident['year'],'display_name_zh':'',
            'search_name_hint':' '.join(dict.fromkeys([(entry.get('zh') or {}).get('title','')]+hint.get('aliases',[])))[:180]}
def apply_verified(entry,cached,ident):
    out=copy.deepcopy(entry)
    if cached.get('identity')!=ident or cached.get('status')!='verified':return out
    patch=cached.get('patch') or {}
    if not chinese(patch.get('display_name_zh')) or not patch.get('sources'):return out
    zh=out.setdefault('zh',{}) or {};out['zh']=zh
    old=zh.get('title','');name=patch['display_name_zh']
    aliases=list(dict.fromkeys([name]+patch.get('aliases_zh',[])+zh.get('aliases',[])+[old]))
    zh.update(title=name,aliases=[s for s in aliases if s],name_status='verified_title_sources',name_checked_at=patch.get('name_checked_at'),name_sources=patch['sources'])
    # Only title fields change. Synopsis/cast/date/season/posters remain tied to existing identities.
    out['nameStatus']='verified_title_sources';out['titleIdentity']=ident;return out

class SearchClient:
    def __init__(self,keys,session=None):
        self.keys=keys;self.session=session;self.index=0;self.stopped=False;self.requests=0;self.statuses=[]
        self.direct_client=Lookup('',session=session)
    def direct(self,reference,checked_at):return self.direct_client.direct(reference,checked_at)
    def verify(self,reference,results,checked_at):return self.direct_client.verify_results(reference,results,checked_at)
    def search(self,reference,checked_at,reserve):
        if not self.keys:return None,{'status':'missing_api_key','results':[]}
        while self.index<len(self.keys):
            if not reserve():return None,{'status':'monthly_budget_exhausted','results':[]}
            lookup=Lookup(self.keys[self.index],session=self.session);self.requests+=1
            patch,evidence=lookup.search(reference,checked_at)
            error=evidence.get('error','')
            self.statuses.append({'key_slot':self.index+1,'http_status':int(error.split()[-1]) if re.fullmatch(r'HTTP \d{3}',error) else (0 if error else 200)})
            if error in ('HTTP 401','HTTP 403','search_unavailable') and self.index+1<len(self.keys):
                self.index+=1;continue
            # Respect throttling/quota errors; do not switch keys to bypass rate limits.
            self.stopped=lookup.stopped
            return patch,clean(evidence,self.keys)
        return None,{'status':'api_keys_unavailable','results':[]}

def run(root=ROOT,*,force=False,limit=12,monthly_limit=100,clock=None,client=None,slugs=None):
    clock=clock or datetime.now(timezone.utc);checked=clock.isoformat(timespec='seconds');month=clock.strftime('%Y-%m')
    docs=root/'docs';path=root/'data/title-cache.json'
    cache=read(path,{'schema':1,'records':{},'budgets':{}});assert cache.get('schema')==1
    if not force and cache.get('last_run_at') and 0<=(clock-datetime.fromisoformat(cache['last_run_at'])).total_seconds()<604800:
        print('Title lookup not due; keep verified names and cached evidence');return None
    hints=read(root/'data/title-requests.json',{'records':{}})['records']
    current=read(docs/'catalog.json',{});version=read(docs/'version.json',{});entries=copy.deepcopy(current['entries'])
    client=client or SearchClient(keys_from_env());limit=max(0,min(int(limit),20));monthly_limit=max(0,min(int(monthly_limit),200))
    used=int(cache.setdefault('budgets',{}).get(month,0))
    report={'checked_at':checked,'api_configured':bool(client.keys),'attempted':0,'searched':0,'direct_verified':0,'cache_hits':0,'verified_changes':[],
            'monthly_limit':monthly_limit,'pending':0,'reused_verified':0,'status':'completed'}
    def reserve():
        nonlocal used
        if used>=monthly_limit:return False
        used+=1;cache['budgets'][month]=used;dump(path,clean(cache,client.keys));report['searched']+=1;return True
    order={e['slug']:i for i,e in enumerate(entries)}
    entries.sort(key=lambda e:(not hints.get(e['slug'],{}).get('sourceMatchPending',False),bool(chinese((e.get('zh') or {}).get('title'))),cache['records'].get(cache_key(identity(e,hints.get(e['slug'],{}))),{}).get('checked_at',''),e['slug']))
    output=[]
    for e in entries:
        hint=hints.get(e['slug'],{});ident=identity(e,hint);key=cache_key(ident);old=cache['records'].get(key,{})
        original=copy.deepcopy(e);e=apply_verified(e,old,ident)
        if e!=original:report['cache_hits']+=1
        if old.get('status')=='verified' and old.get('identity')==ident:
            report['reused_verified']+=1;output.append(e);continue
        if hint.get('matchedSource') and chinese((e.get('zh') or {}).get('title')):
            report['reused_verified']+=1;output.append(e);continue
        if slugs and e['slug'] not in slugs:output.append(e);continue
        if not ident['year'] or (old.get('query_version')==QUERY_VERSION and old.get('next_retry_at','')>checked) or report['attempted']>=limit:
            output.append(e);continue
        if e.get('releaseDate','')>clock.date().isoformat() and e.get('seasonNumber',1)==1:
            output.append(e);continue
        report['attempted']+=1;ref=record(e,hint);patch=None;evidence={'status':'direct_source'}
        if old.get('identity')==ident and old.get('evidence',{}).get('results'):
            patch=client.verify(ref,old['evidence']['results'],checked)
        if not patch:patch=client.direct(ref,checked)
        if patch:report['direct_verified']+=1
        elif not client.stopped:patch,evidence=client.search(ref,checked,reserve)
        entry={'identity':ident,'query_version':QUERY_VERSION,'status':'verified' if patch else 'pending_review','checked_at':checked,'evidence':evidence,
               'next_retry_at':(clock+timedelta(days=1 if evidence.get('status')=='missing_api_key' else 30)).isoformat(timespec='seconds')}
        if patch:
            entry['patch']=patch;e=apply_verified(e,entry,ident)
            report['verified_changes'].append({'slug':e['slug'],'before':(original.get('zh') or {}).get('title',''),'after':e['zh']['title'],'aliases':e['zh']['aliases']})
        else:report['pending']+=1
        cache['records'][key]=clean(entry,client.keys);output.append(e)
    output.sort(key=lambda e:order[e['slug']]);cache['last_run_at']=checked
    report['monthly_reserved']=used;report['remaining_unverified']=sum(e.get('nameStatus')!='verified_title_sources' for e in output)
    report['api_results']=getattr(client,'statuses',[])
    report['status']='degraded' if client.stopped else ('missing_api_key' if not client.keys else 'completed')
    dump(path,clean(cache,client.keys));dump(root/'logs/title-lookup.json',clean(report,client.keys))
    if output!=current['entries']:
        updated=copy.deepcopy(current);updated['entries']=output
        publish(updated,version.get('checked_at'),'verified-title-calibration')
    print(json.dumps(clean(report,client.keys),ensure_ascii=False,indent=2));return report

def reapply_cache(catalog,root=ROOT):
    cached=read(root/'data/title-cache.json',{'records':{}})['records'];hints=read(root/'data/title-requests.json',{'records':{}})['records']
    for i,e in enumerate(catalog['entries']):
        ident=identity(e,hints.get(e['slug'],{}));catalog['entries'][i]=apply_verified(e,cached.get(cache_key(ident),{}),ident)
    return catalog
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--force',action='store_true');parser.add_argument('--slug',action='append');args=parser.parse_args()
    try:run(force=args.force,limit=os.getenv('TITLE_LOOKUP_LIMIT','12'),monthly_limit=os.getenv('TITLE_LOOKUP_MONTHLY_LIMIT','100'),slugs=args.slug)
    except Exception as exc:print('Title lookup aborted:',type(exc).__name__,'(credentials and transport omitted)');raise SystemExit(1)
