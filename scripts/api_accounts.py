"""Separate provider account pools. Empty results are success, not an account failure."""
import os,re,time,json
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
    def candidate_names(self,question):
        """Ask an answer-generating service; returned names remain untrusted queries."""
        from opencc import OpenCC
        for service in ('ydc','tavily'):
            for name,key in self.pools.get(service,[]):
                if name in self.disabled:continue
                if not self.reserve():return {'names':[],'sources':[],'status':'budget_exhausted'}
                try:
                    if service=='ydc':
                        r=self.session.post('https://api.you.com/v1/research',headers={'X-API-Key':key},json={'input':question,'research_effort':'lite'},timeout=(8,45),allow_redirects=False)
                    else:
                        r=self.session.post('https://api.tavily.com/search',headers={'Authorization':'Bearer '+key},json={'query':question,'search_depth':'basic','max_results':6,'include_answer':'advanced','include_raw_content':False},timeout=(8,45),allow_redirects=False)
                    try:data=r.json()
                    except ValueError:data={}
                    status=r.status_code;error=str(data.get('error')or data.get('message')or'')[:1000].lower()if isinstance(data,dict)else''
                    exhausted=status in(402,432,433)or bool(re.search(r'credit.{0,30}(exhaust|insufficient|limit|zero)|quota.{0,30}(exceed|exhaust)|usage limit|balance.{0,20}(insufficient|exhaust)',error))
                    self.events.append({'service':service,'account':name,'stage':'candidate_answer','http':status,'reason':'quota_exhausted'if exhausted else'rate_limited'if status==429 else'request_configuration_error'if status in(400,404,422)else'http'})
                    if exhausted:self.disabled.add(name);continue
                    if status!=200:
                        if status==401:self.disabled.add(name);continue
                        break  # Endpoint/configuration/rate errors are not fixed by cycling the same service's keys.
                    output=data.get('output')or{};answer=output.get('content','')if service=='ydc'else data.get('answer','')
                    text=answer if isinstance(answer,str)else json.dumps(answer,ensure_ascii=False)
                    text=text[:12000];names=[]
                    try:
                        clean=re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip());value=json.loads(clean);names=value.get('names',[])if isinstance(value,dict)else value if isinstance(value,list)else[]
                    except ValueError:pass
                    names+=re.findall(r'《([^》]{2,40})》|[“\"]([^”\"\n]{2,40})[”\"]',text)
                    names=[v[0]or v[1]if isinstance(v,tuple)else v for v in names]
                    cc=OpenCC('t2s');names=list(dict.fromkeys(cc.convert(v.strip())for v in names if isinstance(v,str)and 2<=len(v.strip())<=40 and re.search(r'[\u3400-\u9fff]',v)and not re.search(r'https?://|[<>{}\n]',v)))[:4]
                    rows=output.get('sources',[])if service=='ydc'else data.get('results',[])
                    sources=[{'title':str(x.get('title',''))[:200],'url':str(x.get('url',''))[:2000]}for x in rows[:8]if isinstance(x,dict)and str(x.get('url','')).startswith('https://')]
                    if names:return {'names':names,'sources':sources,'status':'ok','service':service}
                    break  # An empty answer can use the other service, not identical keys.
                except (requests.RequestException,ValueError,TypeError):
                    self.events.append({'service':service,'account':name,'stage':'candidate_answer','http':0});break
        return {'names':[],'sources':[],'status':'accounts_unavailable'}
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
