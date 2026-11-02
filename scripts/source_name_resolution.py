"""AI names are locators; only identity-checked playable library votes may rename a work."""
import copy,hashlib,json,re,time
POLICY='ai-answer-verified-source-or-douban-v1'
def resolve(identity,ref,providers,client,direct_patch=None,hints=(),state=None,probe=None,discover=None,now=None):
    from mainland_names import public_sources,source_people,base
    from alias_discovery import discover as find_aliases
    state=state if state is not None else{};now=int(time.time()if now is None else now);probe=probe or public_sources;discover=discover or find_aliases
    original=identity.get('title')or ref['english_title'];kind='movie'if ref['kind']=='movie'else'series'
    key=hashlib.sha256(json.dumps([POLICY,identity['douban_id'],ref['english_title'],ref['year'],ref['season'],original],ensure_ascii=False).encode()).hexdigest()
    ai=state.get('answer',{})
    if state.get('key')!=key or now>=state.get('expiresAt',0):
        question=(f"{ref['year']}年的{ref['english_title']}（{'电影'if kind=='movie'else'第'+str(ref['season'])+'季剧集'}，豆瓣编号{identity['douban_id']}）在中国叫什么？请查实际使用的中文片名、中文别名及视频片库使用的名字。区分同名书籍、其他年份作品和其他季，不要仅凭字面翻译猜测。只输出JSON对象，格式为names字段的中文名称数组；不确定则返回空数组。")
        ai=client.candidate_names(question);state.update(key=key,answer=copy.deepcopy(ai),expiresAt=now+(7*86400 if ai.get('names')else 3600))
    candidates=list(dict.fromkeys(list(hints)+[n for n in ai.get('names',[])if isinstance(n,str)and re.search(r'[\u3400-\u9fff]',n)]+[original]+identity.get('aliases',[])))[:4]
    target=source_people({'kind':kind,'year':str(identity['year'])if kind=='movie'else str(ref['year']),'season':int(ref['season']or 1),'douban_id':identity['douban_id']},identity)
    deadline=time.monotonic()+180;events=[];stages=[]
    best,errors=probe(target,candidates,providers,deadline=min(deadline,time.monotonic()+60));events+=errors;stages.append('ai_candidates_source_query')
    strong=lambda value:bool(value and value.get('routes',0)>0 and value.get('selection',{}).get('libraries',0)>0 and not value.get('recallOnly'))
    discovered=[]
    if not strong(best):
        alias,errors=discover(identity,ref,providers,candidates,deadline=min(deadline,time.monotonic()+60),state=state.setdefault('discovery',{}));events+=errors;stages.append('bounded_keyword_discovery')
        if alias:
            discovered=alias.get('aliases_zh',[])[:4]
            best,errors=probe(target,discovered,providers,deadline=deadline);events+=errors;stages.append('discovered_alias_source_query')
    selected=strong(best);title=base(best['title'])if selected else original
    patch=copy.deepcopy(direct_patch)if direct_patch else {'metadataPolicy':'mainland-v1','name_status':'verified_title_sources','name_checked_at':str(now),'sources':[{'type':'douban_mobile_identity','url':identity['url'],'retrieved_at':str(now)}]}
    verified_aliases=[o['title']for o in best.get('selection',{}).get('options',[])if o.get('libraries',0)>0]if selected else[]
    patch.update(display_name_zh=title,aliases_zh=list(dict.fromkeys([title,original]+identity.get('aliases',[])+verified_aliases)),douban_id=identity['douban_id'],douban_title=original,actors=identity.get('actors',[]),directors=identity.get('directors',[]))
    if selected:patch['sources']=[{'type':'douban_identity_cms_alias','url':identity['url'],'retrieved_at':str(now)}]+patch.get('sources',[])
    return {'patch':patch,'best':best if selected else None,'events':events,'evidence':{'policy':POLICY,'aiStatus':ai.get('status'),'aiService':ai.get('service'),'aiCandidates':ai.get('names',[]),'aiSources':ai.get('sources',[]),'queryNames':candidates,'discoveredAliases':discovered,'doubanTitle':original,'selectedTitle':title,'decision':'verified_playable_source_name'if selected else'douban_fallback_no_confirmed_source','stages':stages}}
