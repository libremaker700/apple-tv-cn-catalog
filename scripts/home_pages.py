"""A bounded homepage and its official topic pages, with shared work identities."""
import re,hashlib,concurrent.futures
from datetime import datetime,timezone
from urllib.parse import urlsplit
from requests import HTTPError
from home_sources import CHANNEL,SEARCH,data_page,watch_url

CATEGORY_NAMES={'Coming to Apple TV':'即将上线','Kids & Family':'儿童与家庭','Sci-Fi':'科幻','Nonfiction':'非虚构','Action Adventure':'动作冒险','TV Shows':'电视剧','Dramas':'剧情','Comedies':'喜剧','Thrillers':'惊悚','Crime':'犯罪','Movies':'电影'}
LABELS={'Top 10 TV Shows':'Top 10 电视剧','Top 10 Movies':'Top 10 电影','New Releases':'最新上线','Dark Destinations':'暗黑秘境','Browse All Apple Originals':'浏览全部 Apple 原创作品','Must-See Hits':'必看热门影视',
 'Essentials':'精选必看','Action-Packed Sci-Fi':'动作科幻','Sci-Fi Mysteries':'动作科幻片','Heartfelt Sci-Fi':'温情科幻','All Sci-Fi':'全部科幻影视','TV & Movie Fun':'趣味影视','Animation, Adventure & More':'动画与冒险','Family-Friendly Frights':'合家欢惊奇故事','Snoopy & Peanuts':'史努比与花生漫画','Watch with Your Family':'全家一起看','Books Come to Life':'书中的故事','Amazing Animals':'奇妙动物','Sing-Along Fun':'一起唱歌','All Shows':'全部剧集','All Movies':'全部电影'}
LABELS.update({'Coming to Apple TV+':'即将上线','Latest Trailers':'最新预告','Explore Upcoming Apple Originals & Add to Watchlist':'即将上线的原创作品','Recent Highlights':'近期精选','Sports':'体育','Nature':'自然','Real-Life Stories':'真实故事','Music':'音乐','All Nonfiction Movies':'全部非虚构电影','All Nonfiction TV Shows':'全部非虚构剧集','Spies & Detectives':'间谍与侦探','Historical Epics':'历史史诗','Sci-Fi Action':'科幻动作','All Action Adventure':'全部动作冒险','Action':'动作','Comedy':'喜剧','Drama':'剧情','Nonfiction':'非虚构','Sci-Fi':'科幻','Kids & Family':'儿童与家庭','Crime Dramas':'犯罪剧情','Workplace Dramas':'职场故事','Go Back in Time':'回望历史','All Drama TV Shows':'全部剧情剧集','Feel-Good Comedies':'轻松治愈喜剧','Dark Comedies':'黑色喜剧','Funny Co-Workers':'职场喜剧','All Comedy TV Shows':'全部喜剧剧集','Based on a Book':'根据文学作品改编','Sci-Fi Thrillers':'科幻惊悚','Psychological Thrillers':'心理惊悚','Action Thrillers':'动作惊悚','All Thrillers':'全部惊悚作品','Crime Comedies':'犯罪喜剧','Crime Documentaries':'犯罪纪录片','All Crime':'全部犯罪题材','Great Movies Now on Apple TV':'Apple TV 正在热播','Comedies':'喜剧电影','Dramas':'剧情电影','Documentaries':'纪录片'})
LABELS['A Holiday Classic']='节日经典'
FEATURE_SIZE=(640,800)
FEATURE_LOGO_LAYOUT='aligned-31-v1'
KIDS_HOME_ROOM='uts.room.kids-tv-plus'
MOVIES_HOME_ROOM='uts.room.movies-on-apple-tv'
SHELF_SUBTITLES={'Watch these shows and movies together.':'一起观看这些电视节目和电影。'}
KIDS_EDITORIAL_ROOM='edt.item.6126cd40-38d1-4e11-8211-3f41619392df'
LEARN_SHELF='edt.col.6a7e3ee5-401c-4f44-a2e7-735a055a3ef1'
LEARN_URL='https://tv.apple.com/us/collection/lets-learn-together/'+LEARN_SHELF+'?ctx_cvs=edt.cvs.6126cd67-fc86-4eea-a72c-5aa69ce16575&ctx_shelf=edt.shelf.6a162139-2028-41f5-bbd5-2360b25eb83b'

def excluded_home_shelf(shelf):
    title=(shelf.get('header')or{}).get('title')or shelf.get('officialTitle')or''
    return title=='Watch Premieres for Free'

def clean(text):return re.sub(r'\s+',' ',re.sub(r'[\u200b-\u200f\ufeff]', '',str(text or ''))).strip()
def name_key(text):return re.sub(r'[^a-z0-9]','',clean(text).casefold())
def page_id(identity):return 'topic-'+hashlib.sha256(identity.encode()).hexdigest()[:16]
def page_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.hostname!='tv.apple.com' or p.username or p.password or not re.fullmatch(r'/us/(room|shelf|collection|channel)/[^?#]+',p.path):raise ValueError('Invalid topic source')
    return 'https://tv.apple.com'+p.path

def kids_search_room(html):
    search=data_page(html,'SearchPageIntent',None)
    if search.get('canonicalURL')!=SEARCH:raise ValueError('Unexpected Apple search landing page')
    matches=set()
    for shelf in search.get('shelves',[]):
        if clean((shelf.get('header')or{}).get('title'))!='Browse':continue
        for row in shelf.get('items',[]):
            if clean(row.get('title'))!='Kids & Family':continue
            destination=(row.get('segue')or{}).get('destination')or{}
            identity=destination.get('id','')
            if (destination.get('$kind')=='RoomPageIntent' and destination.get('storefront')=='us'
                    and isinstance(identity,str) and re.fullmatch(r'(?:edt\.item\.|uts\.room\.)[a-zA-Z0-9.\-]{1,100}',identity)):
                matches.add(identity)
    if len(matches)!=1:raise ValueError('Missing or ambiguous US Kids & Family search destination')
    return matches.pop()

def topic_shelf_changes(previous,current):
    before={page['id']:page for page in previous.get('pages',[]) if page.get('officialId')}
    after={page['id']:page for page in current.get('pages',[]) if page.get('officialId')}
    changes=[]
    for identity in dict.fromkeys([*after,*before]):
        old=before.get(identity,{})
        new=after.get(identity,{})
        old_shelves={s['id']:s['officialTitle'] for s in old.get('shelves',[])}
        new_shelves={s['id']:s['officialTitle'] for s in new.get('shelves',[])}
        added=[title for key,title in new_shelves.items() if key not in old_shelves]
        removed=[title for key,title in old_shelves.items() if key not in new_shelves]
        renamed=[{'before':old_shelves[key],'after':title} for key,title in new_shelves.items()
                 if key in old_shelves and title!=old_shelves[key]]
        source_changed=bool(old and new and old['source']!=new['source'])
        if added or removed or renamed or source_changed:
            changes.append({'pageId':identity,'title':(new or old)['title'],'added':added,'removed':removed,
                            'renamed':renamed,'sourceChanged':source_changed})
    return changes

def kids_editorial_shelves(api,shelves):
    # The room endpoint can omit or shorten this web editorial row.
    before='edt.col.6a036cf4-74fa-4d18-9994-75ec1f1338f8'
    after='edt.col.638d9741-269d-469e-9762-48dbf059c5e1'
    indexes={row['id']:i for i,row in enumerate(shelves)}
    if not {LEARN_SHELF,before,after}.intersection(indexes):return shelves
    try:
        official=api.editorial_shelf(LEARN_SHELF,LEARN_URL)
    except HTTPError as error:
        if error.response is not None and error.response.status_code in (404,410) and LEARN_SHELF not in indexes:
            return shelves
        raise
    out=list(shelves)
    if LEARN_SHELF in indexes:out[indexes[LEARN_SHELF]]=official
    else:out.insert(indexes[before] if before in indexes else indexes[after]+1,official)
    return out

def collect(catalog,api,image,poster=None,kids_room=None):
    entries={};works={};details={};art_jobs={};pages=[]
    for e in catalog['entries']:
        for url in [(e.get('officialIdentity')or{}).get('watchUrl',''),(e.get('zh')or{}).get('watchUrl','')]:
            m=re.search(r'umc\.cmc\.[a-z0-9]+',url)
            if m:entries.setdefault(m[0],e)
    def metadata(it):
        identity=it['id']
        if identity not in details:
            value=api.get('movie'if it['type']=='Movie'else'series',identity)
            if value.get('id')!=identity or value.get('type')!=it['type'] or clean(value.get('title')).casefold()!=clean(it['title']).casefold():raise ValueError('Detail identity mismatch')
            details[identity]=value
        return details[identity]
    def art(it,w,h):
        imgs=it.get('images',{});names=('shelfItemImage','shelfImageBackground','contentImage16X9')if(w,h)==(1920,720)else ('shelfImageBackground','contentImage16X9','shelfItemImage')if w>h else('shelfItemImage','posterArt','contentImageTall')
        def choose(images):
            if (w,h)==FEATURE_SIZE:return (images.get('shelfItemImage')or{}).get('url')
            for n in names:
                x=images.get(n)or{};a=x.get('width',0);b=x.get('height',0)
                # Stage artwork may be 4:3; prefer it over generic title cards.
                stage_background=w==1920 and h==1080 and n=='shelfImageBackground' and a and b and a>b
                if (w,h)==(1920,720):
                    if a and b and 2.2<a/b<2.9:return x.get('url')
                    continue
                if stage_background or (a and b and ((w>h and 1.6<a/b<1.9)or(w<h and .4<a/b<.8))):return x.get('url')
        url=choose(imgs)
        if not url and it.get('type')in('Movie','Show'):url=choose(metadata(it).get('images',{}))
        if not url:raise ValueError('Missing native artwork '+str(it.get('title')))
        url=url.replace('{w}',str(w)).replace('{h}',str(h)).replace('{f}','jpg').replace('{c}','sr')
        if not re.match(r'https://is\d+-ssl\.mzstatic\.com/image/',url)or'{'in url:raise ValueError('Invalid image origin')
        art_jobs[url]=(w,h);return {'sourceArtwork':url,'width':w,'height':h}
    def work(it,w=400,h=600):
        identity=it.get('id','');kind={'Movie':'movie','Show':'series'}.get(it.get('type'))
        if not kind or not re.fullmatch(r'umc\.cmc\.[a-z0-9]+',identity):return None
        en=clean(it['title']);entry=entries.get(identity)
        if not entry:
            candidates=[e for e in catalog['entries']if name_key(en)and name_key(e['en'])==name_key(en)and e['kind']==kind and not any(re.search(r'umc\.cmc\.',u)for u in [(e.get('officialIdentity')or{}).get('watchUrl',''),(e.get('zh')or{}).get('watchUrl','')])]
            if len(candidates)==1:
                e=candidates[0];date=metadata(it).get('releaseDate');year=str(datetime.fromtimestamp(date/1000,timezone.utc).year)if isinstance(date,(int,float))and date>0 else''
                years={str((e.get('zh')or{}).get('_identityYear','')),str((e.get('officialIdentity')or{}).get('year','')),str(e.get('releaseDate',''))[:4]}|{str(s.get('year',''))for s in e.get('seasons',[])}
                if year and year in years:entry=e;entries[identity]=e
        slug=entry['slug']if entry else'home-'+identity[8:]
        if identity not in works:
            value={'slug':slug,'officialId':identity,'en':entry['en']if entry else en,'kind':kind,'watchUrl':watch_url(it['url'],identity,kind),'genres':[g['name']for g in (metadata(it).get('genres')or it.get('genres',[]))if g.get('name')]}
            if entry:value['knownCatalog']=True
            else:
                detail=metadata(it);date=detail.get('releaseDate',it.get('releaseDate'))
                if isinstance(date,(int,float))and date>0:
                    iso=datetime.fromtimestamp(date/1000,timezone.utc).date().isoformat();value.update(year=iso[:4],releaseDate=iso)
                value['summaryEn']=str(detail.get('description')or detail.get('heroDescription')or'')[:1800]
                value['landscapeSource']=art(detail,960,540)['sourceArtwork']
            works[identity]=value
        row=dict(slug=slug,officialId=identity,**art(it,w,h))
        logo=(it.get('images',{}).get('contentLogo')or{}).get('url','')
        if (w,h)in((400,600),(1920,720),FEATURE_SIZE) and logo:
            row['sourceLogo']=logo.replace('{w}','470').replace('{h}','140').replace('{f}','png')
        return row
    def work_rows(items,w,h):
        rows=[];seen=set()
        for item in items:
            row=work(item,w,h)
            if row and row['officialId']not in seen:seen.add(row['officialId']);row['rank']=len(rows)+1;rows.append(row)
        return rows
    def shelf(sh,source,forced=None):
        title=clean((sh.get('header')or{}).get('title'))
        if not title or title=='Watch Premieres for Free':return None
        items=api.shelf(sh)['items']
        shows=[i for i in items if i.get('type')in('Movie','Show') and re.fullmatch(r'umc\.cmc\.[a-z0-9]+',i.get('id',''))]
        epic=sh.get('displayType')=='epicShowcase'
        def has_tall_art(item):
            art=(item.get('images')or{}).get('shelfItemImage')or{}
            return art.get('width',0)>0 and art.get('height',0)>art['width'] and bool(art.get('url'))
        editorial=epic and len(shows)>=2 and all(i.get('flavorType')=='Flavor_F' and has_tall_art(i) for i in shows)
        layout=forced or ('showcase' if epic and len(shows)==1 else
            'featured' if editorial or epic and len({i['id']for i in shows})>=4 and all(map(has_tall_art,shows)) else
            'landscape' if epic else 'portrait')
        w,h={'showcase':(1920,720),'featured':FEATURE_SIZE,'landscape':(640,360),'portrait':(400,600)}[layout]
        rows=work_rows(items,w,h)
        if not rows:return None
        if layout=='featured':
            from home_copy import GENRES,enrich,featured_api_copy
            by_id={i['id']:i for i in shows}
            copy={}
            for row in rows:
                identity=row['officialId']
                genres=[GENRES[g['name']]for g in by_id[identity].get('genres',[])if g.get('name')in GENRES]
                copy[identity]=featured_api_copy(by_id[identity]) if editorial else {'descriptionEn':'','badgeEn':'','noteEn':'','genresZh':list(dict.fromkeys(genres))[:2]}
                if editorial:row['featuredCopyTop']=760
            # Keep catalogue genres as a fallback until official room copy is available.
            for row in enrich({'hero':rows},copy,{},None,0,source_url=source)[0]['hero']:
                rows[row['rank']-1]['showcaseCopy']=row['copy']
        result={'id':sh['id'],'title':LABELS.get(title,title),'officialTitle':title,'source':source,'layout':layout,'items':rows,'count':len(rows)}
        subtitle=SHELF_SUBTITLES.get(clean((sh.get('header')or{}).get('shortNote')))
        if subtitle:result['subtitle']=subtitle
        return result
    def topic_page(title,room_id,pid,source=None):
        raw=api.canvas('room',room_id)
        canonical=page_url(raw['source']) if raw.get('source') else None
        for candidate in (canonical,source):
            if candidate and ('/us/room/' not in candidate or candidate.rsplit('/',1)[-1]!=room_id):
                raise ValueError('Topic destination identity changed')
        if not (source or canonical):raise ValueError('Topic destination missing')
        source=source or canonical
        name=CATEGORY_NAMES.get(title,title)
        page={'id':pid,'officialId':room_id,'title':name,'officialTitle':title,'source':source,'hero':[],'shelves':[]}
        stage=None;seen=set()
        official_shelves=kids_editorial_shelves(api,raw['shelves']) if room_id==KIDS_EDITORIAL_ROOM else raw['shelves']
        for sh in official_shelves:
            if sh['id'] in seen:raise ValueError('Duplicate official shelf in topic '+title)
            seen.add(sh['id'])
            if sh.get('displayType')in('epicStage','epicStageWithUpsell'):
                stage=sh
                page['hero']=work_rows(sh['items'],1920,1080)
            else:
                row=shelf(sh,source)
                if row:page['shelves'].append(row)
        if not page['shelves'] and page['hero']:
            rows=work_rows(stage['items'],400,600)
            page['shelves']=[{'id':room_id+'-all','title':name,'officialTitle':title,'source':source,'layout':'portrait','items':rows}]
        if not page['shelves']:raise ValueError('Empty topic '+title)
        return page

    root=api.canvas('channel','tvs.sbd.4000');root_shelves=root['shelves'];home={'hero':[],'shelves':[]}
    for sh in root_shelves:
        if sh.get('displayType')=='epicStageWithUpsell':home['hero']=work_rows(sh['items'],1920,1080)
    categories=api.shelf(next(s for s in root_shelves if s['id']=='uts.col.tv-plus-browse-by-category'))
    topic_rows=[];topic_ids=set();coming=None
    for it in categories['items']:
        if it.get('type')!='Room':continue
        title=clean(it['title']);room_id=it['id'];source=page_url(it['url']);pid=page_id(room_id)
        if kids_room and (room_id==KIDS_HOME_ROOM or title=='Kids & Family'):
            pid=page_id(KIDS_HOME_ROOM);room_id=kids_room;source=None
        elif room_id==MOVIES_HOME_ROOM or title=='Movies':
            pid=page_id(MOVIES_HOME_ROOM)
        if pid in topic_ids:continue
        topic_ids.add(pid)
        page=topic_page(title,room_id,pid,source)
        pages.append(page)
        if title=='Coming to Apple TV':coming=page
        else:topic_rows.append(dict(pageId=pid,officialId=room_id,title=page['title'],**art(it,400,600)))
    if kids_room and page_id(KIDS_HOME_ROOM) not in topic_ids:
        pages.append(topic_page('Kids & Family',kids_room,page_id(KIDS_HOME_ROOM)))
    # Traverse Apple's canvas order. Only skip non-film/show offers/sports and the
    # explicitly hidden free-premiere shelf; the upcoming destination stays last.
    for sh in root_shelves:
        title=clean((sh.get('header')or{}).get('title'))
        if not title or excluded_home_shelf(sh) or sh.get('displayType')in ('epicStage','epicStageWithUpsell','channelUpsell','upNextLockup','sportsCardLockup'):continue
        if title!='Browse All Apple Originals' and not any(i.get('type')in ('Movie','Show')for i in sh.get('items',[])):continue
        if title=='Browse All Apple Originals':row={'id':sh['id'],'title':LABELS[title],'officialTitle':title,'source':CHANNEL,'layout':'portrait','kind':'topics','items':topic_rows,'count':len(topic_rows)}
        else:row=shelf(sh,CHANNEL,'landscape'if title=='Dark Destinations'else None)
        if not row:continue
        if title=='Must-See Hits':
            pid='must-see-hits';row['morePageId']=pid;pages.append({'id':pid,'title':LABELS[title],'source':page_url((sh.get('header')or{}).get('url')or sh['url']),'hero':[],'shelves':[dict(row)]})
        home['shelves'].append(row)
    if not coming:raise ValueError('Missing upcoming topic')
    seen=set();upcoming=[]
    for row in coming['hero']+[r for sh in coming['shelves']for r in sh['items']]:
        if row['officialId']not in seen:seen.add(row['officialId']);upcoming.append(row)
    # The upcoming homepage row uses actual portrait images from its destination page.
    existing={r['officialId']:r for sh in coming['shelves']if sh['layout']=='portrait'for r in sh['items']}
    upcoming=[existing[r['officialId']]for r in upcoming if r['officialId']in existing]
    if not upcoming:raise ValueError('Missing upcoming portraits')
    home['shelves'].append({'id':'coming-to-apple-tv','title':'即将上线','officialTitle':'Coming to Apple TV','source':coming['source'],'layout':'portrait','items':upcoming,'count':len(upcoming),'morePageId':coming['id']})
    with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:rendered=dict(pool.map(lambda row:(row[0],image(row[0],*row[1])),art_jobs.items()))
    for page in [home]+pages:
        for row in page['hero']+[r for s in page['shelves']for r in s['items']]:
            if 'sourceArtwork'in row:row.update(rendered[row.pop('sourceArtwork')])
            if row.get('sourceLogo'):
                if not callable(poster):raise ValueError('Official logo renderer is required')
                logo=row.pop('sourceLogo')
                row.update(poster(row,logo,editorial=True) if 'featuredCopyTop' in row else poster(row,logo))
    for value in works.values():
        if value.get('landscapeSource'):value['landscapeArtwork']=rendered[value.pop('landscapeSource')]['artwork']
    out={'schema':3,'source':CHANNEL,'sources':list(dict.fromkeys([CHANNEL]+[p['source']for p in pages])),'hero':home['hero'],'shelves':home['shelves'],'pages':pages,'works':list(works.values())}
    return out,{'heroCount':len(out['hero']),'shelfCount':len(out['shelves']),'topicPages':len(pages),'workCount':len(works),'additionalWorks':sum(not w.get('knownCatalog')for w in works.values()),'orderPolicy':'official-canvas-with-user-exclusions','officialCanvasOrder':[{'id':s['id'],'title':clean((s.get('header')or{}).get('title'))}for s in root_shelves],'officialShelves':[{'title':s['title'],'count':len(s['items'])}for s in out['shelves']]}

def image_rows(home):
    return [r for p in [home]+home.get('pages',[])for r in p['hero']+[r for s in p['shelves']for r in s['items']if r.get('artwork')]]+[{'artwork':w['landscapeArtwork'],'width':960,'height':540}for w in home.get('works',[])if w.get('landscapeArtwork')]
