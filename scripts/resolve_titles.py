"""Small, incremental batch: verified cache -> Douban -> Wikipedia -> MiniMax -> Tavily.

Outputs metadata only. Native provider matching continues to enforce type/year/season identity.
"""
import argparse,copy,csv,io,json,os
from contextlib import redirect_stdout
from datetime import datetime,timedelta,timezone
from pathlib import Path
from catalog import ROOT,publish
from title_lookup import read,dump,identity,cache_key,record,apply_verified,SearchClient,keys_from_env,QUERY_VERSION,clean
from title_sources import Lookup,chinese,complete_patch,merge_patches,norm
from summary_cache import has_summary
from source_candidate import verify_candidate
from minimax_agent import credentials,MiniMaxAgent,AgentError,redact

def export_map(root,catalog,checked):
    rows=[]
    for entry in catalog['entries']:
        zh=entry.get('zh') or {};verified=zh.get('name_status')=='verified_title_sources'
        rows.append({'slug':entry['slug'],'english_title':entry['en'],'chinese_title':zh.get('title') or '未收录',
            'aliases':zh.get('aliases',[]),'douban_url':zh.get('douban_url',''),'douban_id':zh.get('douban_id',''),
            'type':entry['kind'],'year':identity(entry,{})['year'],
            'rating':zh.get('douban_rating') if zh.get('rating_status')=='AVAILABLE' else None,
            'rating_count':zh.get('douban_rating_count') if zh.get('rating_status')=='AVAILABLE' else None,
            'confidence':('NO_RATING' if zh.get('rating_status')=='NO_RATING' else 'VERIFIED') if verified else 'UNVERIFIED',
            'name_confidence':'VERIFIED' if verified else 'UNVERIFIED','sources':zh.get('name_sources',[]),
            'synopsis_available':has_summary(zh.get('summary','')),'provider_status':'NATIVE_CHECK_ON_OPEN'})
    dump(root/'docs/title-map.json',{'schema':1,'checked_at':checked,'records':rows})
    fields=['english_title','chinese_title','douban_url','douban_id','type','year','rating','rating_count','confidence','sources']
    out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=fields,lineterminator='\n');writer.writeheader()
    for row in rows:writer.writerow({k:json.dumps(row[k],ensure_ascii=False) if isinstance(row[k],list) else row[k] for k in fields})
    path=root/'docs/title-map.csv';tmp=path.with_suffix('.tmp');tmp.write_bytes(out.getvalue().encode('utf-8-sig'));tmp.replace(path)
    return rows

def run(root=ROOT,*,slugs=None,limit=3,force=False,credential_path=None,agent=None,lookup=None,search=None,clock=None,publish_changes=True):
    now=clock or datetime.now(timezone.utc);checked=now.isoformat(timespec='seconds');month=now.strftime('%Y-%m')
    catalog=read(root/'docs/catalog.json',{});updated=copy.deepcopy(catalog);version=read(root/'docs/version.json',{})
    hints=read(root/'data/title-requests.json',{'records':{}})['records']
    for slug,link in read(root/'data/identity-links.json',{'records':{}})['records'].items():hints.setdefault(slug,{}).update(link)
    cache_path=root/'data/title-cache.json';cache=read(cache_path,{'schema':1,'records':{},'budgets':{}})
    agent_path=root/'data/agent-title-cache.json';state=read(agent_path,{'schema':1,'budgets':{},'records':{}})
    keys=keys_from_env();cred=credentials(credential_path) if agent is None else None
    scrub=lambda value:redact(clean(value,keys),cred)
    lookup=lookup or Lookup(cache_path=root/'data/source-cache.json');search=search or SearchClient(keys,source_cache=root/'data/source-cache.json')
    report={'schema':1,'checked_at':checked,'order':['verified_cache','douban_mobile','wikipedia','minimax_candidate_and_independent_fetch','tavily'],
        'agent':{'status':'not_needed'},'records':[],'changed':[],'status':'completed'}
    work=[];limit=max(0,min(int(limit),5))
    ordered=sorted(updated['entries'],key=lambda e:(not hints.get(e['slug'],{}).get('sourceMatchPending',False),
        state['records'].get(cache_key(identity(e,hints.get(e['slug'],{}))),{}).get('checked_at',''),
        chinese((e.get('zh') or {}).get('title')),e['slug']))
    for entry in ordered:
        if slugs and entry['slug'] not in slugs:continue
        hint=hints.get(entry['slug'],{});ident=identity(entry,hint);key=cache_key(ident);old=cache['records'].get(key,{})
        verified=old.get('status')=='verified' and old.get('identity')==ident
        if verified and not record(entry,hint)['want_summary'] and not force:continue
        if not slugs and not hint.get('sourceMatchPending') and not record(entry,hint)['want_summary'] and chinese((entry.get('zh') or {}).get('title')):continue
        previous=state['records'].get(key,{})
        if not force and previous.get('next_retry_at','')>checked:continue
        if not ident['year'] or len(work)>=limit:continue
        ref=record(entry,hint);start=len(lookup.pages.events);patch=lookup.direct(ref,checked)
        row={'slug':entry['slug'],'english_title':entry['en'],'confidence':'VERIFIED' if patch else 'UNVERIFIED',
            'stages':copy.deepcopy(lookup.stages),'public_reads':lookup.pages.events[start:]}
        work.append({'entry':entry,'identity':ident,'key':key,'old':old,'reference':ref,'patch':patch,'row':row})
    unresolved=[w for w in work if not complete_patch(w['patch'],w['reference'])]
    used=int(state['budgets'].get(month,0));agent_limit=max(0,min(int(os.getenv('MINIMAX_MONTHLY_BATCH_LIMIT','20')),20))
    if unresolved:
        if agent is None and not cred:report['agent']={'status':'missing_credentials'}
        elif used>=agent_limit:report['agent']={'status':'monthly_budget_exhausted'}
        else:
            # Reserve the entire batch before network use. One failed auth must not turn into repeated calls.
            state['budgets'][month]=used+1;dump(agent_path,scrub(state))
            try:
                client=agent or MiniMaxAgent(cred)
                result=client.search([dict(w['reference'],slug=w['entry']['slug']) for w in unresolved])
                report['agent']={k:v for k,v in result.items() if k!='records'}
                for w in unresolved:
                    candidates=[r for r in result.get('records',[]) if r.get('slug')==w['entry']['slug']]
                    if len(candidates)!=1:continue
                    patch,status=verify_candidate(lookup,w['reference'],candidates[0],checked)
                    w['row']['agent_verification']=status
                    # Existing verified identity and two agreeing sources must not be displaced by a model guess.
                    known=(w['patch'] or {}).get('display_name_zh') or (w['old'].get('patch') or {}).get('display_name_zh')
                    if patch and known and norm(known) not in {norm(n) for n in [patch['display_name_zh']]+patch.get('aliases_zh',[])}:
                        patch=None;w['row']['agent_verification']='DISPUTED'
                    w['patch']=merge_patches(w['patch'],patch)
            except AgentError as exc:report['agent']={'status':exc.status}
            except Exception as exc:report['agent']={'status':type(exc).__name__}
    tavily_used=int(cache.setdefault('budgets',{}).get(month,0));tavily_limit=max(0,min(int(os.getenv('TITLE_LOOKUP_MONTHLY_LIMIT','100')),100))
    def reserve():
        nonlocal tavily_used
        if tavily_used>=tavily_limit:return False
        tavily_used+=1;cache['budgets'][month]=tavily_used;dump(cache_path,scrub(cache));return True
    for w in work:
        patch=w['patch'];row=w['row'];old=w['old'];ident=w['identity'];entry=w['entry'];ref=w['reference']
        if not complete_patch(patch,ref) and not search.stopped:
            found,evidence=search.search(ref,checked,reserve);patch=merge_patches(patch,found)
            row['tavily_status']=evidence.get('status') or evidence.get('error')
            row['tavily_usage']=evidence.get('usage')
        saved=copy.deepcopy(old) if old.get('status')=='verified' and old.get('identity')==ident else {'identity':ident}
        saved.update(query_version=QUERY_VERSION,checked_at=checked,next_retry_at=(now+timedelta(days=1)).isoformat(timespec='seconds'))
        if patch:
            # Retain the prior verified title when only a separately verified synopsis is filled.
            if saved.get('patch'):
                prior=saved['patch'];saved['patch']=merge_patches(prior,patch)
            else:saved['patch']=patch
            saved['status']='verified';fresh=apply_verified(entry,saved,ident)
            if fresh!=entry:
                updated['entries'][updated['entries'].index(entry)]=fresh
                report['changed'].append({'slug':entry['slug'],'title':fresh['zh']['title'],'synopsis':has_summary(fresh['zh'].get('summary',''))})
            row['confidence']='VERIFIED';row['sources']=saved['patch'].get('sources',[])
        else:
            saved.setdefault('status','pending_review');row['confidence']=row.get('agent_verification','UNVERIFIED')
            if saved['status']=='verified':
                row['refresh_confidence']=row['confidence'];row['confidence']='VERIFIED';row['sources']=saved['patch'].get('sources',[])
        saved['resolver_evidence']=row;cache['records'][w['key']]=saved
        state['records'][w['key']]={'checked_at':checked,'next_retry_at':saved['next_retry_at'],'confidence':row['confidence']}
        report['records'].append(row)
    report['tavily_reserved']=tavily_used;report['agent_batches_reserved']=state['budgets'].get(month,0)
    if report['agent']['status'] not in ('ok','not_needed'):report['status']='degraded'
    dump(cache_path,scrub(cache));dump(agent_path,scrub(state));dump(root/'logs/title-resolver.json',scrub(report))
    if updated!=catalog and publish_changes:
        with redirect_stdout(io.StringIO()):publish(updated,version.get('checked_at'),'verified-title-resolver')
    export_map(root,updated,checked)
    return scrub(report)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--slug',action='append');p.add_argument('--limit',type=int,default=3);p.add_argument('--force',action='store_true');p.add_argument('--credentials');p.add_argument('--no-publish',action='store_true');args=p.parse_args()
    try:print(json.dumps(run(slugs=args.slug,limit=args.limit,force=args.force,credential_path=args.credentials,publish_changes=not args.no_publish),ensure_ascii=False,indent=2))
    except Exception as exc:print(json.dumps({'status':'aborted','error':type(exc).__name__}));raise SystemExit(1)
