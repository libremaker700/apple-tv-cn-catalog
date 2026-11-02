"""Separate provider account pools. Empty results are success, not an account failure."""
import os,re,time
import requests

def accounts(service):
    seen=set();rows=[]
    for name,value in sorted(os.environ.items()):
        if re.fullmatch(service+r'_API_KEYI?(?:_\d+)?',name) and value.strip() and value.strip() not in seen:
            seen.add(value.strip());rows.append((name,value.strip()))
    return rows

class SearchAccounts:
    def __init__(self,session=None,configured=None,reserve=None):
        self.session=session or requests.Session();self.pools=configured or {s:accounts(s.upper()) for s in ('ydc','tavily')}
        self.disabled=set();self.events=[];self.reserve=reserve or (lambda:True)
    def search(self,query):
        for service in ('ydc','tavily'):
            for name,key in self.pools.get(service,[]):
                if name in self.disabled:continue
                if not self.reserve():return [],'budget_exhausted'
                try:
                    if service=='ydc':
                        r=self.session.post('https://ydc-index.io/v1/search',headers={'X-API-Key':key},json={'query':query,'count':8,'country':'CN','language':'ZH-HANS','boost_domains':['movie.douban.com','watch.plex.tv']},timeout=(8,35),allow_redirects=False)
                    else:
                        r=self.session.post('https://api.tavily.com/search',headers={'Authorization':'Bearer '+key},json={'query':query,'search_depth':'basic','max_results':6,'include_answer':False,'include_raw_content':False},timeout=(8,35),allow_redirects=False)
                    status=r.status_code
                    try:data=r.json()
                    except ValueError:data={}
                    error=str(data.get('error')or data.get('message')or'')[:1000].lower()if isinstance(data,dict)else''
                    exhausted=status in(402,432,433)or bool(re.search(r'credit.{0,30}(exhaust|insufficient|limit|zero)|quota.{0,30}(exceed|exhaust)|usage limit|balance.{0,20}(insufficient|exhaust)',error))
                    self.events.append({'service':service,'account':name,'http':status,'reason':'quota_exhausted'if exhausted else'rate_limited'if status==429 else'http'})
                    if exhausted:self.disabled.add(name);continue
                    if status==200:
                        items=(data.get('results')or{}).get('web',[])if service=='ydc'else data.get('results',[])
                        return [{'title':str(x.get('title',''))[:250],'url':str(x.get('url',''))[:2000]}for x in items[:8]],'ok'
                    if status in (400,404,422):return [],'request_configuration_error'
                    if status in (401,402,403,429)or status>=500:self.disabled.add(name);continue
                    return [],'http_error'
                except (requests.RequestException,ValueError):
                    self.events.append({'service':service,'account':name,'http':0});self.disabled.add(name)
        return [],'accounts_unavailable'
