"""Read the public US page API advertised by Apple's own bootstrap configuration.

Only public display metadata is retained. Playback assets, sessions and account fields are discarded.
"""
import json,re,time,copy
from pathlib import Path
from urllib.parse import urlsplit
import requests
from title_lookup import read,dump
from home_sources import CHANNEL

def slim_item(x):
    out={k:x[k] for k in ('id','type','title','url','releaseDate','description','heroDescription','genres') if k in x}
    out['images']={k:{f:v[f] for f in ('url','width','height') if f in v} for k,v in x.get('images',{}).items() if isinstance(v,dict)}
    return out

def slim_shelf(s):
    return {**{k:s[k] for k in ('id','displayType','url','nextToken') if k in s},'header':{k:v for k,v in (s.get('header')or{}).items() if k in ('title','url','supportsSeeAllView')},'items':[slim_item(i) for i in s.get('items',[])]}

class Pages:
    def __init__(self,root,html):
        match=re.search(r'<script[^>]*id=["\']serialized-server-data["\'][^>]*>(.*?)</script>',html,re.S)
        blocks=json.loads(match[1])['data'];props=next(b['data']['configuration']['applicationProps'] for b in blocks if 'configuration' in b.get('data',{}))
        self.routes=props['routes'];self.params=props['requiredParamsMap']['Default'];assert self.params['sf']=='143441' and self.params['locale']=='en-US'
        self.session=requests.Session();self.path=root/'data/official-pages-cache.json';self.cache=read(self.path,{});self.requests=0
    def get(self,route,identity,token=None):
        assert re.fullmatch(r'[a-zA-Z0-9.\-]{1,150}',identity)
        params=dict(self.params)
        if token is not None:
            if not re.fullmatch(r'[a-zA-Z0-9:_\-]{1,100}',str(token)):raise ValueError('Invalid pagination token')
            params['nextToken']=token
        key=route+':'+identity+':'+str(token or '');old=self.cache.get(key);now=int(time.time())
        if old and route not in ('channel','room','shelf') and now-old['checkedAt']<6*3600:return copy.deepcopy(old['value'])
        name,kind={'channel':('getCanvasBinding','channels'),'room':('getCanvasBinding','rooms'),'shelf':('getCollectionById',None),'movie':('getMovieDetailById',None),'series':('getShowDetailById',None)}[route]
        url=self.routes[name]['url']
        for k,v in {'canvasType':kind,'entityId':identity,'collectionId':identity,'movieId':identity,'showId':identity}.items():url=url.replace('{'+k+'}',v or '')
        parts=urlsplit(url)
        if parts.scheme!='https' or parts.hostname!='uts-api.itunes.apple.com' or not parts.path.startswith('/uts/v3/'):raise ValueError('Invalid public page route')
        self.requests+=1;r=self.session.get(url,params=params,headers={'Referer':'https://tv.apple.com/','Origin':'https://tv.apple.com','User-Agent':'Mozilla/5.0 AppleTVCatalog/1.0'},timeout=(15,40),allow_redirects=False);r.raise_for_status()
        if r.status_code!=200 or len(r.content)>12_000_000:raise ValueError('Invalid public page response')
        data=r.json()['data']
        if route in ('channel','room'):
            c=data['canvas'];value={'id':c['id'],'source':c['url'],'nextToken':c.get('nextToken'),'shelves':[slim_shelf(s)for s in c.get('shelves',[])]}
        elif route=='shelf':value=slim_shelf(data['shelf'])
        else:value=slim_item(data['content'])
        self.cache[key]={'checkedAt':now,'value':value};dump(self.path,self.cache);return copy.deepcopy(value)
    def canvas(self,kind,identity):
        page=self.get(kind,identity);out=copy.deepcopy(page);seen=set();token=page.get('nextToken')
        while token:
            if token in seen or len(seen)>=15:raise ValueError('Repeating or excessive page pagination')
            seen.add(token);more=self.get(kind,identity,token)
            if more['id']!=page['id']:raise ValueError('Pagination changed canvas identity')
            out['shelves'].extend(more['shelves']);token=more.get('nextToken')
        out.pop('nextToken',None);return out
    def shelf(self,shelf):
        out=copy.deepcopy(shelf);token=shelf.get('nextToken');seen=set()
        while token:
            if token in seen or len(seen)>=35:raise ValueError('Repeating or excessive shelf pagination')
            seen.add(token);more=self.get('shelf',shelf['id'],token)
            if more['id']!=shelf['id']:raise ValueError('Pagination changed shelf identity')
            out['items'].extend(more['items']);token=more.get('nextToken')
        out.pop('nextToken',None);return out
