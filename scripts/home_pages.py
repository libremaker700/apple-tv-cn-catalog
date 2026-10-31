"""A bounded homepage and its official topic pages, with shared work identities."""
import re,hashlib,concurrent.futures
from datetime import datetime,timezone
from urllib.parse import urlsplit
from home_sources import CHANNEL,watch_url

CATEGORY_NAMES={'Coming to Apple TV':'即将上线','Kids & Family':'儿童与家庭','Sci-Fi':'科幻','Nonfiction':'非虚构','Action Adventure':'动作冒险','TV Shows':'电视剧','Dramas':'剧情','Comedies':'喜剧','Thrillers':'惊悚','Crime':'犯罪','Movies':'电影'}
LABELS={'Top 10 TV Shows':'Top 10 电视剧','Top 10 Movies':'Top 10 电影','New Releases':'最新上线','Dark Destinations':'暗黑秘境','Browse All Apple Originals':'浏览全部 Apple 原创作品','Must-See Hits':'必看热门影视',
 'Essentials':'精选必看','Action-Packed Sci-Fi':'动作科幻','Sci-Fi Mysteries':'动作科幻片','Heartfelt Sci-Fi':'温情科幻','All Sci-Fi':'全部科幻影视','TV & Movie Fun':'趣味影视','Animation, Adventure & More':'动画与冒险','Family-Friendly Frights':'合家欢惊奇故事','Snoopy & Peanuts':'史努比与花生漫画','Watch with Your Family':'全家一起看','Books Come to Life':'书中的故事','Amazing Animals':'奇妙动物','Sing-Along Fun':'一起唱歌','All Shows':'全部剧集','All Movies':'全部电影'}
LABELS.update({'Coming to Apple TV+':'即将上线','Latest Trailers':'最新预告','Explore Upcoming Apple Originals & Add to Watchlist':'即将上线的原创作品','Recent Highlights':'近期精选','Sports':'体育','Nature':'自然','Real-Life Stories':'真实故事','Music':'音乐','All Nonfiction Movies':'全部非虚构电影','All Nonfiction TV Shows':'全部非虚构剧集','Spies & Detectives':'间谍与侦探','Historical Epics':'历史史诗','Sci-Fi Action':'科幻动作','All Action Adventure':'全部动作冒险','Action':'动作','Comedy':'喜剧','Drama':'剧情','Nonfiction':'非虚构','Sci-Fi':'科幻','Kids & Family':'儿童与家庭','Crime Dramas':'犯罪剧情','Workplace Dramas':'职场故事','Go Back in Time':'回望历史','All Drama TV Shows':'全部剧情剧集','Feel-Good Comedies':'轻松治愈喜剧','Dark Comedies':'黑色喜剧','Funny Co-Workers':'职场喜剧','All Comedy TV Shows':'全部喜剧剧集','Based on a Book':'根据文学作品改编','Sci-Fi Thrillers':'科幻惊悚','Psychological Thrillers':'心理惊悚','Action Thrillers':'动作惊悚','All Thrillers':'全部惊悚作品','Crime Comedies':'犯罪喜剧','Crime Documentaries':'犯罪纪录片','All Crime':'全部犯罪题材','Great Movies Now on Apple TV':'精选电影','Comedies':'喜剧电影','Dramas':'剧情电影','Documentaries':'纪录片'})
def clean(text):return re.sub(r'\s+',' ',re.sub(r'[\u200b-\u200f\ufeff]', '',str(text or ''))).strip()
def name_key(text):return re.sub(r'[^a-z0-9]','',clean(text).casefold())
def page_id(identity):return 'topic-'+hashlib.sha256(identity.encode()).hexdigest()[:16]
def page_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.hostname!='tv.apple.com' or p.username or p.password or not re.fullmatch(r'/us/(room|shelf|collection|channel)/[^?#]+',p.path):raise ValueError('Invalid topic source')
    return 'https://tv.apple.com'+p.path
def collect(catalog,api,image):
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
        imgs=it.get('images',{});names=('shelfImageBackground','contentImage16X9','shelfItemImage')if w>h else('shelfItemImage','posterArt','contentImageTall')
        def choose(images):
            for n in names:
                x=images.get(n)or{};a=x.get('width',0);b=x.get('height',0)
                # Stage artwork may be 4:3; prefer it over generic title cards.
                stage_background=w==1920 and h==1080 and n=='shelfImageBackground' and a and b and a>b
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
        return dict(slug=slug,officialId=identity,**art(it,w,h))
    def work_rows(items,w,h):
        rows=[];seen=set()
        for item in items:
            row=work(item,w,h)
            if row and row['officialId']not in seen:seen.add(row['officialId']);row['rank']=len(rows)+1;rows.append(row)
        return rows
    def shelf(sh,source,forced=None):
        title=clean((sh.get('header')or{}).get('title'));layout=forced or('landscape'if sh.get('displayType')=='epicShowcase'else'portrait');w,h=(640,360)if layout=='landscape'else(400,600)
        if not title or title=='Watch Premieres for Free':return None
        rows=work_rows(api.shelf(sh)['items'],w,h)
        if not rows:return None
        return {'id':sh['id'],'title':LABELS.get(title,title),'officialTitle':title,'source':source,'layout':layout,'items':rows,'count':len(rows)}
    root=api.canvas('channel','tvs.sbd.4000');root_shelves=root['shelves'];home={'hero':[],'shelves':[]}
    for sh in root_shelves:
        if sh.get('displayType')=='epicStageWithUpsell':home['hero']=work_rows(sh['items'],1920,1080)
    categories=next(s for s in root_shelves if s['id']=='uts.col.tv-plus-browse-by-category');topic_rows=[];coming=None
    for it in categories['items']:
        if it.get('type')!='Room':continue
        title=clean(it['title']);source=page_url(it['url']);pid=page_id(it['id']);name=CATEGORY_NAMES.get(title,title)
        raw=api.canvas('room',it['id']);page={'id':pid,'officialId':it['id'],'title':name,'source':source,'hero':[],'shelves':[]}
        for sh in raw['shelves']:
            if sh.get('displayType')in('epicStage','epicStageWithUpsell'):page['hero']=work_rows(sh['items'],1920,1080)
            else:
                row=shelf(sh,source)
                if row:page['shelves'].append(row)
        if not page['shelves'] and page['hero']:page['shelves']=[{'id':it['id']+'-all','title':name,'officialTitle':title,'source':source,'layout':'portrait','items':work_rows(next(s['items']for s in raw['shelves']if s.get('displayType')in('epicStage','epicStageWithUpsell')),400,600)}]
        if not page['shelves']:raise ValueError('Empty topic '+title)
        pages.append(page)
        if title=='Coming to Apple TV':coming=page
        else:topic_rows.append(dict(pageId=pid,officialId=it['id'],title=name,**art(it,400,600)))
    # Traverse Apple's canvas order. Only skip non-film/show offers/sports and the
    # explicitly hidden free-premiere shelf; the upcoming destination stays last.
    for sh in root_shelves:
        title=clean((sh.get('header')or{}).get('title'))
        if not title or title=='Watch Premieres for Free' or sh.get('displayType')in ('epicStage','epicStageWithUpsell','channelUpsell','upNextLockup','sportsCardLockup'):continue
        if title!='Browse All Apple Originals' and not any(i.get('type')in ('Movie','Show')for i in sh.get('items',[])):continue
        if title=='Browse All Apple Originals':row={'id':sh['id'],'title':LABELS[title],'officialTitle':title,'source':CHANNEL,'layout':'portrait','kind':'topics','items':topic_rows,'count':len(topic_rows)}
        else:row=shelf(sh,CHANNEL,'landscape'if title=='Dark Destinations'else'portrait')
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
    for value in works.values():
        if value.get('landscapeSource'):value['landscapeArtwork']=rendered[value.pop('landscapeSource')]['artwork']
    out={'schema':3,'source':CHANNEL,'sources':list(dict.fromkeys([CHANNEL]+[p['source']for p in pages])),'hero':home['hero'],'shelves':home['shelves'],'pages':pages,'works':list(works.values())}
    return out,{'heroCount':len(out['hero']),'shelfCount':len(out['shelves']),'topicPages':len(pages),'workCount':len(works),'additionalWorks':sum(not w.get('knownCatalog')for w in works.values()),'orderPolicy':'official-canvas-with-user-exclusions','officialCanvasOrder':[{'id':s['id'],'title':clean((s.get('header')or{}).get('title'))}for s in root_shelves],'officialShelves':[{'title':s['title'],'count':len(s['items'])}for s in out['shelves']]}

def image_rows(home):
    return [r for p in [home]+home.get('pages',[])for r in p['hero']+[r for s in p['shelves']for r in s['items']if r.get('artwork')]]+[{'artwork':w['landscapeArtwork'],'width':960,'height':540}for w in home.get('works',[])if w.get('landscapeArtwork')]
