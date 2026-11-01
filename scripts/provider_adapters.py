"""Cloud adapters corresponding to App source types. Secrets and media URLs never enter reports."""
import base64,hashlib,hmac,html,json,os,re,secrets,string,time
from urllib.parse import quote,urlsplit
import requests

class AdapterError(Exception):
    def __init__(self,reason,http=0):self.reason=reason;self.http=http;super().__init__(reason)

def provider_key(provider):
    kind=provider.get('type','cms')
    return kind+':'+(str(provider.get('url','')).rstrip('/')if kind=='cms'else provider.get('line')or kind)

def plain(value):return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',str(value or'')))).strip()
def names(value):
    if isinstance(value,list):return ','.join(plain(v.get('name')if isinstance(v,dict)else v)for v in value)
    return plain(value)

class Transport:
    def __init__(self,session,deadline):self.session=session;self.deadline=deadline
    def fetch(self,address,params=None,body=None,headers=None):
        left=self.deadline-time.monotonic()
        if left<=0:raise AdapterError('deadline')
        try:
            kwargs=dict(timeout=(min(5,left/3),min(9,left*2/3)),allow_redirects=False,headers=headers or{},stream=True)
            response=self.session.get(address,params=params,**kwargs)if body is None else self.session.post(address,data=body,**kwargs)
            try:
                if response.status_code!=200:raise AdapterError('access_limited'if response.status_code in(401,403,418,429)else'http',response.status_code)
                raw=bytearray()
                for chunk in response.iter_content(16384):
                    if time.monotonic()>=self.deadline:raise AdapterError('deadline')
                    raw.extend(chunk)
                    if len(raw)>4*1024*1024:raise AdapterError('response_too_large')
                return bytes(raw),response.headers
            finally:response.close()
        except requests.RequestException:raise AdapterError('network')from None
    def json(self,*args,**kw):
        raw,_=self.fetch(*args,**kw)
        try:return json.loads(raw)
        except(ValueError,UnicodeError):raise AdapterError('invalid_json')from None

class Cms:
    def __init__(self,provider,session,deadline):self.provider=provider;self.session=session;self.deadline=deadline
    def request(self,params):
        remaining=self.deadline-time.monotonic()
        if remaining<=0:raise AdapterError('deadline')
        response=self.session.get(self.provider['url'],params=dict(ac='detail',**params),timeout=(min(5,remaining/3),min(9,remaining*2/3)),allow_redirects=False)
        if response.status_code!=200:raise AdapterError('http',response.status_code)
        data=response.json()
        if not isinstance(data,dict)or not isinstance(data.get('list'),list):raise AdapterError('invalid_response')
        return data['list'][:30]
    def search(self,query):return self.request({'wd':query})
    def describe(self,row):
        if row.get('vod_play_url'):return row
        return next((item for item in self.request({'ids':row['vod_id']})if str(item.get('vod_id'))==str(row['vod_id'])),{})
    def playable(self,row):return row

class Ikanbot:
    ORIGIN='https://www2.ikanbot.com'
    def __init__(self,transport):self.http=transport;self.pages={}
    def page(self,path):
        raw,_=self.http.fetch(self.ORIGIN+path,headers={'Referer':self.ORIGIN+'/','User-Agent':'Libre/0.22.0 NativePlayer'})
        value=raw.decode('utf8')
        if re.search(r'captcha|人机验证|安全验证',value,re.I):raise AdapterError('access_limited')
        return value
    @staticmethod
    def field(page,key):
        for tag in re.findall(r'<input\b[^>]*>',page,re.I):
            attrs=dict((k.lower(),html.unescape(v))for k,_,v in re.findall(r'([\w-]+)\s*=\s*([\"\'])(.*?)\2',tag))
            if attrs.get('id')==key:return attrs.get('value','')
        return ''
    def search(self,query):
        page=self.page('/search?q='+quote(query));out=[];seen=set()
        for identity,label in re.findall(r'<a\b[^>]*href=[\"\']/play/(\d+)[\"\'][^>]*class=[\"\']title-text[\"\'][^>]*>(.*?)</a>',page,re.S):
            found=re.fullmatch(r'(.*?)\s+((?:19|20)\d{2})',plain(label))
            if found and identity not in seen:out.append(dict(vod_id=identity,vod_name=found[1],vod_year=found[2]));seen.add(identity)
        return out[:30]
    def describe(self,row):
        identity=str(row['vod_id'])
        if not re.fullmatch(r'\d{1,20}',identity):raise AdapterError('invalid_identity')
        page=self.page('/play/'+identity)
        if self.field(page,'current_id')!=identity:raise AdapterError('identity_changed')
        title=re.search(r'<h1\b[^>]*\sid=[\"\']video_title[\"\'][^>]*>(.*?)</h1>',page,re.S)
        fields=[plain(value)for value in re.findall(r'<h3\b[^>]*\sclass=[\"\'][^\"\']*\bmeta\b[^\"\']*[\"\'][^>]*>(.*?)</h3>',page,re.S)]
        years=[i for i in range(len(fields)-1)if re.fullmatch(r'(19|20)\d{2}',fields[i])and not re.fullmatch(r'(19|20)\d{2}',fields[i+1])]
        kind={'1':'电影','2':'电视剧'}.get(self.field(page,'mtype'))
        if not title or len(years)!=1 or not kind:raise AdapterError('identity_pending')
        i=years[0];people=fields[i+2].split('/',1)if len(fields)>i+2 else[]
        self.pages[identity]=page
        return dict(row,vod_name=plain(title[1]),vod_year=fields[i],type_name=kind,vod_director=people[0].strip()if len(people)==2 else'',vod_actor=people[1].strip()if len(people)==2 else'')
    def playable(self,row):
        identity=str(row['vod_id']);page=self.pages[identity];remaining=self.field(page,'e_token');token=''
        for digit in identity[-4:]:
            offset=int(digit)%3+1
            if len(remaining)<offset+8:raise AdapterError('protocol_changed')
            token+=remaining[offset:offset+8];remaining=remaining[offset+8:]
        data=self.http.json(self.ORIGIN+'/api/getResN',params={'videoId':identity,'mtype':self.field(page,'mtype'),'token':token},headers={'Referer':self.ORIGIN+'/','User-Agent':'Libre/0.22.0 NativePlayer'})
        if data.get('state')!=1 or not isinstance((data.get('data')or{}).get('list'),list):raise AdapterError('resource_unavailable')
        flags=[];urls=[]
        for record in data['data']['list'][:10]:
            try:groups=json.loads(record.get('resData','[]'))
            except(ValueError,TypeError):raise AdapterError('invalid_response')from None
            for group in groups[:10]:
                if re.fullmatch(r'[\w-]{1,50}',group.get('flag','')):flags.append(group['flag']);urls.append(str(group.get('url','')))
        return dict(row,vod_play_from='$$$'.join(flags),vod_play_url='$$$'.join(urls))

def config(name):
    try:value=json.loads(os.environ.get(name,''))
    except(ValueError,TypeError):raise AdapterError('needs_configuration')from None
    if not isinstance(value,dict):raise AdapterError('needs_configuration')
    return value

class Shared:
    ROUTES=[('https://vlogic.'+host,'https://vcache.'+host)for host in('qvfic.com','zwtlzch.cn','ybsdkl.cn','shkjbd.com','mjrlin.cn','srnffc.cn')]
    def __init__(self,transport,settings):
        self.http=transport;self.settings=settings;self.details={}
        if not(settings.get('guest')or{}).get('token'):raise AdapterError('needs_configuration')
        if any(not isinstance(settings.get(key),str)or not settings[key]for key in('appId','apiVer','appVersion','package','signKeyHex','responseKeyHex','responseIvHex'))or any(key not in settings['guest']for key in('id','channelId','level')):raise AdapterError('invalid_configuration')
    def call(self,path,business,cache=False):
        from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
        from cryptography.hazmat.primitives import padding
        s=self.settings;guest=s['guest'];params=dict(business,os='android',appId=s['appId'],userChannel=guest['channelId'],userLevel=str(guest['level']));failure=AdapterError('network')
        for routes in self.ROUTES:
            stamp=str(int(time.time()*1000));canonical='get|'+path+'|'+'&'.join(k+'='+str(params[k])for k in sorted(params))+'|'+stamp+'|appId='+s['appId']+'&st=2&userId='+guest['id']+'|'
            signature=hmac.new(bytes.fromhex(s['signKeyHex']),canonical.encode(),hashlib.sha1).hexdigest()
            headers={k:str(s[k])for k in('appId','apiVer','appVersion','package')};headers.update({'os':'android','channelId':guest['channelId'],'st':'2','x-d-video':'1','userId':guest['id'],'X-Token':guest['token'],'ts':stamp,'sign':signature,'Accept':'application/json','User-Agent':'LibreTV-Ncat-Adapter/0.1'})
            if cache:headers['X-CDN']='1'
            try:
                raw,response_headers=self.http.fetch(routes[1 if cache else 0]+path,params=params,headers=headers)
                if response_headers.get('encrypted')=='1':
                    decryptor=Cipher(algorithms.AES(bytes.fromhex(s['responseKeyHex'])),modes.CBC(bytes.fromhex(s['responseIvHex']))).decryptor();padded=decryptor.update(raw)+decryptor.finalize();unpad=padding.PKCS7(128).unpadder();raw=unpad.update(padded)+unpad.finalize()
                value=json.loads(raw)
                if value.get('code')!=200:raise AdapterError('session_or_api_rejected')
                return value.get('data')
            except AdapterError as error:
                failure=error
                if error.reason in('deadline','session_or_api_rejected'):break
        raise failure
    def search(self,query):
        result=self.call('/vod/search/query',{'channelId':'','k':query,'next':''})
        if not isinstance(result,dict)or not isinstance(result.get('items'),list):raise AdapterError('invalid_response')
        out=[]
        for row in result['items'][:30]:
            year=row.get('year')or'';year=year.get('name','')if isinstance(year,dict)else str(year)
            out.append(dict(vod_id=str(row.get('id','')),vod_name=plain(row.get('title')),vod_year=year,type_name={1:'电影',2:'电视剧'}.get(row.get('channelId'),''),vod_actor=names(row.get('actors')),vod_director=names(row.get('directors'))))
        return out
    def describe(self,row):
        identity=str(row['vod_id'])
        if not re.fullmatch(r'\d{1,24}',identity):raise AdapterError('invalid_identity')
        body=self.call('/v2/vod/detail.capi',{'vodId':identity},True)
        if not isinstance(body,dict)or str(body.get('id',identity))!=identity:raise AdapterError('identity_changed')
        self.details[identity]=body;year=body.get('year')or{}
        return dict(row,vod_name=plain(body.get('title')),vod_year=str(year.get('name','')if isinstance(year,dict)else year),vod_actor=names(body.get('actors')),vod_director=names(body.get('directors')))
    def playable(self,row):
        flags=[];groups=[]
        for source in self.details[str(row['vod_id'])].get('playSources',[])[:20]:
            if source.get('needLogin',1)!=0 or(source.get('needAccelerate',1)!=0 and source.get('siteId')not in('dujia1','dujia2')):continue
            episodes=source.get('list')
            if not episodes:episodes=self.call('/v2/vod/episodes.capi',{'vodId':str(row['vod_id']),'siteId':str(source.get('siteId','')),'episodeVodId':str(source.get('episodeVodId',''))},True)
            urls=[]
            for ep in (episodes or[])[:500]:
                candidates=[v.get('url','')for v in ep.get('playUrls',[])if isinstance(v,dict)]+[ep.get('m3u8Url','')]
                address=next((v for v in candidates if isinstance(v,str)and re.match(r'^https?://',v)and not re.search(r'[\s<>\"\'\\#]',v)),None)
                if address:urls.append(plain(ep.get('title'))+'$'+address)
            if urls:flags.append(str(source.get('siteId','shared')));groups.append('#'.join(urls))
        return dict(row,vod_play_from='$$$'.join(flags),vod_play_url='$$$'.join(groups))

def integer(raw,offset):
    value=0
    for shift in range(0,63,7):
        if offset>=len(raw):raise AdapterError('invalid_protobuf')
        byte=raw[offset];offset+=1;value|=(byte&127)<<shift
        if byte<128:return value,offset
    raise AdapterError('invalid_protobuf')
def varint(value):
    out=bytearray()
    while True:
        out.append((value&127)|(128 if value>127 else 0));value>>=7
        if not value:return bytes(out)
def field(number,value):
    if isinstance(value,int):return varint(number*8)+varint(value)
    raw=str(value).encode();return varint(number*8+2)+varint(len(raw))+raw
class Fields:
    def __init__(self,raw=b''):
        self.values={};offset=0
        while offset<len(raw):
            tag,offset=integer(raw,offset);number,wire=tag>>3,tag&7
            if number<1:raise AdapterError('invalid_protobuf')
            if wire==0:value,offset=integer(raw,offset)
            else:
                if wire==2:length,offset=integer(raw,offset)
                elif wire in(1,5):length=8 if wire==1 else 4
                else:raise AdapterError('invalid_protobuf')
                if length>len(raw)-offset:raise AdapterError('invalid_protobuf')
                value=raw[offset:offset+length];offset+=length
            self.values.setdefault(number,[]).append(value)
    def raw(self,key):return next(iter(self.values.get(key,[])),None)
    def text(self,key):value=self.raw(key);return value.decode('utf8')if isinstance(value,bytes)else''
    def number(self,key):value=self.raw(key);return value if isinstance(value,int)else 0
    def messages(self,key):return [Fields(value)for value in self.values.get(key,[])if isinstance(value,bytes)]

class Juzi:
    ORIGIN='https://juziapp.hzhcbkj.cn'
    def __init__(self,transport,settings,line):
        self.http=transport;self.settings=settings;self.line=line;self.server_key='';self.details={}
        if settings.get('origin')!=self.ORIGIN or line not in('qsvip','bfzym3u8'):raise AdapterError('needs_configuration')
        if any(not settings.get(key)for key in('publicKey','signingSecret','bodyKey','bootstrapUrls','packageName','versionCode','versionName','fakePosition')):raise AdapterError('invalid_configuration')
    @staticmethod
    def nonce(length):return ''.join(secrets.SystemRandom().sample(string.ascii_letters+string.digits,length-1))+'='
    @staticmethod
    def aes(key,value):
        from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
        from cryptography.hazmat.primitives import padding
        pad=padding.PKCS7(128).padder();raw=pad.update(value.encode())+pad.finalize();encrypt=Cipher(algorithms.AES(key.encode()),modes.ECB()).encryptor();return base64.b64encode(encrypt.update(raw)+encrypt.finalize()).decode()
    @staticmethod
    def rsa(key,value):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        public=serialization.load_der_public_key(base64.b64decode(key));return base64.b64encode(public.encrypt(value.encode(),padding.PKCS1v15())).decode()
    def params(self,key=None):
        s=self.settings;params={'plat':'android','v':'1','vApp':str(s['versionCode']),'vName':s['versionName'],'pkg':s['packageName'],'appName':quote('橘汁',safe="~!*'()")}
        if key:
            params={k:quote(v,safe="~!*'()")for k,v in params.items()};stamp=str(int(time.time()*1000));nonce=self.nonce(16);signature=self.aes(s['signingSecret'],stamp+nonce)
            params.update(timestamp=int(stamp),random_str=nonce,sig=self.rsa(key,stamp+nonce+str(s['versionCode'])),sig2=signature[:8],sig3=signature[8:])
        return params
    def exchange(self,path,body,params):
        raw,_=self.http.fetch(self.ORIGIN+path,body=body,headers={'Content-Type':'application/x-protobuf','Accept':'application/x-protobuf','User-Agent':'Mozilla/5.0','publicParams':json.dumps(params,ensure_ascii=False,separators=(',',':'))});response=Fields(raw)
        if response.number(1)!=200:raise AdapterError('protocol_rejected')
        return Fields(response.raw(3)or b'')
    def key(self):
        if self.server_key:return self.server_key
        s=self.settings;bootstrap=s['bootstrapUrls'][0]
        if urlsplit(bootstrap).scheme!='https':raise AdapterError('invalid_configuration')
        discovery=self.http.json(bootstrap)
        if not discovery.get('enabled')or str(discovery.get('domain','')).rstrip('/')!=self.ORIGIN:raise AdapterError('origin_changed')
        stamp=int(time.time()*1000);nonce=self.nonce(16);body=field(1,stamp)+field(2,self.rsa(s['publicKey'],str(stamp)+nonce))+field(3,self.nonce(16))+field(4,nonce)+field(5,self.nonce(16));data=self.exchange('/api/v5/find/app/zone',body,self.params())
        self.server_key=''.join(data.text(i)for i in range(1,6)if i!=s['fakePosition'])
        if not 100<len(self.server_key)<2048:raise AdapterError('protocol_changed')
        return self.server_key
    def request(self,path,query):
        key=self.key();stamp=int(time.time()*1000);nonce=self.nonce(8);encrypted=nonce+self.aes(self.settings['bodyKey'],query+str(stamp))
        return self.exchange(path,field(1,encrypted[:20])+field(2,encrypted[20:])+field(3,self.nonce(20))+field(4,stamp)+field(5,nonce),self.params(key))
    def search(self,query):
        if len(query)>200 or re.search(r'[&=\r\n]',query):raise AdapterError('invalid_query')
        data=self.request('/api/proto/v5/drama/search','searchKeys='+query+'&page=1&pagesize=100');out=[]
        for row in data.messages(1)[:30]:
            kind=row.text(8)or{20:'电影',21:'电视剧',22:'综艺',23:'动漫'}.get(row.number(9),'')
            if row.number(3)>0 and row.text(5):out.append(dict(vod_id=str(row.number(3)),vod_name=row.text(5),vod_year=str(row.number(14)),type_name=kind,vod_director=row.text(7),vod_actor=row.text(12)))
        return out
    def describe(self,row):
        identity=str(row['vod_id'])
        if not re.fullmatch(r'\d{1,16}',identity):raise AdapterError('invalid_identity')
        data=self.request('/api/proto/v5/drama/getDetail','id='+identity)
        if not data.text(9)and isinstance(data.raw(1),bytes):data=Fields(data.raw(1))
        if str(data.number(4))!=identity or not data.text(9):raise AdapterError('identity_changed')
        self.details[identity]=data;kind=data.text(14)or{20:'电影',21:'电视剧',22:'综艺',23:'动漫'}.get(data.number(15),'')
        return dict(row,vod_name=data.text(9),vod_year=str(data.number(18)),type_name=kind,vod_director=data.text(12),vod_actor=data.text(25))
    def playable(self,row):
        data=self.details[str(row['vod_id'])];candidates=[ep for ep in data.messages(29)if ep.text(9)==self.line and ep.text(4)];groups={ep.number(12)for ep in candidates}
        if len(groups)>1:raise AdapterError('episode_groups_ambiguous')
        for ep in candidates:
            label=ep.text(3)or ep.text(2)
            if re.search('预告|花絮|彩蛋|特辑|幕后',label):continue
            value=self.request('/api/proto/v5/videoUsableUrl','vodPlayFrom='+self.line+'&playUrl='+quote(ep.text(4),safe="~!*'()")).text(1)
            if not re.match(r'^https?://',value)or re.search(r'[\s<>\"\'\\]',value):raise AdapterError('media_unavailable')
            return dict(row,vod_play_from=self.line,vod_play_url=(plain(label)or'正片')+'$'+value)
        return dict(row,vod_play_from=self.line,vod_play_url='')

def create(provider,session,deadline):
    kind=provider.get('type','cms')
    if kind=='cms':return Cms(provider,session,deadline)
    transport=Transport(session,deadline)
    if kind=='ikanbot':return Ikanbot(transport)
    if kind=='shared':return Shared(transport,config('APPLETV_SHARED_SESSION_JSON'))
    if kind=='juzi':return Juzi(transport,config('APPLETV_JUZI_PROTOCOL_JSON'),provider.get('line'))
    raise AdapterError('unsupported_adapter')
