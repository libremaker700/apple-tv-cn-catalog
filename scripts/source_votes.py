"""Count identity-checked direct-media libraries per title, never lines per library."""
import math,re,time
from concurrent.futures import ThreadPoolExecutor,as_completed,TimeoutError
from urllib.parse import urlsplit
import requests
from provider_adapters import create,provider_key,AdapterError

VOTE_POLICY='library-votes-v1'
WEB_FLAGS={'changzhang','ruyi','jjzy','ukyun','hnyun','gsyun','subyun'}

def incomplete(events):return any(event.get('reason')not in(None,'checked')or event.get('http',0)not in(200,400,404,422)for event in events)

def canonical_name(ref,title,names,base,norm):
    root=base(title);expected={norm(base(name))for name in names};year=str(ref.get('year',''))
    if norm(root)not in expected and re.fullmatch(r'(19|20)\d{2}',year):
        shorter=base(re.sub(r'\s*[（(]?'+year+r'[）)]?\s*$','',root))
        if shorter and norm(shorter)in expected:return shorter
    return title

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

def collect(ref,names,providers,session,deadline,matches,queries,base,norm,recall=None,name_evidence=False):
    unique=[];seen=set()
    for provider in providers:
        address=provider_key(provider)
        if address not in seen:unique.append(provider);seen.add(address)
    # Reserve a fair slot for every library before aliases can consume the
    # work's entire budget in the first few libraries.
    provider_budget=min(20,max(.01,(deadline-time.monotonic())/max(1,math.ceil(len(unique)/4))))
    def one(provider):
        client=session or requests.Session();local=min(deadline,time.monotonic()+provider_budget);rows=[];events=[];seen_records=set();complete=True;details=0
        try:
            adapter=create(provider,client,local)
            for query in queries(ref,names)[:12]:
                remaining=local-time.monotonic()
                if remaining<=0:complete=False;events.append({'provider':provider['id'],'http':0,'reason':'deadline'});break
                try:
                    for original in adapter.search(query):
                        row=original;record=str(row.get('vod_id',''))
                        if not record or record in seen_records:continue
                        if norm(base(canonical_name(ref,str(row.get('vod_name','')),names,base,norm)))not in {norm(base(n))for n in names}and not(ref.get('douban_id')and str(row.get('vod_douban_id'))==str(ref['douban_id'])):continue
                        if not row.get('vod_play_url'):
                            if details>=4 or time.monotonic()>=local:complete=False;continue
                            details+=1;row=adapter.describe(row)
                        strong=matches(ref,row,names)
                        if not strong and not(recall and recall(ref,row,names)):
                            same_id=ref.get('douban_id')and str(row.get('vod_douban_id'))==str(ref['douban_id'])
                            id_conflict=ref.get('douban_id')and re.fullmatch(r'[1-9][0-9]{4,9}',str(row.get('vod_douban_id','')))and str(row['vod_douban_id'])!=str(ref['douban_id'])
                            if not row.get('type_name')or not same_id and not id_conflict:
                                complete=False;events.append({'provider':provider['id'],'http':200,'reason':'identity_pending'})
                            continue
                        seen_records.add(record)
                        if name_evidence and strong and has_play_entries(row):
                            rows.append((canonical_name(ref,str(row['vod_name']),names,base,norm),usable_groups(row),True))
                            continue
                        row=adapter.playable(row);count=usable_groups(row)
                        if count:rows.append((canonical_name(ref,str(row['vod_name']),names,base,norm),count,strong))
                except AdapterError as error:
                    complete=False;events.append({'provider':provider['id'],'http':error.http,'reason':error.reason})
                    if error.reason=='http'and error.http in(400,404,422):continue
                    break
                except (requests.RequestException,ValueError,TypeError,AttributeError):complete=False;events.append({'provider':provider['id'],'http':0});break
        except AdapterError as error:complete=False;events.append({'provider':provider['id'],'http':error.http,'reason':error.reason})
        finally:
            if session is None:client.close()
        events.append({'provider':provider['id'],'http':200,'reason':'checked'if complete else'partial_results','matchedRecords':len(rows),'identityRecords':sum(int(row[2])for row in rows),'routes':sum(row[1]for row in rows)})
        return provider['id'],rows,events,complete
    votes={};events=[];checked=0;attempted=0;all_complete=True;libraries=set();routes=0;pool=ThreadPoolExecutor(max_workers=4);futures=[pool.submit(one,p)for p in unique]
    try:
        for future in as_completed(futures,timeout=max(.01,deadline-time.monotonic())):
            provider,rows,failures,complete=future.result();attempted+=1;checked+=int(complete);all_complete&=complete;events+=failures
            if rows:libraries.add(provider)
            routes+=sum(row[1]for row in rows)
            for title,count,strong in rows:
                if not strong:continue
                group=votes.setdefault(norm(base(title)),{'titles':set(),'libraries':set(),'routes':0})
                group['titles'].add(title);group['libraries'].add(provider);group['routes']+=count
    except TimeoutError:all_complete=False;events.append({'http':0,'reason':'work_deadline'})
    finally:
        for future in futures:future.cancel()
        pool.shutdown(wait=True,cancel_futures=True)
    coverage=all_complete and checked==len(unique)
    if not votes:
        return ({'title':names[0],'routes':routes,'libraries':len(libraries),'recallOnly':True,'complete':coverage}if routes and names else None),events
    preferred=norm(base(names[0]))if names else''
    ranked=sorted(votes.items(),key=lambda pair:(-len(pair[1]['libraries']),pair[0]!=preferred,pair[0]));key,best=ranked[0]
    options=[{'title':base(min(g['titles'],key=lambda s:(len(s),s))),'libraries':len(g['libraries'])}for _,g in ranked]
    title=min(best['titles'],key=lambda s:(len(s),s))
    return {'title':title,'routes':routes,'libraries':len(libraries),'complete':coverage,**({'nameEvidenceOnly':True}if name_evidence else{}),'selection':{'policy':VOTE_POLICY,'title':base(title),'libraries':len(best['libraries']),'checkedLibraries':checked,'attemptedLibraries':attempted,'requestedLibraries':len(unique),'complete':coverage,'options':options}},events

def has_play_entries(row):
    """Playback metadata can prove a source name even when the media has expired."""
    if row.get('_hasPlayEntries'):return True
    for group in str(row.get('vod_play_url','')).split('$$$')[:50]:
        for entry in group.split('#'):
            label,separator,address=entry.partition('$')
            if re.search('预告|花絮|彩蛋|特辑|幕后',label):continue
            if separator and address.strip():return True
            if not separator and re.match(r'^https?://',label):return True
    return False

def apply_selection(work,selection):
    if not isinstance(selection,dict)or selection.get('policy')!=VOTE_POLICY or not isinstance(selection.get('title'),str)or not re.search('[\u3400-\u9fff]',selection['title'])or type(selection.get('libraries'))is not int or selection['libraries']<1:return
    zh=work.get('zh')or{};old=zh.get('title','');title=selection['title'];zh.update(title=title,aliases=list(dict.fromkeys([title,old]+zh.get('aliases',[]))),nameSelection=selection);work['zh']=zh
