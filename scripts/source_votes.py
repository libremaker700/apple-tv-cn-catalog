"""Count identity-checked direct-media libraries per title, never lines per library."""
import re,time
from concurrent.futures import ThreadPoolExecutor,as_completed,TimeoutError
from urllib.parse import urlsplit
import requests

VOTE_POLICY='library-votes-v1'
WEB_FLAGS={'ruyi','jjzy','ukyun','hnyun','gsyun','subyun'}

def usable_groups(row):
    flags=str(row.get('vod_play_from','')).split('$$$');count=0
    for index,group in enumerate(str(row.get('vod_play_url','')).split('$$$')[:50]):
        if index<len(flags)and flags[index]in WEB_FLAGS:continue
        for episode in group.split('#'):
            label,_,address=episode.partition('$')
            if not address:address=label;label=''
            if re.search('预告|花絮|彩蛋|特辑|幕后',label):continue
            try:
                url=urlsplit(address.split('|',1)[0].strip())
                if url.scheme in ('http','https')and url.hostname and not url.username and re.search(r'\.(m3u8|mp4|m4v|mpd|mkv)$',url.path,re.I):count+=1;break
            except ValueError:continue
    return count

def collect(ref,names,providers,session,deadline,matches,queries,base,norm):
    unique=[];seen=set()
    for provider in providers:
        address=str(provider.get('url','')).rstrip('/')
        if address and address not in seen:unique.append(provider);seen.add(address)
    def one(provider):
        client=session or requests.Session();local=min(deadline,time.monotonic()+20);rows=[];events=[];seen_records=set();complete=True;details=0
        try:
            for query in queries(ref,names)[:12]:
                remaining=local-time.monotonic()
                if remaining<=0:complete=False;events.append({'provider':provider['id'],'http':0,'reason':'deadline'});break
                try:
                    response=client.get(provider['url'],params={'ac':'detail','wd':query},timeout=(min(5,remaining),min(9,remaining)),allow_redirects=False)
                    if response.status_code!=200:
                        events.append({'provider':provider['id'],'http':response.status_code})
                        if response.status_code in (400,404,422):continue
                        complete=False;break
                    for original in response.json().get('list',[])[:30]:
                        row=original;record=str(row.get('vod_id',''))
                        if not record or record in seen_records:continue
                        if norm(base(str(row.get('vod_name',''))))not in {norm(base(n))for n in names}and not(ref.get('douban_id')and str(row.get('vod_douban_id'))==str(ref['douban_id'])):continue
                        if not row.get('vod_play_url')and details<2 and time.monotonic()<local:
                            details+=1;detail=client.get(provider['url'],params={'ac':'detail','ids':record},timeout=(min(5,max(.05,local-time.monotonic())),min(9,max(.05,local-time.monotonic()))),allow_redirects=False)
                            if detail.status_code!=200:complete=False;continue
                            row=next((r for r in detail.json().get('list',[])if str(r.get('vod_id'))==record),{})
                        if not matches(ref,row,names):continue
                        seen_records.add(record);count=usable_groups(row)
                        if count:rows.append((str(row['vod_name']),count))
                except (requests.RequestException,ValueError,TypeError,AttributeError):complete=False;events.append({'provider':provider['id'],'http':0});break
        finally:
            if session is None:client.close()
        return provider['id'],rows,events,complete
    votes={};events=[];checked=0;all_complete=True;pool=ThreadPoolExecutor(max_workers=4);futures=[pool.submit(one,p)for p in unique]
    try:
        for future in as_completed(futures,timeout=max(.01,deadline-time.monotonic())):
            provider,rows,failures,complete=future.result();checked+=1;all_complete&=complete;events+=failures
            for title,count in rows:
                group=votes.setdefault(norm(base(title)),{'titles':set(),'libraries':set(),'routes':0})
                group['titles'].add(title);group['libraries'].add(provider);group['routes']+=count
    except TimeoutError:all_complete=False;events.append({'http':0,'reason':'work_deadline'})
    finally:
        for future in futures:future.cancel()
        pool.shutdown(wait=True,cancel_futures=True)
    if not votes:return None,events
    preferred=norm(base(names[0]))if names else''
    ranked=sorted(votes.items(),key=lambda pair:(-len(pair[1]['libraries']),pair[0]!=preferred,pair[0]));key,best=ranked[0]
    options=[{'title':base(min(g['titles'],key=lambda s:(len(s),s))),'libraries':len(g['libraries'])}for _,g in ranked]
    title=min(best['titles'],key=lambda s:(len(s),s))
    return {'title':title,'routes':best['routes'],'libraries':len(best['libraries']),'selection':{'policy':VOTE_POLICY,'title':base(title),'libraries':len(best['libraries']),'checkedLibraries':checked,'requestedLibraries':len(unique),'complete':all_complete and checked==len(unique),'options':options}},events

def apply_selection(work,selection):
    if not isinstance(selection,dict)or selection.get('policy')!=VOTE_POLICY or not isinstance(selection.get('title'),str)or not re.search('[\u3400-\u9fff]',selection['title'])or type(selection.get('libraries'))is not int or selection['libraries']<1:return
    zh=work.get('zh')or{};old=zh.get('title','');title=selection['title'];zh.update(title=title,aliases=list(dict.fromkeys([title,old]+zh.get('aliases',[]))),nameSelection=selection);work['zh']=zh
