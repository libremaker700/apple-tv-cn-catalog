"""Manual experiment only: search candidates, independently check identities, never publish."""
import json, os, re, time, unicodedata
from pathlib import Path
from urllib.parse import urlsplit
import requests
from title_sources import Lookup, mentions_original, structured_patch
from douban_mobile import DoubanMobile
from gemini_titles import GeminiTitles

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'logs/title-api-experiment.json'
SECRETS=[v for k,v in os.environ.items() if re.match(r'^(?:YDC|TAVILY|GEMINI)_API_KEY',k) and v]
def safe(value):
    raw=json.dumps(value,ensure_ascii=False)
    for key in SECRETS:raw=raw.replace(key,'[REDACTED]')
    return json.loads(raw)
def save(report):
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(safe(report),ensure_ascii=False,indent=2),encoding='utf-8')
def pools(prefix):
    seen=set();out=[]
    for name,value in sorted(os.environ.items()):
        if name.startswith(prefix+'_API_KEY') and value and value not in seen:seen.add(value);out.append({'name':name,'key':value,'usable':False})
    return out
def search(service,slot,query):
    try:
        if service=='ydc':
            r=requests.post('https://ydc-index.io/v1/search',headers={'X-API-Key':slot['key']},json={'query':query,'count':8,'extraction':{'extraction_mode':'highlights'}},timeout=(8,35),allow_redirects=False)
        else:
            r=requests.post('https://api.tavily.com/search',headers={'Authorization':'Bearer '+slot['key']},json={'query':query,'search_depth':'basic','max_results':6,'include_answer':False,'include_raw_content':False},timeout=(8,35),allow_redirects=False)
        if r.status_code!=200:return [],{'http':r.status_code,'status':'unavailable'}
        data=r.json();rows=(data.get('results')or{}).get('web',[]) if service=='ydc' else data.get('results',[])
        result=[]
        for row in rows:
            contents=row.get('contents')or{};snippets=contents.get('highlights')or row.get('snippets')or [row.get('content',''),row.get('description','')]
            result.append({'title':str(row.get('title',''))[:220],'url':str(row.get('url',''))[:2000],'text':'\n'.join(str(x)for x in snippets)[:1800]})
        return result,{'http':200,'status':'ok','results':len(result)}
    except Exception as e:return [],{'http':0,'status':type(e).__name__}
def norm(text):return re.sub(r'[^a-z0-9\u3400-\u9fff]','',unicodedata.normalize('NFKC',text).casefold())
def candidate_name(title):
    title=re.sub('<[^>]*>','',title).strip()
    title=re.split(r'\s*(?:\(|（|\s+-\s+|\s+[-|_]\s*)',title,1)[0].strip('《》 ')
    title=re.split(r'[A-Za-z]',title,1)[0].strip(' ·:：-')
    return title if re.search(r'[\u3400-\u9fff]',title)and 2<=len(title)<=70 else ''
def is_site(url):
    host=urlsplit(url).hostname or ''
    return 'douban' if host in ('movie.douban.com','m.douban.com') and re.search(r'/subject/\d+',urlsplit(url).path) else 'ikanbot' if host.endswith('ikanbot.com')and re.search(r'/(?:play|detail)/\d+',urlsplit(url).path) else ''
def main():
    records=json.loads((ROOT/'data/title-api-probe-input.json').read_text(encoding='utf-8'))['records']
    report={'mode':'manual_experiment_no_publication','catalogModified':False,'checkedAt':int(time.time()),'keyHealth':[],'records':[],'usage':{'ydc':0,'tavily':0,'gemini':0},'siteFailures':[]}
    services={s:pools(s.upper()) for s in ('ydc','tavily')};healthy_gemini=[]
    smoke='"Blood Diamond" 2006 豆瓣 中文片名'
    for service,slots in services.items():
        for slot in slots:
            hits,status=search(service,slot,smoke);report['usage'][service]+=1;slot['usable']=status.get('http')==200
            report['keyHealth'].append(dict(service=service,keyName=slot['name'],**status))
            print(json.dumps(report['keyHealth'][-1]),flush=True);save(report)
    for slot in pools('GEMINI'):
        discovery=GeminiTitles(slot['key']).models();models=[m['name']for m in discovery.get('models',[])if 'generateContent'in m.get('methods',[])]
        model=next((m for m in ('gemini-2.5-flash','gemini-2.5-flash-lite','gemini-3.1-flash-lite','gemini-3.5-flash-lite')if m in models),None)
        status={'service':'gemini','keyName':slot['name'],'modelsHttp':discovery.get('api_http'), 'http':0,'status':'no_supported_model'}
        if model:
            value=GeminiTitles(slot['key'],model).search({'english_title':'Blood Diamond','kind':'movie','year':2006,'official_url':''})
            report['usage']['gemini']+=1;status.update(http=value.get('api_http'),status=value.get('status'),candidateTitles=value.get('candidate_titles',[]),model=model)
            if status['http']==200:slot.update(model=model,usable=True);healthy_gemini.append(slot)
        report['keyHealth'].append(status);print(json.dumps(status,ensure_ascii=False),flush=True);save(report)
    for url in ('https://www2.ikanbot.com/','https://www2.ikanbot.com/play/1028329'):
        try:r=requests.get(url,timeout=(6,15),allow_redirects=False);report['siteFailures'].append({'url':url,'http':r.status_code})
        except Exception:report['siteFailures'].append({'url':url,'http':0})
    if not any(s['usable']for s in services['ydc']):
        report['status']='ydc_unavailable_cannot_validate_requested_primary_path';save(report);return
    lookup=Lookup(cache_path=ROOT/'data/probe-public-source-cache.json')
    def query(text):
        for service in ('ydc','tavily'):
            for slot in services[service]:
                if not slot['usable']:continue
                hits,status=search(service,slot,text);report['usage'][service]+=1
                if status['http']==200:return hits,{'service':service,'keyName':slot['name'],**status}
                slot['usable']=False;report.setdefault('failovers',[]).append({'service':service,'keyName':slot['name'],**status});save(report)
        return [],{'status':'all_search_accounts_unavailable'}
    for index,work in enumerate(records):
        year=work.get('originalYear')or work.get('year')or ''
        ref={'english_title':work['en'],'original_title':work['en'],'kind':'movie'if work['kind']=='movie'else'tv','year':year,'want_summary':False}
        question='"'+work['en']+'" '+str(year)+' 中国大陆 中文名 豆瓣'
        hits,api=query(question);row={'key':work['key'],'en':work['en'],'kind':work['kind'],'season':work['season'],'animation':work['animation'],'originalYear':year,'sourceYear':work.get('reference',{}).get('year')if work.get('reference')else work.get('year'),'oldTitle':work['title'],'reference':work.get('reference'),'api':api,'candidates':[],'verification':[]}
        candidates={}
        def add(name,evidence,confidence):
            name=re.sub(r'\s*第\s*[0-9一二三四五六七八九十]+\s*季\s*$','',name).strip()
            if not re.search(r'[\u3400-\u9fff]',name)or len(name)>70:return
            key=norm(name)
            item=candidates.setdefault(key,{'title':name,'sources':[],'confidence':confidence})
            if evidence not in item['sources']:item['sources'].append(evidence)
            if confidence=='DOUBAN_VERIFIED':item['confidence']=confidence
        direct_checked=set()
        for hit in hits:
            site=is_site(hit['url']);text=hit['title']+' '+hit['text']
            if not site:continue
            original=mentions_original(work['en'],text)
            if not original:continue
            name=candidate_name(hit['title'])
            if site=='douban':
                sid=re.search(r'/subject/(\d+)',urlsplit(hit['url']).path)[1]
                if sid not in direct_checked and len(direct_checked)<2:
                    direct_checked.add(sid)
                    try:patch=DoubanMobile(lookup.pages).subject(ref,sid,str(int(time.time())))
                    except Exception:patch=None
                    if patch:
                        add(patch['display_name_zh'],{'site':'douban','url':hit['url'],'method':'mobile_identity_fields'},'DOUBAN_VERIFIED')
                        for alias in patch.get('aliases_zh',[])[:4]:add(alias,{'site':'douban','url':hit['url'],'method':'verified_alias'},'DOUBAN_VERIFIED')
                        row['doubanTitle']=patch['display_name_zh'];row['doubanId']=sid
            if name and (not year or str(year)in text):add(name,{'site':site,'url':hit['url'],'method':'indexed_original_title_and_year'},'INDEXED_IDENTITY')
        # A separate site lookup validates candidates; the initial model/search answer alone is not enough.
        if not candidates:
            hits2,api2=query('"'+work['en']+'" site:www2.ikanbot.com OR site:movie.douban.com 中文')
            row['siteLookupApi']=api2
            for hit in hits2:
                site=is_site(hit['url']);text=hit['title']+' '+hit['text'];name=candidate_name(hit['title'])
                if site and name and mentions_original(work['en'],text)and(not year or str(year)in text):add(name,{'site':site,'url':hit['url'],'method':'indexed_original_title_and_year'},'INDEXED_IDENTITY')
        row['candidates']=list(candidates.values())[:6]
        row['status']='CANDIDATES_READY_FOR_SOURCE_CHECK'if row['candidates']else'NO_SITE_VERIFIED_NAME'
        row['publicFetchEvents']=lookup.pages.events[-4:];report['records'].append(row);save(report)
        print(json.dumps({'progress':index+1,'total':len(records),'en':work['en'],'candidates':[c['title']for c in row['candidates']],'status':row['status']},ensure_ascii=False),flush=True)
        time.sleep(.3)
    report['status']='name_lookup_completed';report['finishedAt']=int(time.time());save(report)

if __name__=='__main__':main()
