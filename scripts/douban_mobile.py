"""Mobile subject verification, following Prime's lookup endpoints without trusting suggestion type."""
import math,re
from opencc import OpenCC
from metadata_policy import POLICY
CC=OpenCC('t2s')

def norm(s):return re.sub(r'[^a-z0-9\u3400-\u9fff]','',str(s or '').casefold())
def base_title(s):return re.sub(r'\s*(?:第\s*[一1]\s*季|season\s*1)\s*$','',str(s or ''),flags=re.I).strip()

def title_queries(title):
    title=str(title or '').strip()
    short=re.sub(r'\s*\([^()]{1,100}\)\s*$','',title).strip()
    return list(dict.fromkeys(t for t in (title,short) if t))
def mainland_name(s):return isinstance(s,str) and bool(re.search(r'[\u3400-\u9fff]',s)) and not re.search(r'[（(](?:港|台|香港|台湾|臺灣)[）)]',s)
def imdb(data):
    extra=(data.get('attrs') or {}).get('imdb',[])
    values=[data.get('imdb_id','')]+(extra if isinstance(extra,list) else [extra])
    for value in values:
        found=re.search(r'tt\d{7,10}',str(value))
        if found:return found.group()
    return ''

def verify_payload(ref,data,subject_id,endpoint,checked_at):
    if not isinstance(data,dict) or not data.get('title') or data.get('code') or data.get('error'):return None
    if data.get('id') and str(data['id'])!=subject_id:return None
    wanted='movie' if ref.get('kind')=='movie' else 'tv'
    if endpoint!=wanted or data.get('type') not in (wanted,None,''):return None
    if re.search(r'第\s*(?:[2-9]|[1-9]\d|[二三四五六七八九十百]+)\s*季|season\s*(?:[2-9]|[1-9]\d)',str(data['title'])+' '+str(data.get('original_title','')),re.I):return None
    expected={norm(base_title(t)) for t in title_queries(ref.get('english_title') or ref.get('original_title'))}
    aka=data.get('aka') if isinstance(data.get('aka'),list) else []
    originals=[data.get('original_title','')]+aka
    if not expected or not expected.intersection(norm(base_title(s)) for s in originals):return None
    expected_year=str(ref.get('year',''));source_year=str(data.get('year',''))
    if ref.get('imdb_id') and imdb(data) and imdb(data)!=ref['imdb_id']:return None
    if not re.fullmatch(r'(19|20)\d{2}',source_year) or not re.fullmatch(r'(19|20)\d{2}',expected_year):return None
    if source_year!=expected_year and not (ref.get('imdb_id') and imdb(data)==ref['imdb_id']):return None
    name=CC.convert(base_title(data['title']))
    if not mainland_name(name) or len(name)>80:return None
    aliases=list(dict.fromkeys(CC.convert(base_title(s)) for s in [name]+aka if mainland_name(s) and len(s)<80))
    url='https://movie.douban.com/subject/'+subject_id+'/'
    patch={'metadataPolicy':POLICY,'display_name_zh':name,'aliases_zh':aliases,'name_status':'verified_title_sources','name_checked_at':checked_at,'sources':[{'type':'douban_mobile_identity','url':url,'retrieved_at':checked_at}],'douban_id':subject_id,'douban_url':url,'rating_status':'NO_RATING'}
    rating=data.get('rating') or {};value=rating.get('value');count=rating.get('count')
    if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and 0<value<=10 and isinstance(count,int) and not isinstance(count,bool) and count>0:
        patch.update(rating_status='AVAILABLE',douban_rating=value,douban_rating_count=count,rating_checked_at=checked_at)
    if source_year!=expected_year:patch['release_year']=int(source_year)
    # Imported late to avoid a source-lookup import cycle.
    from title_sources import synopsis_patch
    return synopsis_patch(patch,CC.convert(str(data.get('intro',''))),url,checked_at)

class DoubanMobile:
    def __init__(self,pages):self.pages=pages;self.diagnostics=[]
    def subject(self,ref,subject_id,checked_at):
        if not re.fullmatch(r'\d{1,12}',str(subject_id)):return None
        kind='movie' if ref.get('kind')=='movie' else 'tv'
        data=self.pages.json('https://m.douban.com/rexxar/api/v2/'+kind+'/'+str(subject_id))
        patch=verify_payload(ref,data,str(subject_id),kind,checked_at)
        self.diagnostics.append({'stage':'subject','subject_id':str(subject_id),'status':'VERIFIED' if patch else 'UNVERIFIED'})
        return patch
    def lookup(self,ref,checked_at):
        seen=set()
        for title in title_queries(ref.get('english_title') or ref.get('original_title')):
            rows=self.pages.json('https://movie.douban.com/j/subject_suggest',params={'q':title})
            if not isinstance(rows,list):self.diagnostics.append({'stage':'suggest','status':'UNAVAILABLE'});return None
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
        return None
