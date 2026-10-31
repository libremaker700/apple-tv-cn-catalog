"""One public-US synopsis translation per work/source hash, shared by every App surface."""
import copy,json,os,re,time,hashlib,unicodedata,html
from pathlib import Path
from urllib.parse import urlsplit
from title_lookup import read,dump
from home_copy import Translator,digest,valid_zh as short_valid_zh,clean
def valid_zh(text):return short_valid_zh(text,1800)
VERSION='work-summary-zh-cn-v1'
def key(identity,text):return digest([VERSION,identity,clean(text)])
def norm(s):return re.sub(r"[^a-z0-9]","",unicodedata.normalize('NFKD',s).lower())
def source_id(e):return e.get('officialId')or(urlsplit(e.get('officialIdentity',{}).get('watchUrl','')).path.rstrip('/').split('/')[-1])or('pr:'+e['slug']if e.get('officialUrl')=='https://www.apple.com/tv-pr/originals/'+e.get('slug','')+'/'else'')
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
        if identity:wanted[identity]={'officialId':identity,'en':e['en'],'kind':e['kind'],'watchUrl':e.get('officialIdentity',{}).get('watchUrl')or e['officialUrl'],'zh':e.get('zh')}
    for w in home['works']:wanted[w['officialId']]=dict(w,zh=w.get('zh')or wanted.get(w['officialId'],{}).get('zh'))
    report={'works':len(wanted),'translated':0,'cacheHits':0,'existingChinese':0,'missingOriginal':0,'sourceErrors':0,'apiCalls':0,'usage':[],'errors':[]};pending=[];source={}
    # Fetch only display metadata through Apple's US API; identity/type are checked before use.
    for identity,w in wanted.items():
        try:
            if identity.startswith('pr:'):
                originals=read(root/'data/work-original-cache.json',{});old=originals.get(identity,{})
                if now-old.get('checkedAt',0)<6*3600:detail=old['value']
                else:
                    from catalog import get
                    page=get(w['watchUrl']).content.decode('utf-8');match=re.search(r'<div[^>]+id="description-copy"[^>]*>(.*?)</div>',page,re.S)
                    text=clean(html.unescape(re.sub('<[^>]+>',' ',match[1])))if match else''
                    detail={'id':identity,'type':'Movie'if w['kind']=='movie'else'Show','title':w['en'],'description':text};originals[identity]={'checkedAt':now,'value':detail};dump(root/'data/work-original-cache.json',originals)
            else:detail=api.get(w['kind'],identity)
            if detail.get('id')!=identity or detail.get('type')!=('Movie'if w['kind']=='movie'else'Show'):raise ValueError('identity')
            text=clean(detail.get('description')or detail.get('heroDescription')or w.get('summaryEn',''))
            if not text or len(text)>1800:report['missingOriginal']+=1;continue
            k=key(identity,text);source[identity]=(w,text,k)
            if valid_zh(records.get(k,{}).get('text')):report['cacheHits']+=1
            elif (w.get('zh')or{}).get('summary_status')!='translated_official' and valid_zh((w.get('zh')or{}).get('summary')):
                records[k]={'text':w['zh']['summary'],'method':'existing_chinese'};report['existingChinese']+=1
            elif now>=records.get(k,{}).get('nextRetry',0):pending.append({'id':identity,'text':text})
        except Exception as error:report['sourceErrors']+=1;report['errors'].append({'id':identity,'stage':'source','error':type(error).__name__})
    for offset in range(0,min(limit,len(pending)),4):
        batch=pending[offset:offset+4]
        try:
            result=translator.translate(batch);report['apiCalls']+=1;report['usage'].append(translator.usage)
            for r in batch:records[source[r['id']][2]]={'text':result[r['id']],'method':'machine','model':translator.model};report['translated']+=1
        except Exception as error:
            report['errors'].append({'stage':'translation','error':type(error).__name__,'http':translator.http})
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
    translator=Translator(os.getenv('GEMINI_API_KEY',''),os.getenv('HOME_COPY_MODEL')or None,max_length=1800)
    report=run(ROOT,api,translator,now)
    from genre_translation import apply as apply_genres
    main=load(ROOT/'docs/catalog.json');genre_home=load(ROOT/'docs/home/home.json');report['genres']=apply_genres(main,genre_home,ROOT,translator)
    (ROOT/'docs/catalog.json').write_bytes(raw_json(main));(ROOT/'docs/home/home.json').write_bytes(raw_json(genre_home))
    folder=ROOT/'docs';m=load(folder/'version.json');publish(load(folder/'catalog.json'),m.get('checked_at'),'shared-official-summary-translation')
    home=apply_home(load(folder/'home/home.json'),ROOT);from reviewed_names import apply as apply_names;home=apply_names(home,ROOT,home=True);validate(home);m=load(folder/'home/version.json');blob=raw_json(home);sha=hashlib.sha256(blob).hexdigest()
    path='releases/'+sha+'/home.json';(folder/'home'/path).parent.mkdir(parents=True,exist_ok=True);(folder/'home'/path).write_bytes(blob);m.update(path=path,version=sha,checkedAt=now);(folder/'home/home.json').write_bytes(blob);(folder/'home/version.json').write_bytes(raw_json(m));validate_publication();print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
