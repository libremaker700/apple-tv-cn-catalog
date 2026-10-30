"""Bounded Chinese title calibration. Only source-verified names become searchable aliases."""
import argparse, copy, hashlib, json, os, re
from datetime import datetime,timedelta,timezone
from pathlib import Path
from catalog import ROOT,DOCS,load,publish,validate
from title_sources import Lookup,chinese,norm
from metadata_policy import POLICY,allowed_source,clean_entry
from summary_cache import apply_summary,reapply_summaries
QUERY_VERSION='zh-cn-v5-mainland-summary'

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
    zh=entry.get('zh') or {};official=entry.get('officialIdentity') or {};date=zh.get('_identityYear') or official.get('year') or zh.get('date') or hint.get('year') or entry.get('releaseDate','')
    year=str(date)[:4];year=year if re.fullmatch(r'(19|20)\d{2}',year) else ''
    umc=re.search(r'umc\.cmc\.[a-z0-9]+',official.get('watchUrl') or zh.get('watchUrl',''))
    return {'slug':entry['slug'],'english_title':entry['en'],'kind':entry['kind'],'year':year,'official_id':umc.group() if umc else ''}
def cache_key(ident):return hashlib.sha256(json.dumps(ident,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def record(entry,hint):
    ident=identity(entry,hint)
    animated=entry['kind']=='series' and any(str(g).casefold() in ('animation','动画','動畫') for g in entry.get('genres',[]))
    # An existing regional name must not prevent verifying a different mainland alias.
    return {'english_title':entry['en'],'original_title':entry['en'],'kind':'movie' if entry['kind']=='movie' else ('anime' if animated else 'tv'),'year':ident['year'],'display_name_zh':'',
            'search_name_hint':' '.join(dict.fromkeys([(entry.get('zh') or {}).get('title','')]+hint.get('aliases',[])))[:180]}
def needs_title_review(entry,hint):
    title=(entry.get('zh') or {}).get('title','')
    aliases={norm(name) for name in hint.get('aliases',[]) if chinese(name)}
    # A playable source ID alone does not verify the regional display name.
    return not ((entry.get('zh') or {}).get('metadataPolicy')==POLICY and hint.get('matchedSource') and chinese(title) and norm(title) in aliases)
def apply_verified(entry,cached,ident):
    out=clean_entry(entry)
    if cached.get('identity')!=ident or cached.get('status')!='verified':return out
    patch=cached.get('patch') or {}
    if patch.get('metadataPolicy')!=POLICY or not chinese(patch.get('display_name_zh')) or not patch.get('sources') or any(not allowed_source(s.get('url','')) for s in patch['sources']):return out
    zh=out.setdefault('zh',{}) or {};out['zh']=zh
    old=zh.get('title','');name=patch['display_name_zh']
    aliases=list(dict.fromkeys([name]+patch.get('aliases_zh',[])+zh.get('aliases',[])+[old]))
    zh.update(title=name,aliases=[s for s in aliases if s],metadataPolicy=POLICY,provenance='verified_mainland_title',name_status='verified_title_sources',name_checked_at=patch.get('name_checked_at'),name_sources=patch['sources'],_identityYear=int(ident['year']))
    if not zh.get('watchUrl'):zh['watchUrl']=(out.get('officialIdentity') or {}).get('watchUrl','')
    # Cast/date/seasons/posters keep their identities; a separately verified synopsis may fill a gap.
    out['nameStatus']='verified_title_sources';out['titleIdentity']=ident;out['chinesePending']=False
    return apply_summary(out,cached,ident)

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
    # Each record already has its own retry time. A week-wide gate stalled newly added works too.
    if not force and cache.get('last_policy')==POLICY and cache.get('last_run_at') and 0<=(clock-datetime.fromisoformat(cache['last_run_at'])).total_seconds()<6*3600:
        print('Title lookup not due; keep verified names and cached evidence');return None
    hints=read(root/'data/title-requests.json',{'records':{}})['records']
    current=read(docs/'catalog.json',{});version=read(docs/'version.json',{});entries=reapply_summaries(copy.deepcopy(current),root,identity)['entries']
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
        title_verified=old.get('status')=='verified' and old.get('identity')==ident
        summary_needed=not chinese((e.get('zh') or {}).get('summary',''))
        if title_verified and not summary_needed:
            report['reused_verified']+=1;output.append(e);continue
        if not needs_title_review(e,hint) and not summary_needed:
            report['reused_verified']+=1;output.append(e);continue
        if slugs and e['slug'] not in slugs:output.append(e);continue
        retry_field='summary_next_retry_at' if title_verified else 'next_retry_at'
        if not ident['year'] or (old.get('query_version')==QUERY_VERSION and old.get(retry_field,'')>checked) or report['attempted']>=limit:
            output.append(e);continue
        # Mainland presentation metadata can be verified before release;
        # the app's independent release/playback gates stay intact.
        report['attempted']+=1;ref=record(e,hint);patch=None;evidence={'status':'direct_source'}
        if old.get('identity')==ident and old.get('evidence',{}).get('results'):
            patch=client.verify(ref,old['evidence']['results'],checked)
        if patch and title_verified and summary_needed and not patch.get('summary_zh'):patch=None
        if not patch:patch=client.direct(ref,checked)
        if patch and title_verified and summary_needed and not patch.get('summary_zh'):patch=None
        if patch:report['direct_verified']+=1
        elif not client.stopped:patch,evidence=client.search(ref,checked,reserve)
        if not patch and evidence.get('status')=='monthly_budget_exhausted':
            # No search happened: leave it in the queue instead of imposing a 30-day failed-search retry.
            report['budget_deferred']=report.get('budget_deferred',0)+1;output.append(e);continue
        entry={'identity':ident,'query_version':QUERY_VERSION,'status':'verified' if patch else 'pending_review','checked_at':checked,'evidence':evidence,
               'next_retry_at':(clock+timedelta(days=1 if evidence.get('status')=='missing_api_key' else 30)).isoformat(timespec='seconds')}
        if title_verified:
            entry=copy.deepcopy(old);entry.update(query_version=QUERY_VERSION,summary_evidence=evidence,summary_checked_at=checked,
                summary_next_retry_at=(clock+timedelta(days=1 if evidence.get('status')=='missing_api_key' else 30)).isoformat(timespec='seconds'))
            # Missing synopsis must not erase a previously verified name or its evidence.
            if patch and patch.get('summary_zh'):
                entry['patch'].update({k:patch[k] for k in ('summary_zh','summary_sources','summary_checked_at') if k in patch})
            else:patch=None
        if patch:
            if not title_verified:entry['patch']=patch
            e=apply_verified(e,entry,ident)
            if not patch.get('summary_zh'):entry['summary_next_retry_at']=(clock+timedelta(days=30)).isoformat(timespec='seconds')
            report['verified_changes'].append({'slug':e['slug'],'before':(original.get('zh') or {}).get('title',''),'after':e['zh']['title'],'aliases':e['zh']['aliases']})
        else:report['pending']+=1
        cache['records'][key]=clean(entry,client.keys);output.append(e)
    output.sort(key=lambda e:order[e['slug']]);cache['last_run_at']=checked;cache['last_policy']=POLICY
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
    return reapply_summaries(catalog,root,identity)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--force',action='store_true');parser.add_argument('--slug',action='append');args=parser.parse_args()
    try:run(force=args.force,limit=os.getenv('TITLE_LOOKUP_LIMIT','12'),monthly_limit=os.getenv('TITLE_LOOKUP_MONTHLY_LIMIT','100'),slugs=args.slug)
    except Exception as exc:print('Title lookup aborted:',type(exc).__name__,'(credentials and transport omitted)');raise SystemExit(1)
