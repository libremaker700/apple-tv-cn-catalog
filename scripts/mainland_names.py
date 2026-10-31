"""You.com first -> independent Douban/ikanbot identity -> bounded public source comparison.

Only verified page fields may become titles. Gemini is never called here.
"""
import argparse,copy,hashlib,json,re,time
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
    return sum(any(re.match(r'https?://',e.split('$',1)[-1].split('|',1)[0])for e in group.split('#'))for group in str(row.get('vod_play_url','')).split('$$$')[:20])
def season(title):
    found=re.search(r'第([0-9一二三四五六七八九十]+)季|season\s*(\d+)',title,re.I)
    if not found:return 1
    word=found[1]or found[2]
    if word.isdigit():return int(word)
    digits='零一二三四五六七八九';pos=word.find('十')
    return (1 if pos==0 else digits.index(word[0]))*10+(digits.index(word[-1])if pos<len(word)-1 else 0)if pos>=0 else digits.index(word)
def base(text):return re.sub(r'\s*第[0-9一二三四五六七八九十]+季\s*$','',text).strip()
def candidate_matches(ref,row,names):
    title=str(row.get('vod_name',''));kind=str(row.get('type_name',''));year=str(row.get('vod_year',''))
    if re.search(r'解说|预告|短剧|伦理',kind):return False
    if norm(base(title))not in {norm(base(n))for n in names}or year!=str(ref['year']):return False
    if ref['kind']=='series':return season(title)==ref['season']and not re.search(r'恐怖片|动作片|爱情片|剧情片|喜剧片',kind)
    return not re.search(r'电视剧|连续剧|综艺',kind)
def public_sources(ref,names,providers,session=None):
    client=session or requests.Session();best=None;observed=0;events=[];seen=set()
    for provider in providers:
        for name in names[:4]:
            try:
                response=client.get(provider['url'],params={'ac':'detail','wd':name},timeout=(5,9),allow_redirects=False)
                if response.status_code!=200:events.append({'provider':provider['id'],'http':response.status_code});break
                rows=response.json().get('list',[])
                for row in rows[:30]:
                    record=(provider['id'],str(row.get('vod_id','')))
                    if not candidate_matches(ref,row,names)or record in seen:continue
                    seen.add(record)
                    count=source_count(row)
                    if count and(best is None or count>best['routes']):best={'title':row['vod_name'],'routes':count,'provider':provider['id']}
                    observed+=count
                if observed>=10:return best,events
            except (requests.RequestException,ValueError,TypeError):events.append({'provider':provider['id'],'http':0});break
        if best:break  # One useful provider is enough for scheduled background name calibration.
    return best,events

def independent_name(ref,hits,lookup,now,http=None):
    for item in hits[:6]:
        part=urlsplit(item['url']);sid=re.fullmatch(r'/(?:movie/)?subject/(\d+)/?',part.path)
        if part.hostname in ('movie.douban.com','m.douban.com')and sid:
            patch=DoubanMobile(lookup.pages).subject(ref,sid[1],str(now))
            if patch:return patch
        if part.hostname in ('www2.ikanbot.com','www.ikanbot.com')and re.fullmatch(r'/play/\d+',part.path) and not getattr(lookup,'ikanbot_blocked',False):
            # A blocked site is left pending. Never solve or bypass its access challenge.
            try:
                response=(http or requests).get(item['url'],timeout=(5,12),allow_redirects=False)
                if response.status_code!=200:
                    if response.status_code in (401,403,429):lookup.ikanbot_blocked=True
                    continue
                raw=response.text;head=re.search(r'(?is)<h1[^>]*>(.*?)</h1>',raw);parts=[plain_html(v)for v in re.findall(r'(?is)<h3[^>]*>(.*?)</h3>',raw)]
                if not head or len(parts)<2:continue
                aliases=[s.strip()for s in re.split(r'[,，/]',parts[0])]
                if norm(ref['english_title'])not in {norm(s)for s in aliases}or str(ref['year'])not in parts[1]:continue
                expected='Movie'if ref['kind']=='movie'else'TVSeries'
                if not re.search(r'@type[\"\s:]+ '+expected,raw,re.I) and not re.search(r'@type[\"\s:]+'+expected,raw,re.I):continue
                title=plain_html(head[1]);
                if chinese(title):return {'metadataPolicy':'mainland-v1','display_name_zh':title,'aliases_zh':[title],'name_status':'verified_title_sources','sources':[{'type':'ikanbot_identity_fields','url':item['url']}],'name_checked_at':str(now)}
            except requests.RequestException:continue
    return None

def republish_home(home,root):
    from home_sync import validate
    validate(home);folder=root/'docs/home';manifest=load(folder/'version.json');blob=raw_json(home);sha=hashlib.sha256(blob).hexdigest();path='releases/'+sha+'/home.json'
    (folder/path).parent.mkdir(parents=True,exist_ok=True);(folder/path).write_bytes(blob);(folder/'home.json').write_bytes(blob)
    manifest.update(version=sha,path=path,checkedAt=int(time.time()));(folder/'version.json').write_bytes(raw_json(manifest))

def run(root=ROOT,limit=3,force=False,client=None,lookup=None,probe=None,slugs=None):
    main=load(root/'docs/catalog.json');home=load(root/'docs/home/home.json');cache_path=root/'data/mainland-name-cache.json';cache=read(cache_path,{'records':{},'budgets':{}});now=int(time.time());month=time.strftime('%Y-%m',time.gmtime(now));budget=200
    report={'order':['you.com','douban_or_ikanbot_identity','public_source_match'],'records':[],'changed':[],'geminiUsed':False};used=int(cache['budgets'].get(month,0))
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
    selected.sort(key=lambda pair:(chinese((pair[0].get('zh')or{}).get('title','')),cache['records'].get(pair[0]['slug'],{}).get('checkedAt',0),pair[0]['en']))
    for work,is_home in selected:
        key=work['slug'];zh=work.get('zh')or{};old=cache['records'].get(key,{})
        if slugs and key not in slugs:continue
        if key in seen:continue
        seen.add(key)
        release_work=release_by_slug.get(key,work);deferred_now=source_deferred(release_work,now)
        released_after_name_only=old.get('result',{}).get('sourcePolicy')=='deferred_until_release'and not deferred_now
        if zh.get('name_status')=='verified_title_sources'and not force and not released_after_name_only:continue
        if now<old.get('nextRetry',0)and not force and not released_after_name_only:continue
        year=str(zh.get('_identityYear')or(work.get('year')if is_home else identity(work,{})['year'])or'')
        if not re.fullmatch(r'(19|20)\d{2}',year):continue
        if len(report['records'])>=max(0,min(5,int(limit))):break
        ref={'english_title':work['en'],'kind':'movie'if work['kind']=='movie'else'tv','year':year,'want_summary':False}
        if released_after_name_only and zh.get('name_sources'):
            status='cached_verified_name';patch={'display_name_zh':zh.get('douban_title')or zh['title'],'aliases_zh':zh.get('aliases',[]),'sources':zh['name_sources']}
        else:
            hits,status=client.search('"'+work['en']+'" '+year+' 中国大陆 中文片名 豆瓣')
            patch=independent_name(ref,hits,lookup,now)
        record={'slug':key,'en':work['en'],'searchStatus':status,'confidence':'UNVERIFIED'}
        if patch:
            names=list(dict.fromkeys([patch['display_name_zh']]+patch.get('aliases_zh',[])));n=int(work.get('artworkSeasonNumber')or work.get('seasonNumber')or 1);rows=work.get('seasons',[]);current=next((s for s in rows if s.get('season')==n),{})
            source_ref={'year':str(current.get('year')or year),'season':n,'kind':work['kind']}
            deferred=source_deferred(release_by_slug.get(key,work),now)
            best,events=(None,[])if deferred else(probe or public_sources)(source_ref,names,providers)
            record['sourcePolicy']='deferred_until_release'if deferred else'eligible'
            animated=any(str(g).casefold()in ('animation','动画')for g in work.get('genres',[]))
            title=patch['display_name_zh']if animated or not best else base(best['title'])
            zh.update(title=title,aliases=list(dict.fromkeys([title]+names+zh.get('aliases',[]))),metadataPolicy='mainland-v1',name_status='verified_title_sources',name_sources=patch['sources'],_identityYear=int(year),douban_title=patch['display_name_zh']if any('douban'in s['url']for s in patch['sources'])else zh.get('douban_title',''))
            work['zh']=zh;record.update(confidence='VERIFIED',title=title,sourceMatch=best,sourceEvents=events);report['changed'].append(key)
        cache['records'][key]={'checkedAt':now,'nextRetry':now+86400,'result':record};report['records'].append(record);dump(cache_path,cache)
    report['accounts']=client.events;report['reservedThisMonth']=used;dump(root/'logs/mainland-name-sync.json',report)
    if report['changed']:
        publish(main,load(root/'docs/version.json').get('checked_at'),'youcom-verified-mainland-names')
        published=load(root/'docs/catalog.json');by_slug={e['slug']:e for e in published['entries']}
        for work in home['works']:
            if work.get('knownCatalog')and work['slug']in report['changed']:work['zh']=copy.deepcopy(by_slug[work['slug']].get('zh'))
        republish_home(home,root)
    return report

if __name__=='__main__':
    args=argparse.ArgumentParser();args.add_argument('--limit',type=int,default=3);args.add_argument('--force',action='store_true');args.add_argument('--slug',action='append');a=args.parse_args();print(json.dumps(run(limit=a.limit,force=a.force,slugs=a.slug),ensure_ascii=False))
