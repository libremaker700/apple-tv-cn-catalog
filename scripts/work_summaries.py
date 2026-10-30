"""One public-US synopsis translation per work/source hash, shared by every App surface."""
import copy,json,os,re,time,hashlib,unicodedata
from pathlib import Path
from title_lookup import read,dump
from home_copy import Translator,digest,valid_zh,clean
VERSION='work-summary-zh-cn-v1'
def key(identity,text):return digest([VERSION,identity,clean(text)])
def norm(s):return re.sub(r"[^a-z0-9]","",unicodedata.normalize('NFKD',s).lower())
def source_id(e):return e.get('officialId')or(e.get('officialIdentity',{}).get('watchUrl','').split('/')[-1])
def attach(e,record):
    if not record or not valid_zh(record.get('text')):return
    zh=e.setdefault('zh',{}) or {};e['zh']=zh
    zh.update(metadataPolicy='mainland-v1',summary=record['text'],summary_status='translated_official',summary_sources=[{'type':'apple_us_translation','url':record['source']}],summary_source_hash=record['hash'],summary_original=record['original'])
    if not zh.get('watchUrl'):zh['watchUrl']=record['source']
def apply_main(value,root):
    out=copy.deepcopy(value);records=read(root/'data/work-summary-cache.json',{}).get('works',{})
    for e in out['entries']:attach(e,records.get(source_id(e)))
    return out
def apply_home(value,root):
    out=copy.deepcopy(value);records=read(root/'data/work-summary-cache.json',{}).get('works',{})
    for w in out.get('works',[]):attach(w,records.get(w['officialId']))
    return out

def run(root,api,translator,now,limit=400):
    main=read(root/'docs/catalog.json',{});home=read(root/'docs/home/home.json',{})
    cache=read(root/'data/work-summary-cache.json',{'schema':1,'records':{},'works':{}});records=cache['records'];works=cache['works'];wanted={}
    for e in main['entries']:
        identity=source_id(e)
        if identity.startswith('umc.cmc.'):wanted[identity]={'officialId':identity,'en':e['en'],'kind':e['kind'],'watchUrl':e['officialIdentity']['watchUrl'],'zh':e.get('zh')}
    for w in home['works']:wanted[w['officialId']]=dict(w,zh=w.get('zh')or wanted.get(w['officialId'],{}).get('zh'))
    report={'works':len(wanted),'translated':0,'cacheHits':0,'existingChinese':0,'missingOriginal':0,'sourceErrors':0,'apiCalls':0,'usage':[]};pending=[];source={}
    # Fetch only display metadata through Apple's US API; identity/type are checked before use.
    for identity,w in wanted.items():
        try:
            detail=api.get(w['kind'],identity)
            if detail.get('id')!=identity or detail.get('type')!=('Movie'if w['kind']=='movie'else'Show')or norm(detail.get('title',''))!=norm(w['en']):raise ValueError('identity')
            text=clean(detail.get('description')or detail.get('heroDescription')or w.get('summaryEn',''))
            if not text or len(text)>1800:report['missingOriginal']+=1;continue
            k=key(identity,text);source[identity]=(w,text,k)
            if valid_zh(records.get(k,{}).get('text')):report['cacheHits']+=1
            elif (w.get('zh')or{}).get('summary_status')!='translated_official' and valid_zh((w.get('zh')or{}).get('summary')):
                records[k]={'text':w['zh']['summary'],'method':'existing_chinese'};report['existingChinese']+=1
            elif now>=records.get(k,{}).get('nextRetry',0):pending.append({'id':identity,'text':text})
        except Exception:report['sourceErrors']+=1
    for offset in range(0,min(limit,len(pending)),8):
        batch=pending[offset:offset+8]
        try:
            result=translator.translate(batch);report['apiCalls']+=1;report['usage'].append(translator.usage)
            for r in batch:records[source[r['id']][2]]={'text':result[r['id']],'method':'machine','model':translator.model};report['translated']+=1
        except Exception:
            report['apiCalls']+=1
            for r in batch:records[source[r['id']][2]]={'nextRetry':now+6*3600}
        dump(root/'data/work-summary-cache.json',cache)
    for identity,(w,text,k)in source.items():
        record=records.get(k,{})
        if valid_zh(record.get('text')):works[identity]=dict(record,original=text,hash=k,source=w['watchUrl'])
    report['ready']=len(works);report['pending']=sum(i not in works for i in wanted);dump(root/'data/work-summary-cache.json',cache);dump(root/'logs/work-summaries.json',report)
    return report

def main():
    from catalog import ROOT,load,publish,raw_json
    from home_sync import fetch,validate,validate_publication
    from home_sources import CHANNEL
    from official_pages import Pages
    now=int(time.time());api=Pages(ROOT,fetch(CHANNEL).decode('utf-8'))
    report=run(ROOT,api,Translator(os.getenv('GEMINI_API_KEY',''),os.getenv('HOME_COPY_MODEL')or None),now)
    folder=ROOT/'docs';m=load(folder/'version.json');publish(load(folder/'catalog.json'),m.get('checked_at'),'shared-official-summary-translation')
    home=apply_home(load(folder/'home/home.json'),ROOT);validate(home);m=load(folder/'home/version.json');blob=raw_json(home);sha=hashlib.sha256(blob).hexdigest()
    path='releases/'+sha+'/home.json';(folder/'home'/path).parent.mkdir(parents=True,exist_ok=True);(folder/'home'/path).write_bytes(blob);m.update(path=path,version=sha,checkedAt=now);(folder/'home/home.json').write_bytes(blob);(folder/'home/version.json').write_bytes(raw_json(m));validate_publication();print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
