"""Discover real seasons from Apple US; persist only public metadata, never web session parameters."""
import copy,json,re,time
from datetime import datetime,timezone
from html.parser import HTMLParser
from urllib.parse import urlencode

SCHEMA=1
ID=re.compile(r'umc\.cmc\.[a-z0-9]+\Z')

class SeasonError(ValueError):pass

class Scripts(HTMLParser):
    def __init__(self,text):
        super().__init__();self.blocks=[];self.active=None;self.parts=[];self.feed(text)
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='script' and (a.get('id')=='serialized-server-data' or a.get('type')=='application/ld+json'):
            self.active=a;self.parts=[]
    def handle_data(self,data):
        if self.active is not None:self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=='script' and self.active is not None:
            try:self.blocks.append((self.active,json.loads(''.join(self.parts))))
            except (ValueError,TypeError):pass
            self.active=None

def year_date(value):
    try:
        date=datetime.fromtimestamp(value/1000,timezone.utc).strftime('%Y-%m-%d') if isinstance(value,(int,float)) else str(value)[:10]
        return date if re.fullmatch(r'(19|20)\d\d-\d\d-\d\d',date) else ''
    except (ValueError,OverflowError,OSError):return ''

def chinese_summary(value):
    value=re.sub(r'\s+',' ',str(value or '')).strip()
    return value if re.search(r'[\u4e00-\u9fff]',value) and not re.search(r'暂无简介|简介.*(?:待完善|暂未提供)',value) else ''

def base_title(entry):
    name=(entry.get('zh') or {}).get('title') or entry['en']
    return re.sub(r'\s*(?:第\s*[0-9一二三四五六七八九十百]+\s*季|Season\s+\d+)\s*$','',name,flags=re.I).strip()

def label_seasons(entry):
    for season in entry.get('seasons',[]):season['title']=base_title(entry)+' 第'+str(season['season'])+'季'

def public_seasons(rows):
    return [{k:v for k,v in row.items() if k not in ('checkedAt','imageCheckedAt')} for row in rows]

def parse_show(text,show_id):
    blocks=Scripts(text).blocks
    packed=next((v for a,v in blocks if a.get('id')=='serialized-server-data'),None)
    if not isinstance(packed,dict):raise SeasonError('show_page_format_changed')
    rows=packed.get('data',[])
    item=next((r for r in rows if r.get('intent',{}).get('$kind')=='ShowPageIntent' and r['intent'].get('id')==show_id),None)
    if not item:raise SeasonError('show_identity_mismatch')
    options=[]
    for shelf in item.get('data',{}).get('shelves',[]):
        if isinstance(shelf.get('header'),dict) and isinstance(shelf['header'].get('seasons'),list):
            options=shelf['header']['seasons'];break
    if not options:raise SeasonError('season_list_missing')
    seen=set();ids=set();clean=[]
    for row in options:
        number=row.get('seasonNumber');sid=row.get('id','')
        if type(number) is not int or not 1<=number<=100 or number in seen or not ID.fullmatch(sid) or sid in ids:raise SeasonError('duplicate_or_invalid_season')
        seen.add(number);ids.add(sid);clean.append({'season':number,'officialId':sid,'officialEpisodeCount':max(0,int(row.get('episodeCount') or 0))})
    if seen!=set(range(1,max(seen)+1)):raise SeasonError('official_season_list_has_gaps')
    config=next((r.get('data',{}) for r in rows if r.get('intent',{}).get('$kind')=='UtsConfigureIntent'),{})
    params=config.get('configuration',{}).get('applicationProps',{}).get('requiredParamsMap',{}).get('Default',{})
    params={k:params[k] for k in ('utsk','utscf','caller','sf','v','pfm','locale') if k in params}
    if str(params.get('sf'))!='143441' or params.get('locale')!='en-US' or not params.get('utsk'):raise SeasonError('us_metadata_configuration_missing')
    series=next((v for a,v in blocks if isinstance(v,dict) and v.get('@type')=='TVSeries'),{})
    return sorted(clean,key=lambda s:s['season']),params,year_date(series.get('datePublished'))

class Collector:
    def __init__(self,get,save_image,image_exists,cache=None,now=None,artwork_preferences=None):
        self.get=get;self.save_image=save_image;self.image_exists=image_exists;self.now=int(now or time.time())
        self.cache=copy.deepcopy(cache) if cache and cache.get('schema')==SCHEMA else {'schema':SCHEMA,'shows':{}}
        self.artwork_preferences=artwork_preferences or {}
        self.report=[]
    def watch_url(self,entry,seed):
        for candidate in ((entry.get('officialIdentity') or {}).get('watchUrl'),(entry.get('zh') or {}).get('watchUrl'),(seed.get('officialIdentity') or {}).get('watchUrl')):
            if candidate and (m:=re.search(r'https://tv\.apple\.com/(?:us/)?show/[^/?]+/(umc\.cmc\.[a-z0-9]+)',candidate)):
                return 'https://tv.apple.com/us/show/'+entry['slug']+'/'+m[1],m[1]
        text=self.get(entry['officialUrl']).text
        if not (m:=re.search(r'https://tv\.apple\.com/(?:us/)?show/[^/"\s]+/(umc\.cmc\.[a-z0-9]+)',text)):raise SeasonError('official_show_link_missing')
        return 'https://tv.apple.com/us/show/'+entry['slug']+'/'+m[1],m[1]
    def season(self,row,show_id,params,trusted,cached,latest,fallback=None,size=('960','540')):
        number=row['season'];sid=row['officialId'];ttl=20*3600 if number==latest else 7*86400
        quality_ok=size==('960','540') or bool(cached and cached.get('sourceArtwork','').endswith('/'+'x'.join(size)+'.jpg'))
        if cached and quality_ok and cached.get('officialId')==sid and self.now-cached.get('checkedAt',0)<ttl and self.image_exists(cached.get('artwork','')):
            out=copy.deepcopy(cached)
        else:
            url='https://uts-api.itunes.apple.com/uts/v3/seasons/'+sid+'/metadata?'+urlencode(params)
            try:meta=self.get(url).json()['data']
            except Exception:raise SeasonError('official_season_request_failed') from None
            if meta.get('id')!=sid or meta.get('showId')!=show_id or meta.get('seasonNumber')!=number or meta.get('type')!='Season':raise SeasonError('season_identity_mismatch')
            date=year_date(meta.get('releaseDate'))
            if not date:raise SeasonError('season_release_date_missing')
            image=meta.get('images',{}).get('coverArt16X9',{}).get('url','')
            if not image and fallback and fallback.get('season')==number and fallback.get('year')==date[:4] and self.image_exists(fallback.get('artwork','')):
                # PR inventory explicitly names this season, independently of the UTS image field.
                image=fallback['sourceArtwork'];art=fallback['artwork'];image_checked=self.now
            elif not re.match(r'https://is\d+-ssl\.mzstatic\.com/image/',image):raise SeasonError('season_artwork_missing')
            image=image.replace('{w}',size[0]).replace('{h}',size[1]).replace('{f}','jpg')
            if size!=('960','540') and re.match(r'https://is\d+-ssl\.mzstatic\.com/image/',image):
                image=re.sub(r'/\d+x\d+\.jpg$', '/'+'x'.join(size)+'.jpg',image)
            if '{' in image or '}' in image:raise SeasonError('unknown_artwork_template')
            if fallback and image==fallback.get('sourceArtwork'):
                pass
            elif cached and cached.get('sourceArtwork')==image and self.image_exists(cached.get('artwork','')) and self.now-cached.get('imageCheckedAt',0)<7*86400:
                art=cached['artwork'];image_checked=cached.get('imageCheckedAt',self.now)
            else:
                try:art=self.save_image(self.get(image).content)
                except Exception:raise SeasonError('season_artwork_download_failed') from None
                image_checked=self.now
            out={**row,'showId':show_id,'year':date[:4],'releaseDate':date,'artwork':art,'sourceArtwork':image,
                 'officialUrl':'https://tv.apple.com/us/season/season-'+str(number)+'/'+sid+'?showId='+show_id,
                 'metadataStatus':'verified','checkedAt':self.now,'imageCheckedAt':image_checked}
        out['officialEpisodeCount']=row['officialEpisodeCount']
        valid=next((s for s in trusted if s.get('season')==number and str(s.get('year'))==out['year'] and chinese_summary(s.get('summary'))),{})
        out['summary']=chinese_summary(valid.get('summary'));out['summaryPending']=not bool(out['summary'])
        return out
    def sync(self,entry,seed):
        if entry['kind']!='series':return entry
        slug=entry['slug'];previous=copy.deepcopy(self.cache['shows'].get(slug,{}))
        try:
            watch,show_id=self.watch_url(entry,seed)
            try:options,params,first_date=parse_show(self.get(watch).text,show_id)
            except SeasonError:raise
            except Exception:raise SeasonError('official_show_request_failed') from None
            old={s['season']:s for s in previous.get('seasons',[])}
            trusted=(entry.get('seasons') or [])+(seed.get('seasons') or [])
            artwork_match=re.search(r'/season-(\d+)/',entry.get('sourceArtwork',''))
            artwork_number=int(artwork_match[1]) if artwork_match else int(entry.get('seasonNumber') or 1)
            fallback={'season':artwork_number,'year':year_date(entry.get('releaseDate'))[:4],'artwork':entry.get('artwork',''),'sourceArtwork':entry.get('sourceArtwork','')}
            preferred=self.artwork_preferences.get(slug,{})
            if any(value!='1080p' for value in preferred.values()):raise SeasonError('unsupported_artwork_preference')
            rows=[self.season(s,show_id,params,trusted,old.get(s['season']),options[-1]['season'],fallback,
                              ('1920','1080') if preferred.get(str(s['season']))=='1080p' else ('960','540')) for s in options]
            self.cache['shows'][slug]={'showId':show_id,'watchUrl':watch,'checkedAt':self.now,'seasons':copy.deepcopy(rows)}
            entry['seasons']=public_seasons(rows);entry['seasonStatus']='verified';entry.pop('seasonError',None)
            entry['officialIdentity']={'watchUrl':watch,'year':rows[0]['year']}
            zh=entry.get('zh')
            if zh:zh['_identityYear']=int(rows[0]['year'])
            latest=int(entry.get('seasonNumber') or 1)
            if latest>rows[-1]['season']:
                date=year_date(entry.get('releaseDate'))
                if date and date>datetime.fromtimestamp(self.now,timezone.utc).strftime('%Y-%m-%d'):
                    entry['seasons'].append({'season':latest,'year':date[:4],'releaseDate':date,'summary':'','summaryPending':True,'metadataStatus':'announced'})
            self.report.append({'slug':slug,'status':'verified','seasons':[s['season'] for s in rows],'announced':latest if latest>options[-1]['season'] else None})
        except Exception as exc:
            reason=str(exc) if isinstance(exc,SeasonError) else 'official_metadata_unavailable'
            if previous.get('seasons') and all(self.image_exists(s.get('artwork','')) for s in previous['seasons']):entry['seasons']=public_seasons(previous['seasons'])
            else:entry['seasons']=copy.deepcopy(seed.get('seasons') or entry.get('seasons') or [])
            entry['seasonStatus']='pending';entry['seasonError']=reason
            self.report.append({'slug':slug,'status':'pending','reason':reason,'retainedSeasons':[s['season'] for s in entry['seasons']]})
        # The latest announced season can differ from the season shown on the current PR artwork.
        match=re.search(r'/season-(\d+)/',entry.get('sourceArtwork',''))
        number=int(match[1]) if match else int(entry.get('seasonNumber') or 1)
        date=year_date(entry.get('releaseDate'))
        if entry.get('seasonStatus')=='pending' and number==int(entry.get('seasonNumber') or 1) and date and not any(s['season']==number for s in entry['seasons']):
            entry['seasons'].append({'season':number,'year':date[:4],'releaseDate':date,'artwork':entry.get('artwork',''),'summary':'','summaryPending':True,'metadataStatus':'pending'})
            entry['seasons'].sort(key=lambda s:s['season'])
        entry['artworkSeasonNumber']=number
        displayed=next((s for s in entry.get('seasons',[]) if s['season']==number),{})
        entry['artworkSeasonYear']=displayed.get('year','')
        # Bind hero art to the same season. Untagged historical backdrops must not label another season.
        if displayed.get('artwork'):entry['heroArtwork']=displayed['artwork']
        else:entry['heroArtwork']=entry.get('artwork','')
        entry['heroSeasonNumber']=number
        label_seasons(entry)
        if len(self.report)%20==0:print(json.dumps({'season_progress':len(self.report)}),flush=True)
        return entry
