"""Read the public US page API advertised by Apple's own bootstrap configuration.

Only public display metadata is retained. Playback assets, sessions and account fields are discarded.
"""
import json,re,time,copy
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
import requests
from title_lookup import read,dump
from home_sources import CHANNEL

def slim_item(x):
    out={k:x[k] for k in ('id','type','title','url','releaseDate','description','heroDescription','genres','flavorType','shortNote') if k in x}
    out['images']={k:{f:v[f] for f in ('url','width','height') if f in v} for k,v in x.get('images',{}).items() if isinstance(v,dict)}
    return out

def slim_shelf(s, channels=None):
    items=[slim_item(i) for i in s.get('items',[])]
    if s.get('displayType')=='epicShowcase':
        for item,original in zip(items,s['items']):
            item['serviceLogo']=original.get('channelId')=='tvs.sbd.4000' and 'tvs.sbd.4000' in (channels or {})
    return {**{k:s[k] for k in ('id','displayType','url','nextToken') if k in s},'header':{k:v for k,v in (s.get('header')or{}).items() if k in ('title','url','shortNote','supportsSeeAllView')},'items':items}

def editorial_context(shelf):
    url=urlsplit(shelf.get('url',''))
    if url.scheme!='https' or url.netloc!='tv.apple.com' or not url.path.startswith('/us/collection/') or url.path.rsplit('/',1)[-1]!=shelf['id']:
        return {}
    query=parse_qs(url.query)
    context={}
    for key,prefix in [('ctx_cvs','edt.cvs.'),('ctx_shelf','edt.shelf.')]:
        value=query.get(key,[])
        if len(value)!=1 or not re.fullmatch(re.escape(prefix)+r'[a-zA-Z0-9-]{1,100}',value[0]):
            return {}
        context[key]=value[0]
    return context

class Pages:
    def __init__(self,root,html):
        match=re.search(r'<script[^>]*id=["\']serialized-server-data["\'][^>]*>(.*?)</script>',html,re.S)
        blocks=json.loads(match[1])['data'];props=next(b['data']['configuration']['applicationProps'] for b in blocks if 'configuration' in b.get('data',{}))
        self.routes=props['routes'];self.params=props['requiredParamsMap']['Default'];assert self.params['sf']=='143441' and self.params['locale']=='en-US'
        self.session=requests.Session();self.path=root/'data/official-pages-cache.json';self.cache=read(self.path,{});self.requests=0
    def get(self,route,identity,token=None,context=None):
        assert re.fullmatch(r'[a-zA-Z0-9.\-]{1,150}',identity)
        params=dict(self.params)
        if token is not None:
            if not re.fullmatch(r'[a-zA-Z0-9:_\-]{1,100}',str(token)):raise ValueError('Invalid pagination token')
            params['nextToken']=token
        params.update(context or {})
        key=route+':'+identity+':'+str(token or '')+(':'+context['ctx_shelf'] if context else '');old=self.cache.get(key);now=int(time.time())
        if old and old.get('metadataVersion')==2 and route not in ('channel','room','shelf') and now-old['checkedAt']<6*3600:return slim_item(old['value'])
        name,kind={'channel':('getCanvasBinding','channels'),'room':('getCanvasBinding','rooms'),'shelf':('getCollectionById',None),'movie':('getMovieDetailById',None),'series':('getShowDetailById',None)}[route]
        url=self.routes[name]['url']
        for k,v in {'canvasType':kind,'entityId':identity,'collectionId':identity,'movieId':identity,'showId':identity}.items():url=url.replace('{'+k+'}',v or '')
        parts=urlsplit(url)
        if parts.scheme!='https' or parts.hostname!='uts-api.itunes.apple.com' or not parts.path.startswith('/uts/v3/'):raise ValueError('Invalid public page route')
        self.requests+=1;r=self.session.get(url,params=params,headers={'Referer':'https://tv.apple.com/','Origin':'https://tv.apple.com','User-Agent':'Mozilla/5.0 AppleTVCatalog/1.0'},timeout=(15,40),allow_redirects=False);r.raise_for_status()
        if r.status_code!=200 or len(r.content)>12_000_000:raise ValueError('Invalid public page response')
        data=r.json()['data']
        if route in ('channel','room'):
            c=data['canvas']
            if not isinstance(c.get('shelves'),list):raise ValueError('Invalid official canvas shelves')
            value={'id':c['id'],'source':c['url'],'nextToken':c.get('nextToken'),'shelves':[slim_shelf(s,data.get('channels'))for s in c['shelves']]}
        elif route=='shelf':
            shelf=data['shelf']
            if not isinstance(shelf.get('items'),list):raise ValueError('Invalid official shelf items')
            # The website omits the provider badge on shelf continuation cards.
            value=slim_shelf(shelf)
        else:value=slim_item(data['content'])
        self.cache[key]={'checkedAt':now,'metadataVersion':2,'value':value};dump(self.path,self.cache);return copy.deepcopy(value)
    def canvas(self,kind,identity):
        page=self.get(kind,identity);out=copy.deepcopy(page);seen=set();token=page.get('nextToken')
        while token:
            if token in seen or len(seen)>=15:raise ValueError('Repeating or excessive page pagination')
            seen.add(token);more=self.get(kind,identity,token)
            if more['id']!=page['id'] or not more['shelves']:raise ValueError('Invalid official canvas page')
            out['shelves'].extend(more['shelves']);token=more.get('nextToken')
        out.pop('nextToken',None);return out
    def shelf(self,shelf):
        out=copy.deepcopy(shelf);token=shelf.get('nextToken');seen=set()
        epic=shelf.get('displayType')=='epicShowcase'
        context=editorial_context(shelf) if epic and token else {}
        while token:
            if token in seen or len(seen)>=35:raise ValueError('Repeating or excessive shelf pagination')
            seen.add(token)
            more=self.get('shelf',shelf['id'],token,context=context) if context else self.get('shelf',shelf['id'],token)
            if more['id']!=shelf['id'] or not more['items']:raise ValueError('Invalid official shelf page')
            if epic and more.get('displayType')!='epicShowcase':raise ValueError('Official editorial shelf returned regular posters')
            out['items'].extend(more['items']);token=more.get('nextToken')
        out.pop('nextToken',None);return out
