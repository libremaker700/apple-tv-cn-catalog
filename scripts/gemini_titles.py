"""Single-work grounded Gemini candidate lookup. AI text alone never changes playback bindings."""
import json,os,re
from urllib.parse import urlsplit
import requests
from metadata_policy import allowed_source

DEFAULT_MODEL='gemini-2.5-flash'

def extract_titles(text):
    """Read the answer's mainland-title field, not every movie/book mentioned in prose."""
    lines=[line.strip() for line in str(text or '').splitlines() if line.strip()]
    candidates=[]
    for line in lines:
        if re.search(r'未核实|未查到|暂无|暂未|猜测|建议译|暂译|直译为',line):continue
        if re.search(r'(?:大陆|国内|中国).{0,90}?《',line) or re.match(r'^[*#\s]*《',line):
            matches=re.findall(r'《([^》\n]{1,90})》',line)
            if matches:candidates=matches[:1];break
    out=[]
    for value in candidates:
        value=re.sub(r'[*_`]|\[(.*?)\]\([^)]*\)',lambda m:m[1] or '' if m.lastindex else '',value).strip()
        value=re.sub(r'\s*[（(](?:19|20)\d{2}[)）]\s*$','',value).strip()
        if re.search(r'[（(](?:港|台|香港|台湾|臺灣)[)）]',value):continue
        if not re.search(r'[\u3400-\u9fff]',value) or not 2<=len(value)<=60:continue
        if value not in out:out.append(value)
    return out

def redact(value,secrets=()):
    raw=json.dumps(value,ensure_ascii=False)
    for secret in secrets:
        if secret:raw=raw.replace(secret,'[REDACTED]')
    raw=re.sub(r'AIza[A-Za-z0-9_-]{20,}|tvly-[A-Za-z0-9_-]{12,}','[REDACTED]',raw)
    return json.loads(raw)

class GeminiTitles:
    def __init__(self,key,model=DEFAULT_MODEL,session=None):
        self.key=key.strip();self.model=model;self.session=session or requests.Session()
        if not re.fullmatch(r'gemini-[a-zA-Z0-9.-]{1,80}',model):raise ValueError('Invalid model name')
    def search(self,ref):
        report={'status':'missing_api_key','model':self.model,'api_http':0,'grounded':False,'candidate_titles':[],'sources':[]}
        if not self.key:return report
        prompt=(f"请实际使用 Google Search 联网检索，核对这部作品在中国大陆的常用中文片名。英文原名：{ref['english_title']}；"
                f"作品类型：{'电影' if ref['kind']=='movie' else '电视剧'}；年份：{ref['year']}；苹果官网：{ref.get('official_url','')}。"
                "不要把同名书籍、其他年份电影或其他季混为一谈。大陆译名优先，不采用仅供香港、台湾使用的译名。"
                "首行只写：大陆片名：《片名》。之后用两句话说明原名、年份和身份核对依据并引用网页来源。"
                "若没有可靠中文片名，首行写：大陆片名：未核实。不要猜测，也不要推荐其他电影。")
        body={'contents':[{'parts':[{'text':prompt}]}],'tools':[{'google_search':{}}],
              'generationConfig':{'temperature':0.1,'maxOutputTokens':1024}}
        try:
            response=self.session.post(f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent',
                headers={'x-goog-api-key':self.key,'Content-Type':'application/json'},json=body,timeout=(10,75),allow_redirects=False)
            report['api_http']=response.status_code;data=response.json()
        except (requests.RequestException,ValueError):report['status']='transport_or_json_error';return report
        if report['api_http']!=200:
            report.update(status='api_error',api_error_code=(data.get('error') or {}).get('status','unknown'))
            return redact(report,[self.key])
        candidate=(data.get('candidates') or [{}])[0]
        text='\n'.join(part.get('text','') for part in candidate.get('content',{}).get('parts',[]) if not part.get('thought'))
        grounding=candidate.get('groundingMetadata') or {};queries=grounding.get('webSearchQueries') or []
        sources=[]
        for chunk in grounding.get('groundingChunks',[]):
            web=chunk.get('web') or {};url=web.get('uri','')
            if allowed_source(url):sources.append({'title':str(web.get('title',''))[:200],'url':url[:2500]})
        report.update(grounded=bool(queries and sources),answer=text[:4000],sources=sources[:8],search_queries=queries[:6],
                      finish_reason=candidate.get('finishReason'),usage=data.get('usageMetadata',{}),model_version=data.get('modelVersion',''))
        report['candidate_titles']=extract_titles(text) if report['grounded'] else []
        report['status']='ok' if report['candidate_titles'] else ('no_mainland_title' if report['grounded'] else 'no_grounding_evidence')
        return redact(report,[self.key])
