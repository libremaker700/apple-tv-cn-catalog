"""One public-US synopsis translation per work/source hash, shared by every App surface."""
import copy,json,os,re,time,hashlib,unicodedata,html
from pathlib import Path
from urllib.parse import urlsplit
from title_lookup import read,dump
from home_copy import Translator,digest,valid_zh as short_valid_zh,clean
from season_sync import apply_reviewed_summaries,official_synopsis,season_synopsis_identity,season_synopsis_url,year_date
def valid_zh(text):return short_valid_zh(text,1800) and bool(official_synopsis(text))
VERSION='work-summary-zh-cn-v1'
def key(identity,text):return digest([VERSION,identity,clean(text)])
def norm(s):return re.sub(r"[^a-z0-9]","",unicodedata.normalize('NFKD',s).lower())
def source_id(e):return e.get('officialId')or(urlsplit((e.get('officialIdentity')or{}).get('watchUrl','')).path.rstrip('/').split('/')[-1])or('pr:'+e['slug']if e.get('officialUrl')=='https://www.apple.com/tv-pr/originals/'+e.get('slug','')+'/'else'')
def attach(e,record):
    if isinstance(e.get('zh'),dict):e['zh'].pop('contentRating',None)
    if not record:return
    zh=e.setdefault('zh',{}) or {};e['zh']=zh
    zh.update(metadataPolicy='mainland-v1')
    if 'officialReleaseYear'in record:zh['officialReleaseYear']=record['officialReleaseYear']
    if not valid_zh(record.get('text')):return
    zh.update(summary=record['text'],summary_status='legacy_chinese'if record.get('method')=='existing_chinese'else'translated_official',summary_sources=[{'type':'apple_us_translation','url':record['source']}],summary_source_hash=record['hash'],summary_original=record['original'])
    if not zh.get('watchUrl'):zh['watchUrl']=record['source']
def apply_summaries(value,root,field):
    out=copy.deepcopy(value)
    cache=read(root/'data/work-summary-cache.json',{})
    entries=out.get(field,[])
    apply_reviewed_summaries(entries,root)
    for work in entries:
        show_id=source_id(work)
        attach(work,cache.get('works',{}).get(show_id))
        for season in work.get('seasons',[]):
            identity=season_synopsis_identity(season,show_id)
            if identity is None:continue
            sid,_,number,release=identity
            record=cache.get('seasons',{}).get(sid,{})
            if (record.get('showId'),record.get('season'),record.get('releaseDate'))!=(show_id,number,release):continue
            url=season_synopsis_url(identity)
            if valid_zh(season.get('summary')) and season.get('summarySource')!=url:continue
            if valid_zh(record.get('text')):
                season.update(summary=record['text'],summarySource=url,summaryPending=False)
    return out

def apply_main(value,root):
    return apply_summaries(value,root,'entries')

def apply_home(value,root):
    from detail_metadata import apply_cached
    return apply_cached(apply_summaries(value,root,'works'),root,home=True)

def season_originals(root,entries,work_originals):
    """Reuse synopsis copy from verified season responses already collected for artwork."""
    from detail_metadata import valid as valid_detail
    eligible={}
    conflicts=set()
    protected=set()
    for work in entries:
        show_id=source_id(work)
        zh=work.get('zh')or{}
        packets=zh.get('detailSeasons')or[zh.get('detailMetadata')]
        douban_seasons={(p['season'],str(p['year'])) for p in packets
                        if valid_detail(p,'series') and p['summaryStatus']=='AVAILABLE'}
        for season in work.get('seasons',[]):
            identity=season_synopsis_identity(season,show_id)
            if identity is None:continue
            sid=identity[0]
            if eligible.setdefault(sid,identity)!=identity:conflicts.add(sid)
            if ((season['season'],str(season['year'])) in douban_seasons
                    or valid_zh(season.get('summary')) and season.get('summarySource')!=season_synopsis_url(identity)):
                protected.add(identity)
    result={}
    main=read(root/'data/season-cache.json',{}).get('shows',{})
    home=read(root/'data/home-season-cache.json',{}).get('records',{})
    groups=[(row.get('showId'),row) for row in main.values()]+list(home.items())
    for show_id,group in groups:
        for season in group.get('seasons',[]):
            identity=season_synopsis_identity(season,show_id)
            text=official_synopsis(season.get('summaryOriginal'))
            if (identity is not None and identity[0] not in conflicts and eligible.get(identity[0])==identity
                    and identity not in protected and text and text!=work_originals.get(show_id)):
                result.setdefault(identity,text)
    return result

def run(root,api,translator,now,limit=400,season_limit=24):
    main=read(root/'docs/catalog.json',{});home=read(root/'docs/home/home.json',{})
    cache=read(root/'data/work-summary-cache.json',{'schema':1,'records':{},'works':{}});records=cache['records'];works=cache['works'];seasons=cache.setdefault('seasons',{});wanted={}
    for record in works.values():record.pop('contentRating',None)
    for e in main['entries']:
        identity=source_id(e)
        if identity:wanted[identity]={'officialId':identity,'en':e['en'],'kind':e['kind'],'watchUrl':e.get('officialIdentity',{}).get('watchUrl')or e['officialUrl'],'zh':e.get('zh')}
    for w in home['works']:wanted[w['officialId']]=dict(w,zh=w.get('zh')or wanted.get(w['officialId'],{}).get('zh'))
    report={'works':len(wanted),'translated':0,'cacheHits':0,'missingOriginal':0,'sourceErrors':0,'apiCalls':0,'usage':[],'errors':[]}
    pending_new=[];pending_refresh=[];source={};metadata={}
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
        except Exception as error:
            report['sourceErrors']+=1;report['errors'].append({'id':identity,'stage':'source','error':type(error).__name__})
            detail=None
        if detail is not None and (not isinstance(detail,dict) or detail.get('id')!=identity
                                   or detail.get('type')!=('Movie'if w['kind']=='movie'else'Show')):
            report['sourceErrors']+=1;report['errors'].append({'id':identity,'stage':'source','error':'identity'})
            continue
        if detail:
            date=year_date(detail.get('releaseDate'))
            metadata[identity]={'source':w['watchUrl']}
            if date:metadata[identity]['officialReleaseYear']=int(date[:4])
        # The published homepage retains the original from an already verified work response.
        text=next((synopsis for value in ((detail or {}).get('description'),(detail or {}).get('heroDescription'),w.get('summaryEn'))
                   if (synopsis:=official_synopsis(value))), '')
        if not text:report['missingOriginal']+=1;continue
        k=key(identity,text);source[identity]=(w,text,k)
        if valid_zh(records.get(k,{}).get('text')) and records[k].get('method')!='existing_chinese':
            report['cacheHits']+=1
        elif now>=records.get(k,{}).get('nextRetry',0):
            target=pending_refresh if valid_zh(works.get(identity,{}).get('text')) else pending_new
            target.append({'id':identity,'text':text})
    entries=main['entries']+home['works']
    apply_reviewed_summaries(entries,root)
    work_originals={identity:record.get('original') for identity,record in works.items()}
    work_originals.update({identity:text for identity,(_,text,_) in source.items()})
    season_source=season_originals(root,entries,work_originals)
    season_keys={identity[0]:key(identity[0],text) for identity,text in season_source.items()}
    pending_seasons=[]
    for identity,text in sorted(season_source.items(),key=lambda item:item[0][3],reverse=True):
        sid=identity[0]
        record=records.get(season_keys[sid],{})
        if not valid_zh(record.get('text')) and now>=record.get('nextRetry',0):
            pending_seasons.append({'id':sid,'text':text})
    pending=(pending_new+pending_seasons[:season_limit]+pending_refresh)[:limit]
    report.update(seasonCandidates=len(season_source),seasonTranslated=0)
    translation_keys={identity:k for identity,(_,_,k) in source.items()}|season_keys
    for offset in range(0,len(pending),4):
        batch=pending[offset:offset+4]
        try:
            result=translator.translate(batch)
            if not all(valid_zh(result.get(row['id'])) for row in batch):
                raise ValueError('invalid_translation_synopsis')
            report['usage'].append(translator.usage)
            for row in batch:
                identity=row['id']
                records[translation_keys[identity]]={'text':result[identity],'method':'machine','model':translator.model}
                report['seasonTranslated' if identity in season_keys else 'translated']+=1
        except Exception as error:
            report['errors'].append({'stage':'translation','error':type(error).__name__,'http':getattr(translator,'http',0)})
            for row in batch:records[translation_keys[row['id']]]={'nextRetry':now+6*3600}
        report['apiCalls']+=1
        dump(root/'data/work-summary-cache.json',cache)
    for identity,(w,text,k)in source.items():
        record=records.get(k,{})
        if valid_zh(record.get('text')):works[identity]=dict(record,original=text,hash=k,source=w['watchUrl'])
    for (sid,show_id,number,release),text in season_source.items():
        record=records.get(season_keys[sid],{})
        if valid_zh(record.get('text')):
            seasons[sid]=dict(record,showId=show_id,season=number,releaseDate=release,original=text,hash=season_keys[sid])
    for identity,info in metadata.items():
        works.setdefault(identity,{}).update(info)
    report['ready']=sum(valid_zh(works.get(identity,{}).get('text')) for identity in wanted)
    report['pending']=len(wanted)-report['ready']
    report['seasonPending']=sum(not valid_zh(records.get(k,{}).get('text')) for k in season_keys.values())
    dump(root/'data/work-summary-cache.json',cache);dump(root/'logs/work-summaries.json',report)
    return report

def main():
    from catalog import ROOT,load,publish,raw_json
    from home_sync import fetch,publish_home,validate_publication
    from home_sources import CHANNEL
    from official_pages import Pages
    now=int(time.time());api=Pages(ROOT,fetch(CHANNEL).decode('utf-8'))
    translator=Translator(os.getenv('GEMINI_API_KEY',''),os.getenv('HOME_COPY_MODEL')or None,max_length=1800)
    report=run(ROOT,api,translator,now)
    from genre_translation import apply as apply_genres
    main=load(ROOT/'docs/catalog.json');genre_home=load(ROOT/'docs/home/home.json');report['genres']=apply_genres(main,genre_home,ROOT,translator)
    (ROOT/'docs/catalog.json').write_bytes(raw_json(main));(ROOT/'docs/home/home.json').write_bytes(raw_json(genre_home))
    folder=ROOT/'docs';m=load(folder/'version.json');publish(load(folder/'catalog.json'),m.get('checked_at'),'shared-official-summary-translation')
    home=apply_home(load(folder/'home/home.json'),ROOT);from reviewed_names import apply as apply_names;home=apply_names(home,ROOT,home=True)
    publish_home(home,folder/'home',now,load(folder/'home/version.json'))
    validate_publication();print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
