"""Complete official channel + sci-fi shelves; never replace provider or existing catalog identities."""
import copy,json,re,concurrent.futures
from urllib.parse import urlsplit
CHANNEL='https://tv.apple.com/us/channel/apple-tv/tvs.sbd.4000'
ROOM='https://tv.apple.com/us/room/sci-fi-on-appletv/edt.item.650b3154-accd-4b87-9f89-6bde117cee31'
ROOM_ID='edt.item.650b3154-accd-4b87-9f89-6bde117cee31'
LABELS={'Great Movies Now on Apple TV':'精选电影','Top 10 TV Shows':'热门剧集','Top 10 Movies':'热门电影','Watch Premieres for Free':'免费试看首集','New Releases':'最新上线',
    'Essentials':'精选必看','Action-Packed Sci-Fi':'动作科幻','Sci-Fi Mysteries':'悬疑科幻','Heartfelt Sci-Fi':'温情科幻','All Sci-Fi':'全部科幻影视'}
def data_page(raw,kind,identity):
    found=re.search(r'<script[^>]*id=["\']serialized-server-data["\'][^>]*>(.*?)</script>',raw,re.S)
    if not found:raise ValueError('Official structured data missing')
    for block in json.loads(found[1]).get('data',[]):
        intent=block.get('intent',{})
        if intent.get('$kind')==kind and intent.get('id')==identity and intent.get('storefront')=='us':return block['data']
    raise ValueError('Official page identity or storefront mismatch')
def watch_url(value,identity,kind):
    p=urlsplit(value or '');wanted='movie' if kind=='movie' else 'show'
    if p.scheme!='https' or p.hostname!='tv.apple.com' or p.username or p.password or not re.fullmatch('/us/'+wanted+r'/[^/]+/'+re.escape(identity),p.path):raise ValueError('Invalid official work URL')
    return 'https://tv.apple.com'+p.path
def detail_work(work,raw):
    data=data_page(raw,'MoviePageIntent' if work['kind']=='movie' else 'ShowPageIntent',work['officialId'])
    header=next((s for s in data.get('shelves',[]) if s.get('id','').startswith('canonical-header-')),{});rows=header.get('items',[])
    first=next((i for i in rows if i.get('id')==work['officialId']),rows[0] if len(rows)==1 else {})
    if not first or str(first.get('title','')).casefold()!=work['en'].casefold():raise ValueError('Official title identity mismatch')
    out=dict(work);out['summaryEn']=str(first.get('description',''))[:1800]
    for match in re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',raw,re.S):
        obj=json.loads(match[1])
        if not isinstance(obj,dict) or obj.get('@type') not in (('Movie',) if work['kind']=='movie' else ('TVSeries','TVShow')) or obj.get('name','').casefold()!=work['en'].casefold():continue
        date=obj.get('datePublished') or obj.get('startDate') or ''
        if re.match(r'(19|20)\d{2}',date):out['year']=date[:4];out['releaseDate']=date[:10]
        cover=obj.get('image','');cover=cover.get('url','') if isinstance(cover,dict) else cover
        if isinstance(cover,str) and re.match(r'https://is\d+-ssl\.mzstatic\.com/image/',cover):out['landscapeSource']=re.sub(r'/\d+x\d+\.\w+$','/960x540.jpg',cover)
    return out
def collect(catalog,channel_html,room_html,image,detail):
    by_id={}
    for entry in catalog['entries']:
        for url in [(entry.get('officialIdentity')or{}).get('watchUrl',''),(entry.get('zh')or{}).get('watchUrl','')]:
            m=re.search(r'umc\.cmc\.[a-z0-9]+',url)
            if m and entry not in by_id.setdefault(m[0],[]):by_id[m[0]].append(entry)
    works={};hero=[];shelves=[];art_jobs={}
    def art(template,width,height):
        url=str(template or '').replace('{w}',str(width)).replace('{h}',str(height)).replace('{c}','sr').replace('{f}','jpg')
        if not re.match(r'https://is\d+-ssl\.mzstatic\.com/image/',url) or '{' in url:raise ValueError('Missing native official artwork')
        art_jobs[url]=(width,height);return url
    def match(item):
        dest=(item.get('segue')or{}).get('destination',{});identity=dest.get('id')or item.get('id','')
        kind='movie' if dest.get('$kind')=='MoviePageIntent' or item.get('type')=='Movie' else 'series' if dest.get('$kind')=='ShowPageIntent' or item.get('type')=='Show' else ''
        if not kind or not re.fullmatch(r'umc\.cmc\.[a-z0-9]+',identity):return None
        name=str(item.get('title',''));candidates=[e for e in by_id.get(identity,[]) if e['kind']==kind]
        if len(candidates)>1:candidates=[e for e in candidates if e['en'].casefold()==name.casefold()]
        if len(candidates)>1:raise ValueError('Ambiguous original identity')
        entry=candidates[0] if candidates else None
        slug=entry['slug'] if entry else 'home-'+identity.removeprefix('umc.cmc.')
        if identity not in works:
            url=watch_url((item.get('segue')or{}).get('url',''),identity,kind)
            work={'slug':slug,'officialId':identity,'en':entry['en'] if entry else name,'kind':kind,'watchUrl':url}
            if not name:raise ValueError('Missing official title')
            if entry:work['knownCatalog']=True
            works[identity]=work
        return {'slug':slug,'officialId':identity}
    for source,raw,kind,identity in [(CHANNEL,channel_html,'ChannelPageIntent','tvs.sbd.4000'),(ROOM,room_html,'RoomPageIntent',ROOM_ID)]:
        data=data_page(raw,kind,identity);found=0
        for shelf in data.get('shelves',[]):
            sid=shelf.get('id','');title=(shelf.get('header')or{}).get('title','')
            if source==CHANNEL and sid=='uts.col.tv-plus-epic-stage':
                for item in shelf.get('items',[]):
                    row=match(item)
                    if row and not any(r['officialId']==row['officialId']for r in hero):
                        row['sourceArtwork']=art((item.get('artwork')or{}).get('wide',{}).get('template'),1920,1080);hero.append(row)
            elif title in LABELS:
                rows=[];seen=set()
                for rank,item in enumerate(shelf.get('items',[]),1):
                    row=match(item)
                    if not row or row['officialId'] in seen:continue
                    seen.add(row['officialId']);row.update(rank=rank,sourceArtwork=art((item.get('artwork')or{}).get('template'),400,600));rows.append(row)
                if not rows or len(rows)>100:raise ValueError('Incomplete official shelf')
                shelves.append({'id':sid,'title':LABELS[title],'officialTitle':title,'source':source,'layout':'portrait','items':rows});found+=1
        if found<4:raise ValueError('Incomplete official page shelves')
    for work in works.values():
        if not work.get('knownCatalog'):
            work.update(detail(work))
            if work.get('landscapeSource'):art_jobs[work['landscapeSource']]=(960,540)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        rendered=dict(pool.map(lambda row:(row[0],image(row[0],*row[1])),art_jobs.items()))
    for row in hero+[r for s in shelves for r in s['items']]:row.update(rendered[row['sourceArtwork']])
    for work in works.values():
        if work.get('landscapeSource'):work['landscapeArtwork']=rendered[work['landscapeSource']]['artwork']
    value={'schema':2,'source':CHANNEL,'sources':[CHANNEL,ROOM],'hero':hero,'shelves':shelves,'works':list(works.values())}
    return value,{'heroCount':len(hero),'shelfCount':len(shelves),'workCount':len(works),'additionalWorks':sum(not w.get('knownCatalog')for w in works.values()),'officialShelves':[{'title':s['title'],'count':len(s['items']),'source':s['source']}for s in shelves]}
