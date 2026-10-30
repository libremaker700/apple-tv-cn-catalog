"""Optional bounded MiniMax title-candidate lookup. Only independently fetched sources verify names."""
import argparse,hashlib,json,os,re,shutil,subprocess,time,uuid
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]
JAR_SHA='3cf6cd6892e32e2b4c1c39e0f52f5248a2f5b37646fdfbb79a66b46b618414ed'
BASES={'https://agent.minimax.io':'https://agent-stream.minimax.io','https://agent.minimax.cn':'https://agent-stream.minimaxi.com'}

def credentials(path=None):
    raw=Path(path).read_text(encoding='utf-8-sig') if path else os.getenv('MINIMAX_CREDENTIALS_JSON','')
    if not raw:return None
    value=json.loads(raw);base=value.get('base','https://agent.minimax.io').rstrip('/')
    if base not in BASES or not value.get('token') or not str(value.get('user_id') or value.get('realUserID') or '').isdigit():raise ValueError('Invalid MiniMax credential shape')
    return {'base':base,'token':value['token'],'user_id':str(value.get('user_id') or value.get('realUserID')),'op_ticket':value.get('op_ticket','')}

def redact(value,cred):
    raw=json.dumps(value,ensure_ascii=False)
    for field in ('token','user_id','op_ticket'):
        if cred and cred.get(field):raw=raw.replace(str(cred[field]),'[REDACTED]')
    return json.loads(re.sub(r'eyJ[A-Za-z0-9_.-]{30,}','[REDACTED]',raw))

class Signer:
    def __init__(self):
        self.stage=ROOT/'.local/title-agent';self.stage.mkdir(parents=True,exist_ok=True);self.jar=self.stage/'json.jar'
        if not self.jar.exists():
            r=requests.get('https://repo.maven.apache.org/maven2/org/json/json/20240303/json-20240303.jar',timeout=(10,30));r.raise_for_status();self.jar.write_bytes(r.content)
        if hashlib.sha256(self.jar.read_bytes()).hexdigest()!=JAR_SHA:raise ValueError('JSON Java dependency hash mismatch')
        java_home=os.getenv('JAVA_HOME','');self.java=str(Path(java_home)/'bin/java') if java_home else shutil.which('java')
        javac=str(Path(java_home)/'bin/javac') if java_home else shutil.which('javac')
        if not self.java or not javac:raise RuntimeError('Java 17 JDK required for title signing adapter')
        sources=[ROOT/'tools/title-resolver/vendor/MinimaxMatrixClient.java',ROOT/'tools/title-resolver/SignBridge.java']
        stamp=hashlib.sha256(b''.join(p.read_bytes() for p in sources)).hexdigest();version=self.stage/'build.sha'
        if not version.exists() or version.read_text()!=stamp:
            p=subprocess.run([javac,'-encoding','UTF-8','-cp',str(self.jar),'-d',str(self.stage),*[str(s) for s in sources]],capture_output=True,timeout=40)
            if p.returncode:raise RuntimeError('Title signing bridge compilation failed')
            version.write_text(stamp)
    def sign(self,method,url,params,body,ms):
        data=json.dumps({'method':method,'url':url,'params':params,'body':body,'unix_ms':ms},ensure_ascii=False)
        p=subprocess.run([self.java,'-cp',str(self.stage)+os.pathsep+str(self.jar),'SignBridge'],input=data,capture_output=True,text=True,encoding='utf-8',timeout=15)
        if p.returncode:raise RuntimeError('Title request signing failed')
        return json.loads(p.stdout)

class AgentError(Exception):
    def __init__(self,status):self.status=status;super().__init__(status)

class MiniMaxAgent:
    def __init__(self,cred,session=None):self.cred=cred;self.session=session or requests.Session();self.signer=Signer();self.events=[]
    def request(self,method,path,body=None,stream=False):
        if not path.startswith(('/minimax-cloud/api/v1/','/v1/api/user/renewal')):raise ValueError('Unsupported title-agent path')
        ms=int(time.time()*1000);base=BASES[self.cred['base']] if stream else self.cred['base'];raw=json.dumps(body,ensure_ascii=False,separators=(',',':')) if body is not None else ''
        params={'device_platform':'web','biz_id':'3','app_id':'3001','version_code':'22201','unix':ms,'timezone_offset':'-480','client':'web','region':'cn','sys_language':'zh','lang':'zh','uuid':str(uuid.uuid4()),'device_id':str(uuid.uuid4()),'os_name':'Android','browser_name':'chrome','device_memory':'8','cpu_core_num':'8','browser_language':'zh-CN','browser_platform':'Linux armv8l','user_id':self.cred['user_id'],'screen_width':'1920','screen_height':'1080','token':self.cred['token']}
        if self.cred.get('op_ticket'):params['op_ticket']=self.cred['op_ticket']
        signed=self.signer.sign(method,base+path,params,raw,ms)
        headers={'token':self.cred['token'],'x-timestamp':str(signed['timestamp']),'x-signature':signed['signature'],'yy':signed['yy'],'Referer':self.cred['base']+'/','Origin':self.cred['base'],'User-Agent':'Mozilla/5.0','Accept':'text/event-stream' if stream else 'application/json'}
        if body is not None:headers['Content-Type']='application/json'
        try:r=self.session.request(method,signed['url'],headers=headers,data=raw.encode() if body is not None else None,timeout=(12,20),stream=stream,allow_redirects=False)
        except requests.RequestException:raise AgentError('transport_unavailable') from None
        self.events.append({'method':method,'endpoint':path.split('/session/')[0],'http_status':r.status_code})
        if r.status_code!=200:r.close();raise AgentError('HTTP_'+str(r.status_code))
        return r
    def json(self,method,path,body=None):
        with self.request(method,path,body) as r:
            try:data=r.json()
            except ValueError:raise AgentError('non_json') from None
        status=data.get('base_resp',{}).get('status_code',0) or data.get('statusInfo',{}).get('code',0)
        if status:raise AgentError('business_'+str(status))
        return data
    def agents(self):
        data=self.json('GET','/minimax-cloud/api/v1/agent');rows=data.get('agents') or data.get('data',{}).get('agents') or []
        return [str(r.get('name','')) for r in rows if re.fullmatch(r'[A-Za-z0-9_-]{1,100}',str(r.get('name','')))]
    def search(self,records):
        agents=self.agents()
        if not agents:raise AgentError('no_agent')
        created=self.json('POST','/minimax-cloud/api/v1/agent/'+agents[0]+'/session',{})
        sid=str(created.get('session_id') or created.get('data',{}).get('session_id') or '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',sid):raise AgentError('no_session')
        prompt='请实际使用 web_search/web_fetch 为以下 Apple TV 作品查询中国大陆常用中文名、豆瓣条目和中文剧情简介来源。必须核对原名、电影或电视剧、首播年份和IMDb。不要用香港台湾译名，不要自行翻译，找不到写未核实。仅输出JSON对象 {"records":[{"slug":"...","english_title":"...","chinese_title":"...","sources":["实际来源URL"],"reason":"依据"}]}。模型答案只作为待核验候选，网址会被独立重新获取。作品：'+json.dumps(records,ensure_ascii=False)
        answer='';usage={};tools=set();seen=set();started=time.monotonic()
        try:
            with self.request('POST','/minimax-cloud/api/v1/session/'+sid+'/message',{'id':sid,'content':prompt},True) as response:
                for line in response.iter_lines(chunk_size=1024):
                    if time.monotonic()-started>180:break
                    if not line.startswith(b'data:'):continue
                    try:event=json.loads(line[5:].strip())
                    except ValueError:continue
                    chunk=event.get('agent_message_chunk') or {};full=event.get('agent_message') or {}
                    if event.get('type')==6:
                        marker=(chunk.get('id') or chunk.get('message_id'),chunk.get('chunk_index'))
                        if marker[1] is None or marker not in seen:
                            if isinstance(chunk.get('msg_content'),str):answer+=chunk['msg_content']
                            seen.add(marker)
                    if event.get('type')==2 and full.get('role')=='assistant' and isinstance(full.get('msg_content'),str):answer=full['msg_content']
                    for tc in chunk.get('tool_calls',[])+full.get('tool_calls',[]):tools.add(str(tc.get('tool_name') or tc.get('name') or ''))
                    usage=chunk.get('usage') or full.get('usage') or usage
                    if len(answer)>64000:raise AgentError('answer_too_large')
                    if full.get('role')=='assistant' and full.get('finish_reason'):break
        except requests.RequestException:
            if not answer:raise AgentError('stream_unavailable') from None
        # History supplies a completed message if a transport ended between final chunks.
        history=self.json('GET','/minimax-cloud/api/v1/session/'+sid+'/message')
        def visit(value):
            nonlocal answer,usage
            if isinstance(value,list):
                for item in value:visit(item)
            elif isinstance(value,dict):
                if value.get('role')=='assistant' and isinstance(value.get('msg_content'),str) and value['msg_content']:answer=value['msg_content'];usage=value.get('usage') or usage
                for key in ('messages','data','history','agent_messages','list'):
                    if key in value:visit(value[key])
        visit(history)
        match=re.search(r'\{[\s\S]*\}',answer)
        try:parsed=json.loads(match.group()) if match else {}
        except ValueError:parsed={}
        candidates=parsed.get('records',[])
        allowed={r['slug'] for r in records};candidates=[r for r in candidates if isinstance(r,dict) and r.get('slug') in allowed]
        return redact({'status':'ok' if candidates else 'unparseable_answer','records':candidates,'usage':usage,'tools':sorted(tools),'seconds':round(time.monotonic()-started,1),'request_count':len(self.events)},self.cred)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--credentials');p.add_argument('--probe',action='store_true');a=p.parse_args()
    try:
        c=credentials(a.credentials)
        if not c:raise AgentError('missing_credentials')
        agent=MiniMaxAgent(c);print(json.dumps({'status':'ok','agent_count':len(agent.agents())},ensure_ascii=False))
    except AgentError as e:print(json.dumps({'status':e.status}));raise SystemExit(1)
    except Exception as e:print(json.dumps({'status':type(e).__name__}));raise SystemExit(1)
