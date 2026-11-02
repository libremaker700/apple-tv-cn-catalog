"""Direct Douban title -> bounded sources -> search-account fallback with page verification.

Only verified page fields may become titles. Gemini is never called here.
"""
import argparse,copy,hashlib,json,re,time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
import requests
from api_accounts import SearchAccounts
from catalog import ROOT,load,publish,raw_json
from title_lookup import read,dump,identity
from title_sources import Lookup,norm,chinese
from douban_mobile import DoubanMobile
from public_sources import plain_html

def source_deferred(work,now=None):
    # Official release metadata takes priority over stale source bindings.
    today=time.strftime('%Y-%m-%d',time.gmtime(time.time() if now is None else now))
    date=str(work.get('releaseDate')or'')
    if re.fullmatch(r'(19|20)\d{2}-\d{2}-\d{2}',date):return date>today
    return bool(work.get('upcoming')or work.get('metadataStatus')=='announced')

def source_count(row):
    from source_votes import usable_groups
    return usable_groups(row)
def verified_subject(info):
    value=str(info.get('douban_id')or'')
    if re.fullmatch(r'[1-9][0-9]{4,9}',value):return value
    for source in info.get('sources',info.get('name_sources',[])):
        match=re.search(r'^https://(?:movie|m)\.douban\.com/(?:movie/)?subject/(\d+)',source.get('url',''))
        if match:return match[1]
    return None
def season(title):
    found=re.search(r'第([0-9一二三四五六七八九十百]+)季|season\s*(\d+)',title,re.I)
    if not found:return 1
    word=found[1]or found[2]
    if word.isdigit():return int(word)
    if word=='一百':return 100
    digits='零一二三四五六七八九';pos=word.find('十')
    return (1 if pos==0 else digits.index(word[0]))*10+(digits.index(word[-1])if pos<len(word)-1 else 0)if pos>=0 else digits.index(word)
def base(text):return re.sub(r'\s*(?:第[0-9一二三四五六七八九十百]+季|season\s*\d+)\s*$','',text,flags=re.I).strip()

SOURCE_QUERY_POLICY='verified-alias-punctuation-scoped-season-v7'

def source_people(ref,patch):
    if patch.get('sourceSeason'):ref['sourceSeason']=copy.deepcopy(patch['sourceSeason'])
    for key in ('directors','actors'):
        value=patch.get(key)or[]
        if isinstance(value,list):value=','.join(str(person)for person in value if isinstance(person,str))
        if isinstance(value,str)and value:ref[key]=value
    return ref
def source_queries(ref,names):
    """Try the selected season explicitly before the unsuffixed title, per verified alias."""
    try:number=int(ref.get('season',1))
    except (TypeError,ValueError):number=0
    output=[];seen=set()
    for name in names[:4]:
        if not isinstance(name,str)or not name.strip():continue
        variants=[name.strip()]
        if ref.get('kind')=='movie':
            short=re.sub(r'[哦啊呀啦吧]+$','',re.split(r'[！!，,:：]',name,1)[0]).strip()
            if 4<=len(short)<=24 and norm(short)!=norm(name):variants.append(short)
        if ref.get('kind')=='series'and 1<=number<=100:
            root=base(name);digits='零一二三四五六七八九'
            chinese=digits[number]if number<10 else ('一百'if number==100 else ('十'if number<20 else digits[number//10]+'十')+(digits[number%10]if number%10 else ''))
            variants=[root+'第'+chinese+'季',root+'第'+str(number)+'季',root]if re.search(r'[\u3400-\u9fff]',root)else[root+' Season '+str(number),root]
        for query in variants:
            key=re.sub(r'\s+',' ',query).casefold()
            if key not in seen:output.append(query);seen.add(key)
    # Matching after a response cannot help a punctuation-sensitive upstream
    # that returns no rows. Preserve exact queries first, then bounded stripped
    # variants; do not use norm() for dedupe here or it would discard them.
    expanded=[];seen=set()
    for query in output:
        stripped=re.sub(r'[^a-zA-Z0-9\u3400-\u9fff]','',query)
        for variant in (query,stripped):
            if variant and variant.casefold()not in seen:
                expanded.append(variant);seen.add(variant.casefold())
    return expanded[:12]
def matched_season(ref,title):
    if re.search(r'第\s*[0-9一二三四五六七八九十百]+\s*季|season\s*\d+',title,re.I):return season(title)
    scope=ref.get('sourceSeason')or{}
    if scope.get('policy')=='verified-subseries-v1'and scope.get('season')==ref.get('season')and str(scope.get('year'))==str(ref.get('year'))and scope.get('subjectId')==str(ref.get('douban_id')or'')and norm(title)in {norm(t)for t in scope.get('titles',[])if isinstance(t,str)}:
        return scope['season']
    return season(title)

def recall_matches(ref,row,names,strong=False):
    """Recall an existing verified alias; this alone never authorizes renaming."""
    title=str(row.get('vod_name',''));kind=str(row.get('type_name',''));year=str(row.get('vod_year',''))
    if not kind or re.search(r'解说|预告|花絮|短剧|伦理',kind+' '+title):return False
    expected=str(ref.get('douban_id')or'');actual=str(row.get('vod_douban_id')or'');valid=lambda s:bool(re.fullmatch(r'[1-9][0-9]{4,9}',s))
    if valid(expected)and valid(actual)and expected!=actual:return False
    same_id=valid(expected)and expected==actual
    from source_votes import canonical_name
    year_matches=year==str(ref['year'])or ref['kind']=='movie'and same_id and re.fullmatch(r'(19|20)\d{2}',year)and re.fullmatch(r'(19|20)\d{2}',str(ref['year']))and abs(int(year)-int(ref['year']))<=1
    # A year suffix or an unknown alias needs stronger identity evidence.
    compared=canonical_name(ref,title,names,base,norm)if strong else title
    if (norm(base(compared))not in {norm(base(n))for n in names}and not same_id)or not year_matches:return False
    if ref['kind']=='series':return matched_season(ref,title)==ref['season']and bool(re.search(r'剧|劇|动漫|动画|综艺|纪录片|紀錄片',kind))and not re.search(r'电影|電影|剧情片|喜剧片|动作片|恐怖片',kind)
    return (bool(re.search(r'电影|電影|片',kind))or same_id and bool(re.search(r'动漫|动画',kind))and not re.search(r'第.+季|season\s*\d+',title,re.I))and not re.search(r'电视剧|连续剧|欧美剧|剧集|日剧|韩剧|综艺',kind)
def candidate_matches(ref,row,names):
    expected=str(ref.get('douban_id')or'');actual=str(row.get('vod_douban_id')or'')
    same_id=bool(re.fullmatch(r'[1-9][0-9]{4,9}',expected))and expected==actual
    people=lambda text:{norm(n)for n in re.split(r'[,，/、;；|]+',str(text or''))if norm(n)and norm(n)not in ('未知','不详','内详','unknown')}
    if not same_id and(not(people(ref.get('directors'))&people(row.get('vod_director')))or len(people(ref.get('actors'))&people(row.get('vod_actor')))<2):return False
    return recall_matches(ref,row,names,strong=True)
def public_sources(ref,names,providers,session=None,deadline=None):
    from source_votes import collect
    return collect(ref,names,providers,session,time.monotonic()+90 if deadline is None else deadline,candidate_matches,source_queries,base,norm,recall=recall_matches)

def independent_name(ref,hits,lookup,now,http=None):
    for item in hits[:6]:
        part=urlsplit(item['url']);sid=re.fullmatch(r'/(?:movie/)?subject/(\d+)/?',part.path)
        if part.hostname in ('movie.douban.com','m.douban.com')and sid:
            patch=DoubanMobile(lookup.pages).subject(ref,sid[1],str(now))
            if patch:return patch
    from plex_names import PlexNames
    return PlexNames(getattr(lookup,'pages',None)).lookup(ref,str(now),hits)


def republish_home(home,root):
    from home_sync import validate
    from detail_metadata import apply_cached
    home=apply_cached(home,root,home=True)
    from source_availability import apply_cached as apply_sources
    for work in home.get('works',[]):apply_sources(work,root)
    validate(home);folder=root/'docs/home';manifest=load(folder/'version.json');blob=raw_json(home);sha=hashlib.sha256(blob).hexdigest();path='releases/'+sha+'/home.json'
    (folder/path).parent.mkdir(parents=True,exist_ok=True);(folder/path).write_bytes(blob);(folder/'home.json').write_bytes(blob)
    manifest.update(version=sha,path=path,checkedAt=int(time.time()));(folder/'version.json').write_bytes(raw_json(manifest))

def run(root=ROOT,limit=3,force=False,client=None,lookup=None,probe=None,slugs=None,names_only=False):
    main=load(root/'docs/catalog.json');home=load(root/'docs/home/home.json');cache_path=root/'data/mainland-name-cache.json';cache=read(cache_path,{'records':{},'budgets':{}});now=int(time.time());month=time.strftime('%Y-%m',time.gmtime(now));budget=200
    report={'order':['douban_direct','verified_search_fallback']if names_only else['douban_direct','public_source_match','you.com_fallback','douban_or_plex_identity','public_source_match'],'records':[],'changed':[],'geminiUsed':False,'namesOnly':names_only};used=int(cache['budgets'].get(month,0))
    search_hints_by_slug=read(root/'data/name-search-hints.json',{'works':{}}).get('works',{})
    def reserve():
        nonlocal used
        if used>=budget:return False
        used+=1;cache['budgets'][month]=used;dump(cache_path,cache);return True
    client=client or SearchAccounts(reserve=reserve);lookup=lookup or Lookup(cache_path=root/'data/source-cache.json');providers=read(root/'data/public-source-providers.json',[])
    selected=[];seen=set();release_by_slug={e['slug']:e for e in main['entries']}
    for work in home['works']:
        if work.get('knownCatalog'):continue
        selected.append((work,True))
    selected+=[(e,False)for e in main['entries']]
    def priority(pair):
        work=pair[0];n=int(work.get('artworkSeasonNumber')or work.get('seasonNumber')or 1)
        current=next((s for s in work.get('seasons',[])if s.get('season')==n),{})
        return (source_deferred(current or work,now),cache['records'].get(work['slug'],{}).get('checkedAt',0),work['en'])
    selected.sort(key=priority)
    for work,is_home in selected:
        key=work['slug'];zh=work.get('zh')or{};old=cache['records'].get(key,{})
        if slugs and key not in slugs:continue
        if key in seen:continue
        seen.add(key)
        release_work=release_by_slug.get(key,work)
        n=int(work.get('artworkSeasonNumber')or work.get('seasonNumber')or 1)
        current=next((s for s in work.get('seasons',[])if s.get('season')==n),{})
        deferred_now=source_deferred(current or release_work,now)
        released_after_name_only=old.get('result',{}).get('sourcePolicy')=='deferred_until_release'and not deferred_now
        from detail_metadata import valid as valid_detail
        has_detail=any(valid_detail(p,work['kind'])and p['season']==(0 if work['kind']=='movie'else n)and p['summaryStatus']=='AVAILABLE'and 0<=now-datetime.fromisoformat(p['checkedAt']).timestamp()<7*86400 for p in zh.get('detailSeasons',[]))
        if zh.get('name_status')=='verified_title_sources'and has_detail and not force and not released_after_name_only:continue
        if now<old.get('nextRetry',0)and not force and not released_after_name_only:continue
        year=str(zh.get('_identityYear')or(work.get('year')if is_home else identity(work,{})['year'])or'')
        if not re.fullmatch(r'(19|20)\d{2}',year):continue
        if len(report['records'])>=max(0,min(5,int(limit))):break
        detail_year=str(current.get('year')or year)
        ref={'english_title':work['en'],'kind':'movie'if work['kind']=='movie'else'tv','year':detail_year,'season':0 if work['kind']=='movie'else n,'want_summary':True,'display_name_zh':zh.get('title','')}
        watch=work.get('watchUrl')or(work.get('officialIdentity')or{}).get('watchUrl','')
        if work['kind']=='movie'and watch.startswith('https://tv.apple.com/us/movie/'):
            ref.update(release_date=work.get('releaseDate',''),release_region='US')
        hint=search_hints_by_slug.get(key,{})
        if hint.get('englishTitle')==work['en']:
            if not ref['display_name_zh']:ref['display_name_zh']=hint.get('chineseHint','')
            if re.fullmatch(r'tt\d{7,10}',hint.get('imdbId','')):ref['imdb_id']=hint['imdbId']
            official=work.get('officialId')or(work.get('officialIdentity')or{}).get('watchUrl','').rstrip('/').split('/')[-1]
            if official==hint.get('officialId'):
                ref['candidate_subject_ids']=[str(s)for s in hint.get('candidateSubjectIds',[])if re.fullmatch(r'\d{1,12}',str(s))][:3]
                ref['candidate_original_titles']=[str(t)for t in hint.get('candidateOriginalTitles',[])if isinstance(t,str)and len(t)<=200][:3]
            if work['kind']=='movie'and official==hint.get('officialId')and ref['year']==hint.get('expectedPlatformYear')and ref.get('release_date')==(hint.get('releaseDateEvidence')or{}).get('officialReleaseDate'):
                ref['release_date_evidence']=copy.deepcopy(hint.get('releaseDateEvidence')or{})
            allowed=work['kind']=='movie'and hint.get('policy')=='verified_original_movie_year_not_platform_date'or work['kind']=='series'and n==1 and hint.get('policy')=='verified_original_series_year_not_platform_date'
            if allowed and official==hint.get('officialId')and ref['year']==hint.get('expectedPlatformYear')and re.fullmatch(r'(19|20)\d{2}',hint.get('releaseYear',''))and re.fullmatch(r'https://www\.imdb\.com/title/tt\d{7,10}/',hint.get('releaseYearEvidence','')):
                ref['year']=hint['releaseYear']
        source_ref=source_people({'year':ref['year'],'season':n,'kind':work['kind']},zh)
        if verified_subject(zh):source_ref['douban_id']=verified_subject(zh)
        deferred=deferred_now;best=None;events=[];probed=False;probed_names=set();discovery=dict(old.get('discovery')or{});identity_record=old.get('identity');discovery_events=[];hits=[]
        if released_after_name_only and zh.get('name_sources'):
            status='cached_verified_name';patch={'display_name_zh':zh.get('douban_title')or zh['title'],'aliases_zh':zh.get('aliases',[]),'sources':zh['name_sources']}
        else:
            mobile=DoubanMobile(lookup.pages);subject=verified_subject(zh)
            patch=mobile.subject(ref,subject,str(now))if subject else None
            if not patch:patch=mobile.lookup(ref,str(now))
            identities=list(mobile.identities.values())if isinstance(mobile.identities,dict)else[]
            if len(identities)==1:identity_record=identities[0]
            elif len(identities)>1:identity_record=None
            elif names_only:identity_record=None
            status='douban_direct'
            if patch and not deferred and not names_only:
                source_people(source_ref,patch)
                if verified_subject(patch):source_ref['douban_id']=verified_subject(patch)
                direct_names=list(dict.fromkeys([patch['display_name_zh']]+patch.get('aliases_zh',[])))
                best,events=(probe or public_sources)(source_ref,direct_names,providers);probed=True;probed_names.update(direct_names)
            if not patch or not deferred and not best and not names_only:
                hits,fallback_status=client.search('"'+work['en']+'" '+detail_year+' '+ref.get('display_name_zh','')+' 中国大陆 中文片名 豆瓣')
                fallback=independent_name(ref,hits,lookup,now)
                status='douban_direct_then_'+fallback_status if patch else fallback_status
                if fallback:
                    if patch:
                        fallback['aliases_zh']=list(dict.fromkeys([patch['display_name_zh']]+patch.get('aliases_zh',[])+[fallback['display_name_zh']]+fallback.get('aliases_zh',[])))
                        fallback['sources']=patch['sources']+fallback.get('sources',[])
                        fallback['display_name_zh']=patch['display_name_zh']
                        # Keep the single Douban response's synopsis and rating packet intact.
                        for field in ('detailMetadata','douban_id','douban_url','rating_status','douban_rating','rating_checked_at','summary_zh','summary_sources','summary_checked_at','actors','directors'):
                            if field in patch:fallback[field]=copy.deepcopy(patch[field])
                    patch=fallback;probed=False
            if not names_only and (not patch or not best)and not deferred and identity_record and str(identity_record.get('year'))==detail_year and identity_record.get('season')==ref['season']:
                from alias_discovery import discover,search_hints
                if discovery.get('_hintPolicy')!='ydc-tavily-v1':discovery.pop('_hints',None)
                discovery['_hintPolicy']='ydc-tavily-v1'
                hints=(patch.get('aliases_zh',[])+[patch['display_name_zh']]if patch else zh.get('aliases',[])+([zh['title']]if zh.get('title')else[]))or discovery.get('_hints',[])
                if not hints:hints=search_hints(hits)
                if not hints:
                    extra_hits,extra_status=client.search('"'+work['en']+'" '+detail_year+' 动画 电视剧 中文名 别名')
                    hints=search_hints(extra_hits);discovery_events.append({'service':'ydc_tavily','stage':'candidate_names','status':extra_status})
                discovery['_hints']=hints
                alias_patch,extra=discover(identity_record,ref,providers,hints,state=discovery);discovery_events+=extra
                if alias_patch:
                    if patch:patch['aliases_zh']=list(dict.fromkeys(patch.get('aliases_zh',[])+alias_patch['aliases_zh']))
                    else:patch=alias_patch
                    status='automatic_identity_alias';probed=False
        record={'slug':key,'en':work['en'],'searchStatus':status,'confidence':'UNVERIFIED'}
        if discovery_events:record['discoveryEvents']=discovery_events
        if patch:
            source_people(source_ref,patch)
            if work['kind']=='movie'and patch.get('release_date_evidence')and patch.get('release_year'):source_ref['year']=str(patch['release_year'])
            if verified_subject(patch):source_ref['douban_id']=verified_subject(patch)
            names=list(dict.fromkeys([patch['display_name_zh']]+patch.get('aliases_zh',[])))
            if not deferred and not probed and not names_only:
                remaining=[name for name in names if name not in probed_names]
                if remaining:
                    best,new_events=(probe or public_sources)(source_ref,remaining,providers);events+=new_events
            record['sourcePolicy']='not_checked_name_review'if names_only else'deferred_until_release'if deferred else'eligible'
            title=patch['display_name_zh']if not best else base(best['title'])
            zh.update(title=title,aliases=list(dict.fromkeys([title]+names+zh.get('aliases',[]))),metadataPolicy='mainland-v1',name_status='verified_title_sources',name_sources=patch['sources'],_identityYear=int(year),douban_title=patch['display_name_zh']if any(s.get('type')=='douban_mobile_identity'for s in patch['sources'])else zh.get('douban_title',''))
            if verified_subject(patch):zh['douban_id']=verified_subject(patch)
            if patch.get('release_date_evidence'):zh['releaseDateEvidence']=copy.deepcopy(patch['release_date_evidence'])
            for person_field in ('actors','directors'):
                if patch.get(person_field):zh[person_field]=copy.deepcopy(patch[person_field])
            zh.pop('douban_rating_count',None)
            packet=patch.get('detailMetadata')
            if packet:
                from detail_metadata import remember
                work['zh']=zh
                if remember(work,packet,root):record['detailMetadata']={'season':packet['season'],'subjectId':packet['subjectId'],'summaryStatus':packet['summaryStatus'],'ratingStatus':packet['ratingStatus']}
            from source_votes import incomplete
            if not names_only and not deferred and (best or probed and not incomplete(events)):
                from source_availability import make_check
                zh['sourceCheck']=make_check(work,source_ref,best,now)
                if best and best.get('selection'):zh['nameSelection']=copy.deepcopy(best['selection'])
            work['zh']=zh;record.update(confidence='VERIFIED',title=title,sourceMatch=best,sourceEvents=events);report['changed'].append(key)
            if ref['year']!=detail_year:
                zh['searchYear']=int(ref['year']);record['originalReleaseYear']=int(ref['year'])
                if work['kind']=='series':zh['searchSeason']=n
            if work['kind']=='movie'and patch.get('release_date_evidence')and patch.get('release_year'):
                zh['searchYear']=int(patch['release_year']);record['originalReleaseYear']=int(patch['release_year']);record['releaseDateEvidence']=copy.deepcopy(patch['release_date_evidence'])
        if not patch:
            if identity_record:record['identityVerifiedWithoutChineseName']=True;record['verifiedIdentity']=copy.deepcopy(identity_record)
            pages=getattr(lookup,'pages',None)
            record['verificationEvents']=getattr(pages,'events',[])[-12:]if pages is not None else[]
            diagnostics=getattr(mobile,'diagnostics',[])
            record['subjectDiagnostics']=diagnostics if isinstance(diagnostics,list)else[]
        cache['records'][key]={'checkedAt':now,'nextRetry':now+86400,'result':record,'identity':identity_record,'discovery':discovery};report['records'].append(record);dump(cache_path,cache)
    report['accounts']=client.events;report['reservedThisMonth']=used;dump(root/'logs/mainland-name-sync.json',report)
    if report['changed']:
        publish(main,load(root/'docs/version.json').get('checked_at'),'douban-first-verified-mainland-names')
        published=load(root/'docs/catalog.json');by_slug={e['slug']:e for e in published['entries']}
        for work in home['works']:
            if work.get('knownCatalog')and work['slug']in report['changed']:work['zh']=copy.deepcopy(by_slug[work['slug']].get('zh'))
        from home_titles import remember as remember_home_titles
        remember_home_titles(home,root)
        republish_home(home,root)
    return report

if __name__=='__main__':
    args=argparse.ArgumentParser();args.add_argument('--limit',type=int,default=3);args.add_argument('--force',action='store_true');args.add_argument('--slug',action='append');a=args.parse_args();print(json.dumps(run(limit=a.limit,force=a.force,slugs=a.slug),ensure_ascii=False))
