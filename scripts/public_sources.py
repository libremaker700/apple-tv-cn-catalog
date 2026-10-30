"""Bounded public-page reads with positive cache and host-wide access-error cooldowns."""
import hashlib,html,json,re,time
from pathlib import Path
from urllib.parse import urlencode,urlsplit
import requests
HOSTS={'movie.douban.com','zh.wikipedia.org','en.wikipedia.org','baike.baidu.com','api.bgm.tv'}

def plain_html(raw):
    raw=re.sub(r'(?is)<(script|style|head|nav|footer)\b[^>]*>.*?</\1>','',raw)
    raw=re.sub(r'(?i)<br\s*/?>|</(?:h[1-6]|p|div|li|section|tr)>','\n',raw)
    raw=html.unescape(re.sub(r'<[^>]+>','',raw))
    return '\n'.join(re.sub(r'[ \t]+',' ',line).strip() for line in raw.splitlines() if line.strip())

class PublicPages:
    def __init__(self,session=None,path=None,clock=None):
        self.session=session or requests.Session();self.path=Path(path) if path else None;self.clock=clock or time.time;self.events=[];self.bodies={}
        self.data={'schema':1,'pages':{},'hosts':{}}
        if self.path and self.path.exists():
            try:
                value=json.loads(self.path.read_text(encoding='utf8'))
                if value.get('schema')==1:self.data=value
            except (ValueError,OSError):pass
    def save(self):
        if not self.path:return
        pages=self.data['pages']
        while len(pages)>100 or sum(len(json.dumps(v,ensure_ascii=False)) for v in pages.values())>2_000_000:
            del pages[min(pages,key=lambda k:pages[k]['fetched_at'])]
        self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.data,ensure_ascii=False,separators=(',',':')),encoding='utf8');tmp.replace(self.path)
    def get(self,url,params=None):
        parts=urlsplit(url);host=parts.hostname;now=int(self.clock())
        if parts.scheme!='https' or host not in HOSTS or parts.username or parts.password:return None
        full=url+('?' + urlencode(sorted(params.items())) if params else '')
        key=hashlib.sha256(full.encode()).hexdigest();old=self.data['pages'].get(key,{})
        if old.get('expires_at',0)>now and (old.get('status')!=200 or key in self.bodies):
            self.events.append({'host':host,'status':old['status'],'cached':True});return self.bodies.get(key)
        blocked=self.data['hosts'].get(host,{})
        if blocked.get('retry_at',0)>now:
            self.events.append({'host':host,'status':blocked['status'],'cooldown':True});return None
        status=0;body=None
        try:
            response=self.session.get(url,params=params,headers={'User-Agent':'AppleTVCnCatalog/1.0 (public metadata verification)'},timeout=(6,15),allow_redirects=False)
            status=response.status_code
            if status==200 and len(response.content)<=512_000:body=response.text
        except requests.RequestException:pass
        self.events.append({'host':host,'status':status,'cached':False})
        if status in (401,403,418,429) or status==0 or 300<=status<400 or status>=500:
            self.data['hosts'][host]={'status':status,'retry_at':now+(86400 if status==429 else 21600)}
        if body:self.bodies[key]=body
        # Persist only transport metadata, never whole article/review HTML or credentials.
        self.data['pages'][key]={'url':full,'status':status,'fetched_at':now,'expires_at':now+(7*86400 if body else 21600),'sha256':hashlib.sha256(body.encode()).hexdigest() if body else ''}
        self.save();return body
    def json(self,url,**kwargs):
        raw=self.get(url,kwargs.get('params'))
        try:return json.loads(raw) if raw else {}
        except ValueError:
            self.data['hosts'][urlsplit(url).hostname]={'status':200,'reason':'non_json_response','retry_at':int(self.clock())+21600};self.save()
            return {}
