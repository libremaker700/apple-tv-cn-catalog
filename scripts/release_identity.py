"""Supplement truncated release dates without relaxing work or season identity."""
import copy,re
from datetime import date
from html.parser import HTMLParser
NUMBERS=dict(zip('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'.split(),range(21)))
def title_number_key(text):
    value=re.sub(r'\b('+ '|'.join(NUMBERS)+r')\b',lambda m:str(NUMBERS[m[0].casefold()]),str(text or''),flags=re.I)
    return re.sub(r'[^a-z0-9\u3400-\u9fff]','',value.casefold())
def iso(text):
    try:return date.fromisoformat(text).isoformat()if re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(text))else None
    except ValueError:return None
def regional_date(ref,dates):
    expected=ref.get('release_date')
    if ref.get('kind')!='movie'or ref.get('release_region')!='US'or not iso(expected)or expected[:4]!=str(ref.get('year')):return False
    for row in dates if isinstance(dates,list)else[]:
        m=re.fullmatch(r'(\d{4}-\d{2}-\d{2})\s*[（(]\s*(美国|美国上映|美国公映|USA|US)\s*[）)]',str(row),re.I)
        if m and iso(m[1])==expected:return True
    return False
class Dates(HTMLParser):
    def __init__(self):super().__init__();self.subject='';self.depth=0;self.parts=[];self.values=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='meta'and a.get('property')=='og:url':self.subject=a.get('content','')
        if tag=='link'and a.get('rel')=='canonical':self.subject=a.get('href','')
        if self.depth:self.depth+=1
        elif tag=='span'and a.get('property')=='v:initialReleaseDate':self.depth=1;self.parts=[]
    def handle_data(self,text):
        if self.depth:self.parts.append(text)
    def handle_endtag(self,tag):
        if self.depth:
            self.depth-=1
            if not self.depth:self.values.append(''.join(self.parts).strip())
def page_dates(raw,subject_id):
    if not isinstance(raw,str):return []
    parser=Dates();parser.feed(raw)
    return parser.values[:30]if parser.subject=='https://movie.douban.com/subject/'+str(subject_id)+'/'else[]
def subject_with_dates(ref,data,sid,pages):
    if not isinstance(data,dict)or ref.get('kind')!='movie':return data
    out=copy.deepcopy(data);dates=out.get('pubdate')if isinstance(out.get('pubdate'),list)else[]
    e=ref.get('release_date_evidence')or{}
    # Explicitly confirmed evidence must still match the current subject payload.
    if e.get('subjectId')==str(sid)and e.get('sourceUrl')=='https://movie.douban.com/subject/'+str(sid)+'/'and e.get('confirmedBy')=='user'and e.get('originalTitle')==data.get('original_title')and e.get('originalYear')==str(data.get('year'))and e.get('officialReleaseDate')==ref.get('release_date')and e.get('dates')and e['dates'][0]in dates:
        dates=list(dict.fromkeys(dates+e['dates']));out['_release_date_basis']='user_confirmed_subject_dates'
    if not regional_date(ref,dates)and str(data.get('year'))!=str(ref.get('year')):
        get=getattr(pages,'get',None)
        if callable(get):
            extra=page_dates(get('https://movie.douban.com/subject/'+str(sid)+'/'),sid)
            if extra:dates=list(dict.fromkeys(dates+extra));out['_release_date_basis']='douban_full_subject_dates'
    out['_full_pubdate']=dates
    return out
