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

def retry_interval(check,selection):
    selection=selection or{}
    return 3600 if check['found']and selection.get('complete')is False else 7*86400 if check['found']else 86400

def verified_name(zh):
    # The reviewed baseline is also an accepted App title authority.
    return zh.get('metadataPolicy')=='mainland-v1'and bool(re.search(r'[\u3400-\u9fff]',str(zh.get('title',''))))and(zh.get('name_status')=='verified_title_sources'or zh.get('provenance')=='reviewed_mainland_catalog')

def sync_home_zh(home_work,main_work):
    incoming=main_work.get('zh')or{};zh=home_work.setdefault('zh',{})
    for key in ('sourceCheck','nameSelection','detailMetadata','detailSeasons'):
        if key in incoming:zh[key]=copy.deepcopy(incoming[key])
        else:zh.pop(key,None)
    # Homepage-only names require independent evidence; a reviewed main-catalog
    # label alone must not acquire fictitious name_sources or overwrite hero copy.
    if incoming.get('name_status')=='verified_title_sources'and incoming.get('name_sources'):
        for key in ('title','aliases','name_status','name_sources','provenance'):
            if key in incoming:zh[key]=copy.deepcopy(incoming[key])
    return home_work

def apply_cached(work,root=ROOT):
    from mainland_names import source_deferred
    ref=reference(work);current=next((s for s in work.get('seasons',[])if s.get('season')==ref['season']),{})
    if source_deferred(current or work):return work
    record=read(root/'data/cloud-source-cache.json',{'records':{}})['records'].get(work['slug'],{})
    check=record.get('check');zh=work.get('zh')or{}
    existing=zh.get('sourceCheck')or{}
    from mainland_names import SOURCE_QUERY_POLICY
    providers=read(root/'data/public-source-providers.json',[])
    scope=hashlib.sha256(json.dumps(providers,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if record.get('queryPolicy')!=SOURCE_QUERY_POLICY or record.get('scopeHash')!=scope:
        if existing.get('found')is False:zh.pop('sourceCheck',None)
        if isinstance(zh.get('nameSelection'),dict):zh['nameSelection']['complete']=False
        work['zh']=zh
        return work
    if verified_name(zh)and applies(check,work)and existing.get('checkedAt',0)<=check['checkedAt']:
        zh['sourceCheck']=copy.deepcopy(check);work['zh']=zh
        from source_votes import apply_selection
        apply_selection(work,copy.deepcopy(record.get('selection')))
    return work

def run(root=ROOT,limit=12,probe=None,now=None,slugs=None,force=False):
    from mainland_names import public_sources,source_deferred,republish_home,base,SOURCE_QUERY_POLICY,source_people
    from source_votes import incomplete
    now=int(time.time()if now is None else now);deadline=time.monotonic()+1200
    main=load(root/'docs/catalog.json');home=load(root/'docs/home/home.json');path=root/'data/cloud-source-cache.json'
    cache=read(path,{'schema':1,'records':{}});providers=read(root/'data/public-source-providers.json',[])
    works=main['entries']+[w for w in home['works']if not w.get('knownCatalog')]
    works.sort(key=lambda w:cache['records'].get(w['slug'],{}).get('lastAttemptAt',cache['records'].get(w['slug'],{}).get('checkedAt',0)))
    scope=hashlib.sha256(json.dumps(providers,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    report={'records':[],'changed':[],'checkedAt':now,'requestedLibraries':len(providers),'scopeHash':scope,'eligible':0,'cached':0};seen=set()
    for work in works:
        slug=work['slug'];zh=work.get('zh')or{}
        if slug in seen or slugs and slug not in slugs:continue
        seen.add(slug);ref=reference(work);current=next((s for s in work.get('seasons',[])if s.get('season')==ref['season']),{})
        if source_deferred(current or work,now)or not verified_name(zh)or not re.fullmatch(r'(19|20)\d{2}',ref['year']):continue
        report['eligible']+=1
        names=list(dict.fromkeys(base(n)for n in [zh['title']]+zh.get('aliases',[])if re.search(r'[\u3400-\u9fff]',n)))[:4]
        fingerprint=hashlib.sha256(json.dumps([SOURCE_QUERY_POLICY,scope,ref,names,zh.get('actors'),zh.get('directors')],sort_keys=True,ensure_ascii=False).encode()).hexdigest();old=cache['records'].get(slug,{})
        inline=zh.get('sourceCheck')or{}
        selection=zh.get('nameSelection')or old.get('selection')or{}
        policy_ready=old.get('queryPolicy')==SOURCE_QUERY_POLICY and old.get('scopeHash')==scope
        if not force and old.get('pending')and old.get('fingerprint')==fingerprint and now<old.get('nextRetry',0):report['cached']+=1;continue
        if not force and applies(inline,work)and policy_ready and now<inline['checkedAt']+retry_interval(inline,selection)and inline['checkedAt']>=old.get('checkedAt',0):
            cache['records'][slug]={'checkedAt':inline['checkedAt'],'nextRetry':inline['checkedAt']+retry_interval(inline,selection),'fingerprint':fingerprint,'queryPolicy':SOURCE_QUERY_POLICY,'scopeHash':scope,'check':copy.deepcopy(inline),'selection':selection or None};report['cached']+=1
            dump(path,cache);continue
        if not force and old.get('fingerprint')==fingerprint and now<old.get('nextRetry',0)and applies(old.get('check'),work):
            report['cached']+=1
            if zh.get('sourceCheck')!=old['check']:zh['sourceCheck']=copy.deepcopy(old['check']);report['changed'].append(slug)
            continue
        if len(report['records'])>=max(0,min(24,int(limit)))or time.monotonic()>=deadline:continue
        query=source_people({'kind':ref['kind'],'year':ref['year'],'season':ref['season']or 1},zh)
        subject=zh.get('douban_id')or next((re.search(r'/subject/(\d+)',s.get('url',''))[1]for s in zh.get('name_sources',[])if re.search(r'/subject/(\d+)',s.get('url',''))),None)
        from detail_metadata import valid as valid_detail
        packet=next((p for p in zh.get('detailSeasons',[])+[zh.get('detailMetadata')]if valid_detail(p,work['kind'])and p['season']==ref['season']and str(p['year'])==ref['year']),None)
        if packet:subject=packet['subjectId']
        if subject:query['douban_id']=str(subject)
        if not probe and subject and(not query.get('actors')or not query.get('directors')):
            from title_sources import Lookup
            from douban_mobile import DoubanMobile
            lookup=Lookup(cache_path=root/'data/source-cache.json')
            patch=DoubanMobile(lookup.pages).subject({'english_title':work['en'],'kind':'movie'if work['kind']=='movie'else'tv','season':ref['season'],'year':ref['year'],'want_summary':True},str(subject),str(now))
            if patch:
                for key in ('actors','directors'):
                    if patch.get(key):zh[key]=copy.deepcopy(patch[key])
                source_people(query,patch)
                if patch.get('detailMetadata'):
                    from detail_metadata import remember
                    remember(work,patch['detailMetadata'],root)
                report['changed'].append(slug)
        best,events=probe(query,names,providers)if probe else public_sources(query,names,providers,deadline=min(deadline,time.monotonic()+90))
        if not best and incomplete(events):
            pending=dict(old,lastAttemptAt=now,nextRetry=now+3600,fingerprint=fingerprint,queryPolicy=SOURCE_QUERY_POLICY,scopeHash=scope,pending=True)
            # A previous smaller scope cannot supply a negative result for this scope.
            if not policy_ready:
                if not (pending.get('check')or{}).get('found'):pending.pop('check',None)
                if (zh.get('sourceCheck')or{}).get('found')is False:zh.pop('sourceCheck',None);report['changed'].append(slug)
                if isinstance(zh.get('nameSelection'),dict):zh['nameSelection']['complete']=False
            cache['records'][slug]=pending;dump(path,cache)
            report['records'].append({'slug':slug,'status':'incomplete','events':events});continue
        check=make_check(work,query,best,now);zh['sourceCheck']=check;work['zh']=zh
        if best:
            selected=base(best['title']);zh['aliases']=list(dict.fromkeys([selected,zh['title']]+zh.get('aliases',[])));zh['title']=selected
            if subject:
                zh['name_status']='verified_title_sources'
                if not zh.get('name_sources'):zh['name_sources']=[{'type':'douban_mobile_identity','url':'https://movie.douban.com/subject/'+str(subject)+'/','retrieved_at':str(now)}]
            if best.get('selection'):zh['nameSelection']=copy.deepcopy(best['selection'])
        cache['records'][slug]={'checkedAt':now,'lastAttemptAt':now,'nextRetry':now+retry_interval(check,(best or{}).get('selection')or{}),'fingerprint':fingerprint,'queryPolicy':SOURCE_QUERY_POLICY,'scopeHash':scope,'check':check,'selection':copy.deepcopy(best.get('selection'))if best else None}
        report['records'].append({'slug':slug,'check':check,'events':events});report['changed'].append(slug);dump(path,cache)
    by_slug={e['slug']:e for e in main['entries']}
    for work in home['works']:
        if work.get('knownCatalog')and work['slug']in report['changed']and work['slug']in by_slug:sync_home_zh(work,by_slug[work['slug']])
    if report['changed']:
        publish(main,load(root/'docs/version.json').get('checked_at'),'github-verified-source-availability');republish_home(home,root)
    report['changed']=list(dict.fromkeys(report['changed']))
    report['remainingDue']=max(0,report['eligible']-report['cached']-len(report['records']))
    dump(root/'logs/cloud-source-checks.json',report);return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=12);parser.add_argument('--slug',action='append');parser.add_argument('--force',action='store_true');args=parser.parse_args()
    print(json.dumps(run(limit=args.limit,slugs=args.slug,force=args.force),ensure_ascii=False))
