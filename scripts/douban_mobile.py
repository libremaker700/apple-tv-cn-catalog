"""Mobile subject verification, following Prime's lookup endpoints without trusting suggestion type."""
import html,math,re
from opencc import OpenCC
from metadata_policy import POLICY
from release_identity import title_number_key,regional_date,subject_with_dates
CC=OpenCC('t2s')

def norm(s):return re.sub(r'[^a-z0-9\u3400-\u9fff]','',re.sub(r'(?<=[a-z])\s*&\s*(?=[a-z])',' and ',str(s or '').casefold()))
def base_title(s):return re.sub(r'\s*(?:第\s*[一1]\s*季|season\s*1)\s*$','',str(s or ''),flags=re.I).strip()
def subject_season(text):
    """An unnumbered TV subject is season one; explicit later seasons must match."""
    found=re.findall(r'第\s*([0-9一二三四五六七八九十百]+)\s*季|season\s*(\d+)',str(text or''),re.I)
    if not found:return 1
    def number(pair):
        word=pair[0]or pair[1]
        if word.isdigit():return int(word)
        digits='零一二三四五六七八九';pos=word.find('十')
        if word=='一百':return 100
        if pos>=0:return(1 if pos==0 else digits.index(word[0]))*10+(digits.index(word[-1])if pos<len(word)-1 else 0)
        return digits.index(word)
    try:values={number(pair)for pair in found}
    except ValueError:return None
    return next(iter(values))if len(values)==1 else None
def work_title(text):return re.sub(r'\s*(?:第\s*[0-9一二三四五六七八九十百]+\s*季|season\s*\d+)\s*$','',str(text or''),flags=re.I).strip()

def title_queries(title):
    title=str(title or '').strip()
    short=re.sub(r'\s*\([^()]{1,100}\)\s*$','',title).strip()
    native=re.search(r'\(([^()]{2,100})\)\s*$',title)
    return list(dict.fromkeys(t for t in (title,short,native[1]if native else'') if t))
def mainland_name(s):return isinstance(s,str) and bool(re.search(r'[\u3400-\u9fff]',s)) and not re.search(r'[（(](?:港|台|香港|台湾|臺灣)(?:[/／、·和及](?:港|台|香港|台湾|臺灣))*[）)]',s)
def imdb(data):
    extra=(data.get('attrs') or {}).get('imdb',[])
    values=[data.get('imdb_id','')]+(extra if isinstance(extra,list) else [extra])
    for value in values:
        found=re.search(r'tt\d{7,10}',str(value))
        if found:return found.group()
    return ''

def verify_payload(ref,data,subject_id,endpoint,checked_at,identity_only=False):
    if not isinstance(data,dict) or not data.get('title') or data.get('code') or data.get('error'):return None
    if data.get('id') and str(data['id'])!=subject_id:return None
    wanted='movie' if ref.get('kind')=='movie' else 'tv'
    if endpoint!=wanted or data.get('type') not in (wanted,None,''):return None
    season=0 if wanted=='movie'else int(ref.get('season')or 1)
    if wanted=='tv'and subject_season(str(data['title'])+' '+str(data.get('original_title','')))!=season:return None
    expected={norm(work_title(t)) for t in title_queries(ref.get('english_title') or ref.get('original_title'))}
    if str(subject_id)in ref.get('candidate_subject_ids',[]):expected.update(norm(work_title(t))for t in ref.get('candidate_original_titles',[]))
    aka=data.get('aka') if isinstance(data.get('aka'),list) else []
    originals=[data.get('original_title','')]+aka+[data.get('title','')]
    if ref.get('douban_id')and str(ref['douban_id'])!=str(subject_id):return None
    exact=bool(expected.intersection(norm(work_title(s))for s in originals))
    regional=regional_date(ref,data.get('_full_pubdate',data.get('pubdate',[])))
    shared_id=bool(ref.get('imdb_id')and imdb(data)==ref['imdb_id']or ref.get('douban_id')and str(ref['douban_id'])==str(subject_id))
    numeric={title_number_key(work_title(t))for t in title_queries(ref.get('english_title')or ref.get('original_title'))}
    numeric_match=bool(numeric.intersection(title_number_key(work_title(s))for s in originals))
    if not expected or not(exact or numeric_match and(regional or shared_id)):return None
    expected_year=str(ref.get('year',''));source_year=str(data.get('year',''))
    if ref.get('imdb_id') and imdb(data) and imdb(data)!=ref['imdb_id']:return None
    if not re.fullmatch(r'(19|20)\d{2}',source_year) or not re.fullmatch(r'(19|20)\d{2}',expected_year):return None
    if source_year!=expected_year and not (ref.get('imdb_id') and imdb(data)==ref['imdb_id'])and not regional:return None
    if identity_only:
        people=lambda key:[CC.convert(str(v.get('name','')if isinstance(v,dict)else v))for v in data.get(key,[])if isinstance(v,(str,dict))][:30]
        return {'douban_id':str(subject_id),'title':CC.convert(work_title(data['title'])),'originalTitle':data.get('original_title',''),'aliases':[CC.convert(work_title(s))for s in aka if mainland_name(s)and len(s)<80],'year':source_year,'season':season,'actors':people('actors'),'directors':people('directors'),'url':'https://movie.douban.com/subject/'+str(subject_id)+'/'}
    name=CC.convert(work_title(data['title']))
    if not mainland_name(name):
        name=next((CC.convert(work_title(s))for s in aka if mainland_name(s)and len(s)<80),'')
    if not mainland_name(name) or len(name)>80:return None
    aliases=list(dict.fromkeys(CC.convert(work_title(s)) for s in [name]+aka if mainland_name(s) and len(s)<80))
    url='https://movie.douban.com/subject/'+subject_id+'/'
    patch={'metadataPolicy':POLICY,'display_name_zh':name,'aliases_zh':aliases,'name_status':'verified_title_sources','name_checked_at':checked_at,'sources':[{'type':'douban_mobile_identity','url':url,'retrieved_at':checked_at}],'douban_id':subject_id,'douban_url':url,'rating_status':'NO_RATING'}
    rating=data.get('rating') or {};value=rating.get('value')
    if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and 0<value<=10:
        patch.update(rating_status='AVAILABLE',douban_rating=value,rating_checked_at=checked_at)
    def people(key):
        rows=data.get(key)or[]
        if not isinstance(rows,list):return []
        values=[CC.convert(str(row.get('name')or''))if isinstance(row,dict)else CC.convert(row)for row in rows if isinstance(row,(str,dict))]
        return list(dict.fromkeys(value.strip()for value in values if value.strip()))[:30]
    patch['actors']=people('actors');patch['directors']=people('directors')
    if regional:patch['release_date_evidence']={'sourceUrl':url,'dates':data.get('_full_pubdate',data.get('pubdate',[])),'platformReleaseDate':ref['release_date'],'originalYear':int(source_year),'basis':data.get('_release_date_basis','douban_subject_dates')}
    if source_year!=expected_year:patch['release_year']=int(source_year)
    # Imported late to avoid a source-lookup import cycle.
    from title_sources import synopsis_patch
    patch=synopsis_patch(patch,CC.convert(str(data.get('intro',''))),url,checked_at)
    from detail_metadata import from_patch
    packet=from_patch(patch,dict(ref,season=season))
    if packet:patch['detailMetadata']=packet
    return patch

class DoubanMobile:
    def __init__(self,pages):self.pages=pages;self.diagnostics=[];self.identities={}
    def subject(self,ref,subject_id,checked_at):
        if not re.fullmatch(r'\d{1,12}',str(subject_id)):return None
        kind='movie' if ref.get('kind')=='movie' else 'tv'
        data=self.pages.json('https://m.douban.com/rexxar/api/v2/'+kind+'/'+str(subject_id))
        data=subject_with_dates(ref,data,subject_id,self.pages)
        patch=verify_payload(ref,data,str(subject_id),kind,checked_at)
        if not patch:
            from candidate_name_rules import name_only
            patch=name_only(ref,data,str(subject_id),checked_at)
        identity=verify_payload(ref,data,str(subject_id),kind,checked_at,identity_only=True)
        if identity:self.identities[str(subject_id)]=identity
        self.diagnostics.append({'stage':'subject','subject_id':str(subject_id),'status':'VERIFIED'if patch else'IDENTITY_VERIFIED_NO_CHINESE_NAME'if identity else'UNVERIFIED'})
        return patch
    def lookup(self,ref,checked_at):
        seen=set()
        patches=[]
        for sid in list(dict.fromkeys(ref.get('candidate_subject_ids',[])))[:3]:
            if not re.fullmatch(r'\d{1,12}',str(sid)):continue
            sid=str(sid);seen.add(sid);patch=self.subject(ref,sid,checked_at)
            if patch:patches.append(patch)
        names={norm(p['display_name_zh'])for p in patches}
        if len(names)==1:return patches[0]
        if len(names)>1:return None
        queries=title_queries(ref.get('english_title') or ref.get('original_title'))
        if ref.get('kind')!='movie'and int(ref.get('season')or 1)>1:
            queries=[title+' Season '+str(ref['season'])for title in queries]
        hint=work_title(ref.get('display_name_zh',''))
        if mainland_name(hint):
            n=int(ref.get('season')or 1);digits='零一二三四五六七八九'
            word=digits[n]if n<10 else('一百'if n==100 else('十'if n<20 else digits[n//10]+'十')+(digits[n%10]if n%10 else''))
            localized=hint+(' 第'+word+'季'if ref.get('kind')!='movie'else'')
            queries=queries[:1]+[localized]+queries[1:]
        for title in queries[:2]:
            rows=self.pages.json('https://movie.douban.com/j/subject_suggest',params={'q':title})
            if not isinstance(rows,list):self.diagnostics.append({'stage':'suggest','status':'UNAVAILABLE'});break
            if not rows:self.diagnostics.append({'stage':'suggest','status':'EMPTY_RESPONSE'});continue
            patches=[]
            for row in rows[:3]:
                if not isinstance(row,dict):continue
                sid=str(row.get('id',''))
                if not re.fullmatch(r'\d{1,12}',sid) or sid in seen:continue
                seen.add(sid);patch=self.subject(ref,sid,checked_at)
                if patch:patches.append(patch)
            names={norm(p['display_name_zh']) for p in patches}
            if len(names)==1:return patches[0]
            if len(names)>1:return None
        # The public mobile search page is a separate supported search surface.
        # Its movie links are candidates only: every subject must still pass
        # the same original-title/year/medium/season verification above.
        getter=getattr(self.pages,'get',None)
        if not callable(getter):return None
        for title in queries[:2]:
            raw=getter('https://m.douban.com/search/',params={'query':title})
            if not isinstance(raw,str):continue
            ids=list(dict.fromkeys(re.findall(r'href=[\"\'](?:https://m\.douban\.com)?/movie/subject/(\d+)/?[\"\']',html.unescape(raw))))[:3]
            self.diagnostics.append({'stage':'mobile_search','candidates':len(ids)})
            patches=[]
            for sid in ids:
                if sid in seen:continue
                seen.add(sid);patch=self.subject(ref,sid,checked_at)
                if patch:patches.append(patch)
            names={norm(p['display_name_zh'])for p in patches}
            if len(names)==1:return patches[0]
            if len(names)>1:return None
        return None
