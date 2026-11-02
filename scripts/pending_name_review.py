"""A bounded GitHub name review; released identities can verify AI names in VOD libraries."""
import argparse,json,re,time
from datetime import datetime,timezone
from catalog import ROOT,load,raw_json
from mainland_names import run,source_deferred
from title_lookup import dump

def candidates(root):
    main=load(root/'docs/catalog.json');home=load(root/'docs/home/home.json');seen=set();rows=[]
    hints=load(root/'data/name-search-hints.json').get('works',{})if(root/'data/name-search-hints.json').exists()else{}
    for work in main['entries']+[w for w in home['works']if not w.get('knownCatalog')]:
        if work['slug']in seen or re.search(r'[\u3400-\u9fff]',str((work.get('zh')or{}).get('title',''))):continue
        seen.add(work['slug']);n=int(work.get('artworkSeasonNumber')or work.get('seasonNumber')or 1)
        season=next((s for s in work.get('seasons',[])if s['season']==n),{})
        year=str(season.get('year')or(work.get('zh')or{}).get('_identityYear')or(work.get('officialIdentity')or{}).get('year')or work.get('year')or str(work.get('releaseDate',''))[:4])
        reason='future_release'if source_deferred(season or work)else'missing_year'if not re.fullmatch(r'(19|20)\d{2}',year)else''
        hint=hints.get(work['slug'],{});official=work.get('officialId')or(work.get('officialIdentity')or{}).get('watchUrl','').rstrip('/').split('/')[-1]
        if reason=='future_release'and hint.get('allowFutureNameReview')and hint.get('englishTitle')==work['en']and hint.get('officialId')==official and hint.get('candidateSubjectIds'):reason=''
        rows.append({'slug':work['slug'],'en':work['en'],'year':year,'season':0 if work['kind']=='movie'else n,'skip':reason})
    priority={'to-mom-and-dad-with-love':0,'home-6ippzjfc3jg0l4b8x8cslmhfa':1}
    return sorted(rows,key=lambda row:(priority.get(row['slug'],2),row['en']))

def review(root=ROOT,limit=64,slugs=None):
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
    path=root/'docs/pending-name-review.json'
    started=time.monotonic();rows=candidates(root);previous=load(path)if path.exists()else{'records':[]};old_rows={r['slug']:r for r in previous.get('records',[])}
    if path.exists():
        previous=load(path);main=load(root/'docs/catalog.json');home=load(root/'docs/home/home.json')
        works={w['slug']:w for w in main['entries']+home['works']}
        for old in previous.get('records',[]):
            work=works.get(old['slug'],{})
            if old.get('status')=='verified'and work.get('en')==old['en']and re.search(r'[\u3400-\u9fff]',str((work.get('zh')or{}).get('title',''))):rows.append(dict(old,_reused=True))
    report={'schema':1,'checkedAt':datetime.now(timezone.utc).isoformat(timespec='seconds'),'namesOnly':True,'geminiUsed':False,'sourceProbingPerformed':False,'records':[]}
    count=0
    for row in rows:
        result=dict(row)
        if row.get('_reused'):
            result.pop('_reused',None);result['reusedVerified']=True
        elif slugs and row['slug']not in slugs:
            result=dict(old_rows.get(row['slug'],dict(row,status='not_attempted_budget')),notRecheckedThisRun=True)
        elif row['skip']:result['status']=row['skip']
        elif count>=max(0,min(64,limit))or time.monotonic()-started>1050:result['status']='not_attempted_budget'
        else:
            count+=1
            try:
                batch=run(root=root,limit=1,force=True,slugs=[row['slug']],names_only=True)
                record=next((r for r in batch['records']if r['slug']==row['slug']),None)
                if record:
                    if record.get('sourceNameResolution'):report['sourceProbingPerformed']=True
                    result['result']=record
                    limited=any(e.get('status')in(0,401,403,418,429)or e.get('cooldown')for e in record.get('verificationEvents',[]))
                    reviewed=any(e.get('stage')in('subject','mobile_search')for e in record.get('subjectDiagnostics',[]))
                    result['status']='verified'if record['confidence']=='VERIFIED'else'identity_no_chinese_name'if record.get('identityVerifiedWithoutChineseName')else'network_incomplete'if limited and not reviewed else'unverified'
                else:result['status']='missing_identity'
            except Exception as error:result.update(status='error_retry',errorType=type(error).__name__)
        report['records'].append(result);report['summary']={status:sum(r['status']==status for r in report['records'])for status in sorted({r['status']for r in report['records']})}
        dump(path,report)
        print(json.dumps({'slug':row['slug'],'status':result['status']},ensure_ascii=True),flush=True)
    return save_report(root,report)

def save_report(root,report):
    report['summary']={status:sum(r['status']==status for r in report['records'])for status in sorted({r['status']for r in report['records']})}
    dump(root/'docs/pending-name-review.json',report)
    status_names={'identity_no_chinese_name':'身份已核实，暂无经片库确认的中文名','verified':'已确认中文名','network_incomplete':'网络未完成，待重试','unverified':'身份未核实','missing_identity':'身份资料不足','missing_year':'缺少年份','future_release':'尚未上线，本轮跳过','not_attempted_budget':'本轮预算未轮到','error_retry':'执行异常，待重试'}
    lines=['# 待匹配中文名复核','', '本报告复核中文名，不使用 Gemini。已上线且豆瓣身份已核实的作品，使用 YDC／Tavily 查询候选名，再查片库；同片同季且有播放条目即可按片库数量选名，已确认片名不会因线路过期被撤销。用户确认的片库名称另记来源；没有片库名称证据时保留豆瓣名称。超时不代表未收录；名称确认不等于播放器已出画面。','', '检查时间（UTC）：'+report['checkedAt'],'', '| 英文原名 | 结果 | 已核实中文名 | 年份 / 季数 |','|---|---|---|---|']
    for row in report['records']:
        cells=[row['en'],status_names[row['status']],row.get('result',{}).get('title',''),str(row['year'])+' / '+str(row['season'])]
        lines.append('| '+' | '.join(str(c).replace('|','／').replace('\n',' ')for c in cells)+' |')
    (root/'docs/pending-name-review.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    return report

def summarize(root=ROOT):
    """Refresh the report from completed evidence without issuing network requests."""
    path=root/'docs/pending-name-review.json'
    report=load(path)if path.exists()else{'records':[]}
    main=load(root/'docs/catalog.json');home=load(root/'docs/home/home.json')
    works={w['slug']:w for w in main['entries']+home['works']}
    rows={r['slug']:r for r in report['records']}
    cache=load(root/'data/mainland-name-cache.json')
    for slug,cached in cache.get('records',{}).items():
        result=cached.get('result',{});work=works.get(slug)
        if not work or not result.get('sourceNameResolution'):continue
        zh=work.get('zh')or{};chinese=bool(re.search(r'[\u3400-\u9fff]',zh.get('title','')))
        # The latest committed catalog, rather than an earlier Plex result,
        # determines whether the name is still pending.
        row=rows.get(slug)
        if row is None:
            row={'slug':slug,'en':work['en'],'year':str(zh.get('_identityYear')or work.get('year','')),'season':0 if work['kind']=='movie'else int(work.get('artworkSeasonNumber')or work.get('seasonNumber')or 1),'skip':''}
            report['records'].append(row)
        row.update(result=result,status='verified'if chinese else'identity_no_chinese_name')
        row.pop('reusedVerified',None);row.pop('notRecheckedThisRun',None)
        report['sourceProbingPerformed']=True
    report['checkedAt']=datetime.now(timezone.utc).isoformat(timespec='seconds')
    report['geminiUsed']=False
    return save_report(root,report)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=64);parser.add_argument('--slug',action='append');parser.add_argument('--summarize',action='store_true');args=parser.parse_args();value=summarize()if args.summarize else review(limit=args.limit,slugs=args.slug);print(json.dumps(value['summary'],ensure_ascii=True))
