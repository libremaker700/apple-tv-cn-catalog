"""A bounded manual GitHub review of missing Chinese names, without VOD probing."""
import argparse,json,re,time
from datetime import datetime,timezone
from catalog import ROOT,load,raw_json
from mainland_names import run,source_deferred
from title_lookup import dump

def candidates(root):
    main=load(root/'docs/catalog.json');home=load(root/'docs/home/home.json');seen=set();rows=[]
    for work in main['entries']+[w for w in home['works']if not w.get('knownCatalog')]:
        if work['slug']in seen or re.search(r'[\u3400-\u9fff]',str((work.get('zh')or{}).get('title',''))):continue
        seen.add(work['slug']);n=int(work.get('artworkSeasonNumber')or work.get('seasonNumber')or 1)
        season=next((s for s in work.get('seasons',[])if s['season']==n),{})
        year=str(season.get('year')or(work.get('zh')or{}).get('_identityYear')or(work.get('officialIdentity')or{}).get('year')or work.get('year')or str(work.get('releaseDate',''))[:4])
        reason='future_release'if source_deferred(season or work)else'missing_year'if not re.fullmatch(r'(19|20)\d{2}',year)else''
        rows.append({'slug':work['slug'],'en':work['en'],'year':year,'season':0 if work['kind']=='movie'else n,'skip':reason})
    priority={'to-mom-and-dad-with-love':0,'home-6ippzjfc3jg0l4b8x8cslmhfa':1}
    return sorted(rows,key=lambda row:(priority.get(row['slug'],2),row['en']))

def review(root=ROOT,limit=64):
    # A manual transport recheck can retry old connection errors. Do not clear
    # HTTP access-limit/denial cooldowns (401/403/418/429).
    transport=root/'data/source-cache.json'
    if transport.exists():
        cache=load(transport)
        for value in cache.get('hosts',{}).values():
            if value.get('status')==0:value['retry_at']=0
        for value in cache.get('pages',{}).values():
            if value.get('status')==0:value['expires_at']=0
        dump(transport,cache)
    started=time.monotonic();rows=candidates(root);report={'schema':1,'checkedAt':datetime.now(timezone.utc).isoformat(timespec='seconds'),'namesOnly':True,'geminiUsed':False,'sourceProbingPerformed':False,'records':[]}
    path=root/'docs/pending-name-review.json'
    count=0
    for row in rows:
        result=dict(row)
        if row['skip']:result['status']=row['skip']
        elif count>=max(0,min(64,limit))or time.monotonic()-started>1050:result['status']='not_attempted_budget'
        else:
            count+=1
            try:
                batch=run(root=root,limit=1,force=True,slugs=[row['slug']],names_only=True)
                record=next((r for r in batch['records']if r['slug']==row['slug']),None)
                if record:
                    result['result']=record
                    limited=any(e.get('status')in(0,401,403,418,429)or e.get('cooldown')for e in record.get('verificationEvents',[]))
                    result['status']='verified'if record['confidence']=='VERIFIED'else'network_incomplete'if limited else'unverified'
                else:result['status']='missing_identity'
            except Exception as error:result.update(status='error_retry',errorType=type(error).__name__)
        report['records'].append(result);report['summary']={status:sum(r['status']==status for r in report['records'])for status in sorted({r['status']for r in report['records']})}
        dump(path,report)
        print(json.dumps({'slug':row['slug'],'status':result['status']},ensure_ascii=True),flush=True)
    status_names={'verified':'已确认中文名','network_incomplete':'网络未完成，待重试','unverified':'身份未核实','missing_identity':'身份资料不足','missing_year':'缺少年份','future_release':'尚未上线，本轮跳过','not_attempted_budget':'本轮预算未轮到','error_retry':'执行异常，待重试'}
    lines=['# 待匹配中文名复核','', '本报告仅复核中文名，不查播放源，不使用 Gemini。搜索提示不能直接成为中文名；通过作品身份核验后才发布。','', '检查时间（UTC）：'+report['checkedAt'],'', '| 英文原名 | 结果 | 已核实中文名 | 年份 / 季数 |','|---|---|---|---|']
    for row in report['records']:
        cells=[row['en'],status_names[row['status']],row.get('result',{}).get('title',''),str(row['year'])+' / '+str(row['season'])]
        lines.append('| '+' | '.join(str(c).replace('|','／').replace('\n',' ')for c in cells)+' |')
    (root/'docs/pending-name-review.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=64);args=parser.parse_args();value=review(limit=args.limit);print(json.dumps(value['summary'],ensure_ascii=True))
