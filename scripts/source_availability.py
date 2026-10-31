"""Public, identity-scoped source checks. No provider IDs, credentials or playback URLs."""
import argparse,copy,hashlib,json,re,time
from catalog import ROOT,load,publish
from title_lookup import read,dump

def reference(work):
    zh=work.get('zh')or{};kind=work['kind'];n=int(work.get('artworkSeasonNumber')or work.get('seasonNumber')or 1)
    current=next((s for s in work.get('seasons',[])if s.get('season')==n),{})
    if kind=='movie':year=zh.get('searchYear')or zh.get('_identityYear')or work.get('year')or str(work.get('releaseDate',''))[:4]
    else:year=work.get('artworkSeasonYear')or current.get('year')or (str(work.get('releaseDate',''))[:4]if work.get('seasonNumber')==n else '')or (zh.get('_identityYear')or work.get('year')if n==1 else '')
    return {'en':work['en'],'kind':kind,'season':0 if kind=='movie'else n,'year':str(year or '')}

def make_check(work,ref,best,now):
    return dict(schema=1,en=work['en'],kind=work['kind'],season=0 if work['kind']=='movie'else int(ref['season']),year=str(ref['year']),
                found=bool(best and best.get('routes',0)>0),routes=min(1000,int(best['routes']))if best else 0,checkedAt=int(now))

def applies(check,work):
    ref=reference(work)
    return isinstance(check,dict)and check.get('schema')==1 and all(check.get(k)==v for k,v in ref.items())and type(check.get('found'))is bool and type(check.get('routes'))is int and 0<=check['routes']<=1000 and check['found']==(check['routes']>0)and type(check.get('checkedAt'))is int and check['checkedAt']>0 and re.fullmatch(r'(19|20)\d{2}',ref['year'])is not None

def apply_cached(work,root=ROOT):
    from mainland_names import source_deferred
    ref=reference(work);current=next((s for s in work.get('seasons',[])if s.get('season')==ref['season']),{})
    if source_deferred(current or work):return work
    record=read(root/'data/cloud-source-cache.json',{'records':{}})['records'].get(work['slug'],{})
    check=record.get('check');zh=work.get('zh')or{}
    existing=zh.get('sourceCheck')or{}
    if zh.get('name_status')=='verified_title_sources'and applies(check,work)and existing.get('checkedAt',0)<=check['checkedAt']:zh['sourceCheck']=copy.deepcopy(check);work['zh']=zh
    return work

def run(root=ROOT,limit=3,probe=None,now=None,slugs=None):
    from mainland_names import public_sources,source_deferred,republish_home,base,SOURCE_QUERY_POLICY
    now=int(time.time()if now is None else now);deadline=time.monotonic()+180
    main=load(root/'docs/catalog.json');home=load(root/'docs/home/home.json');path=root/'data/cloud-source-cache.json'
    cache=read(path,{'schema':1,'records':{}});providers=read(root/'data/public-source-providers.json',[])
    works=main['entries']+[w for w in home['works']if not w.get('knownCatalog')]
    works.sort(key=lambda w:cache['records'].get(w['slug'],{}).get('checkedAt',0))
    report={'records':[],'changed':[],'checkedAt':now};seen=set()
    for work in works:
        slug=work['slug'];zh=work.get('zh')or{}
        if slug in seen or slugs and slug not in slugs:continue
        seen.add(slug);ref=reference(work);current=next((s for s in work.get('seasons',[])if s.get('season')==ref['season']),{})
        if source_deferred(current or work,now)or zh.get('name_status')!='verified_title_sources'or not re.fullmatch(r'(19|20)\d{2}',ref['year']):continue
        names=list(dict.fromkeys(base(n)for n in [zh['title']]+zh.get('aliases',[])if re.search(r'[\u3400-\u9fff]',n)))[:4]
        fingerprint=hashlib.sha256(json.dumps([SOURCE_QUERY_POLICY,ref,names],sort_keys=True,ensure_ascii=False).encode()).hexdigest();old=cache['records'].get(slug,{})
        inline=zh.get('sourceCheck')or{}
        if applies(inline,work)and (inline['found']or old.get('queryPolicy')==SOURCE_QUERY_POLICY)and now<inline['checkedAt']+(7*86400 if inline['found']else 86400)and inline['checkedAt']>=old.get('checkedAt',0):
            cache['records'][slug]={'checkedAt':inline['checkedAt'],'nextRetry':inline['checkedAt']+(7*86400 if inline['found']else 86400),'fingerprint':fingerprint,'queryPolicy':SOURCE_QUERY_POLICY,'check':copy.deepcopy(inline)}
            dump(path,cache);continue
        if old.get('fingerprint')==fingerprint and now<old.get('nextRetry',0)and applies(old.get('check'),work):
            if zh.get('sourceCheck')!=old['check']:zh['sourceCheck']=copy.deepcopy(old['check']);report['changed'].append(slug)
            continue
        if len(report['records'])>=max(0,min(10,int(limit)))or time.monotonic()>=deadline:continue
        query={'kind':ref['kind'],'year':ref['year'],'season':ref['season']or 1}
        best,events=probe(query,names,providers)if probe else public_sources(query,names,providers,deadline=deadline)
        check=make_check(work,query,best,now);zh['sourceCheck']=check;work['zh']=zh
        # Display name follows the strongest source, except animation keeps the verified Douban name.
        if best and not any(str(g).casefold()in ('animation','动画')for g in work.get('genres',[])):
            selected=base(best['title']);zh['aliases']=list(dict.fromkeys([selected,zh['title']]+zh.get('aliases',[])));zh['title']=selected
        cache['records'][slug]={'checkedAt':now,'nextRetry':now+(7*86400 if check['found']else 86400),'fingerprint':fingerprint,'queryPolicy':SOURCE_QUERY_POLICY,'check':check}
        report['records'].append({'slug':slug,'check':check,'events':events});report['changed'].append(slug);dump(path,cache)
    by_slug={e['slug']:e for e in main['entries']}
    for work in home['works']:
        if work.get('knownCatalog')and work['slug']in report['changed']and work['slug']in by_slug:work['zh']=copy.deepcopy(by_slug[work['slug']].get('zh'))
    if report['changed']:
        publish(main,load(root/'docs/version.json').get('checked_at'),'github-verified-source-availability');republish_home(home,root)
    dump(root/'logs/cloud-source-checks.json',report);return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=3);parser.add_argument('--slug',action='append');args=parser.parse_args()
    print(json.dumps(run(limit=args.limit,slugs=args.slug),ensure_ascii=False))
