"""Bounded automatic alias discovery. Search/model text is never identity evidence."""
import math,re,time
from concurrent.futures import ThreadPoolExecutor
import requests
from provider_adapters import create,AdapterError
from mainland_names import candidate_matches,base,source_people
from title_sources import norm,chinese

def keywords(original,hints):
    out=[]
    for name in [original]+hints[:4]:
        if not isinstance(name,str)or not name.strip():continue
        out.append(name.strip()[:80])
        if chinese(name):
            word=re.sub(r'[^\u3400-\u9fff]','',base(name))
            if len(word)>=4:out.append(word[-2:])
    return list(dict.fromkeys(out))[:4]

def model_hints(ref):
    from api_accounts import accounts
    from gemini_titles import GeminiTitles
    events=[]
    for name,key in accounts('GEMINI'):
        result=GeminiTitles(key).search(ref)
        events.append({'account':name,'http':result.get('api_http',0),'status':result['status']})
        if result['status']=='ok':return result['candidate_titles'][:3],events
        if result.get('api_http')==200:break
    return [],events

def discover(identity,ref,providers,hints=(),deadline=None,state=None):
    if not identity:return None,[]
    deadline=deadline or time.monotonic()+90
    target=source_people({'kind':'movie'if ref['kind']=='movie'else'series','season':ref['season'],'year':ref['year'],'douban_id':identity['douban_id']},identity)
    state=state if state is not None else{}
    queries=keywords(ref['english_title'],list(hints));budget=min(20,max(.01,(deadline-time.monotonic())/max(1,math.ceil(len(providers)/4))))
    def one(provider):
        session=requests.Session();events=[];accepted=[];seen=set();details=0;local=min(deadline,time.monotonic()+budget)
        try:
            adapter=create(provider,session,local)
            cursor=state.setdefault(provider['id'],{})
            if cursor.get('queries')!=queries or cursor.get('done'):cursor.clear();cursor.update(queries=queries,q=0,page=1,offset=0)
            pages=0
            while cursor['q']<len(queries)and pages<3:
                    query=queries[cursor['q']];page=cursor['page'];pages+=1
                    if time.monotonic()>=local:raise AdapterError('deadline')
                    rows=adapter.request({'wd':query,'pg':page})if provider.get('type','cms')=='cms'else adapter.search(query)
                    fresh=0
                    start=cursor.get('offset',0)
                    for index,row in enumerate(rows[start:],start):
                        cursor['offset']=index
                        record=str(row.get('vod_id',''))
                        if not record or record in seen:continue
                        seen.add(record);fresh+=1
                        # Short search-list rows need details even without a known alias.
                        name=str(row.get('vod_name',''))
                        if not chinese(name):continue
                        if not row.get('type_name')or not row.get('vod_play_url')or not row.get('vod_douban_id'):
                            if details>=5:raise AdapterError('detail_limit')
                            details+=1;row=adapter.describe(row)
                        if candidate_matches(target,row,[base(str(row.get('vod_name','')))]):accepted.append(base(str(row['vod_name'])))
                        cursor['offset']=index+1
                    cursor['offset']=0
                    if not rows or not fresh or provider.get('type','cms')!='cms':cursor['q']+=1;cursor['page']=1
                    else:cursor['page']+=1
            cursor['done']=cursor['q']>=len(queries)
            if not cursor['done']:events.append({'provider':provider['id'],'reason':'page_limit'})
        except (AdapterError,requests.RequestException,ValueError,TypeError,KeyError)as error:events.append({'provider':provider['id'],'reason':getattr(error,'reason','transport')})
        finally:session.close()
        return accepted,events
    names={};events=[]
    with ThreadPoolExecutor(max_workers=4)as pool:
        for accepted,errors in pool.map(one,providers):
            events+=errors
            for name in accepted:names.setdefault(norm(name),name)
    if not names:return None,events
    aliases=list(names.values());title=aliases[0]
    return {'display_name_zh':title,'aliases_zh':aliases,'douban_id':identity['douban_id'],'sources':[{'type':'douban_identity_cms_alias','url':identity['url']}],'actors':identity['actors'],'directors':identity['directors']},events
