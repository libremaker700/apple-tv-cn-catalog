"""Audit user-supplied subject IDs as candidates, never as approved display titles."""
import argparse,json,re
from datetime import datetime,timezone
from catalog import ROOT,load
from title_lookup import dump
from public_sources import PublicPages
from douban_mobile import subject_season,mainland_name
def run(root=ROOT,collect=True):
    path=root/'docs/douban-candidate-review.json'
    old=load(path)if path.exists()else{'subjects':{}}
    subjects=old.get('subjects',{})
    source=load(root/'data/douban-candidate-review.json')['records'];pages=PublicPages(path=root/'data/source-cache.json')
    if collect:
        for row in source:
            for sid in row['subjectIds'][:3]:
                preferred='movie'if row.get('kind')=='movie'else'tv';found=None
                for kind in [preferred,'tv'if preferred=='movie'else'movie']:
                    value=pages.json('https://m.douban.com/rexxar/api/v2/'+kind+'/'+sid)
                    if isinstance(value,dict)and str(value.get('id'))==sid and value.get('title')and not value.get('code'):
                        medium=value.get('type')or kind
                        found={'available':True,'subjectId':sid,'endpoint':kind,'mediaType':medium,'title':value['title'],'originalTitle':value.get('original_title',''),'year':str(value.get('year','')),'season':subject_season(value['title']+' '+value.get('original_title',''))if medium=='tv'else 0,'aliases':value.get('aka',[])[:20]if isinstance(value.get('aka'),list)else[],'releaseDates':value.get('pubdate',[]),'durations':value.get('durations',[])};break
                subjects[sid]=found or{'available':False,'subjectId':sid,'status':'network_or_record_unavailable','events':pages.events[-2:]}
                print(json.dumps({'candidate':sid,'available':bool(found)},ensure_ascii=True),flush=True)
        pages.save()
    main=load(root/'docs/catalog.json');home=load(root/'docs/home/home.json');works={w['slug']:w for w in main['entries']+[w for w in home['works']if not w.get('knownCatalog')]}
    review=load(root/'docs/pending-name-review.json');ledger={r['slug']:r for r in review.get('records',[])}
    cache=load(root/'data/home-title-cache.json').get('records',{});rows=[]
    for item in source:
        w=works.get(item.get('slug'),{});zh=w.get('zh')or{};n=0 if(w.get('kind')or item.get('kind'))=='movie'else int(w.get('artworkSeasonNumber')or w.get('seasonNumber')or 1)
        season=next((s for s in w.get('seasons',[])if s.get('season')==n),{})
        year=str(season.get('year')or(zh.get('_identityYear'))or(w.get('officialIdentity')or{}).get('year')or w.get('year')or'')
        facts=[subjects[s]for s in item['subjectIds']if s in subjects];name=zh.get('title','');status='unverified'
        if not w:
            saved=cache.get(item.get('officialId'),{}).get('verifiedZh',{});name=saved.get('title','');status='verified_cached_not_in_current_catalog'if mainland_name(name)else'not_in_current_catalog'
        elif mainland_name(name):status='verified_name_only'if zh.get('nameOnlyScope')else'verified_name_preserved'
        elif not item['subjectIds']:status='no_candidate_supplied'
        elif not any(f.get('available')for f in facts):status='network_or_record_unavailable'
        elif any(f.get('mediaType',f['endpoint'])!=('movie'if w['kind']=='movie'else'tv')for f in facts if f.get('available')):status='medium_conflict'
        elif any(f.get('season')!=n for f in facts if f.get('available')):status='season_conflict'
        elif any(f.get('year')!=year for f in facts if f.get('available')):status='year_conflict'
        elif ledger.get(w['slug'],{}).get('status')=='identity_no_chinese_name':status='identity_no_chinese_name'
        else:status=ledger.get(w['slug'],{}).get('status','unverified')
        if status=='identity_no_chinese_name'and any(re.search(r'[\u3400-\u9fff]',t)and not mainland_name(t)for f in facts for t in [f.get('title','')]+f.get('aliases',[])):status='regional_alias_only'
        rows.append(dict(item,finalTitle=name,status=status,requestedSeason=n,requestedYear=year,currentKind=w.get('kind'),nameOnlyScope=zh.get('nameOnlyScope'),subjects=facts))
    labels={'regional_alias_only':'只见港／台标记别名，未作大陆片名','verified_name_only':'已核实特别篇／版本名称，未套用详情评分','verified_name_preserved':'已核实中文名，保留现有资料','verified_cached_not_in_current_catalog':'已核实名称保留在缓存，本期目录无此作品','not_in_current_catalog':'本期目录无此作品','no_candidate_supplied':'清单未提供可核实条目，不认定未收录','network_or_record_unavailable':'网络或条目未完成，待重试','medium_conflict':'电影／剧集类型冲突，未套用资料','season_conflict':'候选季数与当前季不同，未套用资料','year_conflict':'年份不同，尚无充分对应证据','identity_no_chinese_name':'身份已核实，暂无可采用的中文名','unverified':'尚未通过身份核验','future_release':'尚未上线，未查源','verified':'已核实'}
    report={'schema':1,'checkedAt':datetime.now(timezone.utc).isoformat(timespec='seconds'),'candidateOnly':True,'geminiUsed':False,'sourceProbingPerformed':False,'subjects':subjects,'records':rows,'summary':{s:sum(r['status']==s for r in rows)for s in sorted({r['status']for r in rows})}}
    dump(path,report)
    lines=['# 用户提供的49项豆瓣候选核对','', '候选编号只用于定位条目；不是中文名、季数、年份或版本的自动批准。保留原有已核实结果，不把第一季资料套给后续季。没有候选或请求失败不等于未收录。','', '检查时间：'+report['checkedAt'],'', '| 英文原名 | 当前中文名 | 结果 | 当前年／季 | 候选条目 |','|---|---|---|---|---|']
    for r in rows:
        links='、'.join('['+s+'](https://movie.douban.com/subject/'+s+'/)'for s in r['subjectIds'])or'—';cells=[r['englishTitle'],r['finalTitle']or'—',labels.get(r['status'],r['status']),r['requestedYear']+' / '+str(r['requestedSeason']),links];lines.append('| '+' | '.join(str(c).replace('|','／').replace('\n',' ')for c in cells)+' |')
    (root/'docs/douban-candidate-review.md').write_text('\n'.join(lines)+'\n',encoding='utf8');return report
if __name__=='__main__':
    args=argparse.ArgumentParser();args.add_argument('--summarize',action='store_true');v=args.parse_args();print(json.dumps(run(collect=not v.summarize)['summary'],ensure_ascii=True))
