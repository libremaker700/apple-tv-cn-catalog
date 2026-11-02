"""Public Plex locale pairs verify name identity; never supply a Douban score."""
import html,json,re
from urllib.parse import urlsplit
from opencc import OpenCC
CC=OpenCC('t2s')

def norm(s):return re.sub(r'[^a-z0-9\u3400-\u9fff]','',re.sub(r'^the\s+','',str(s or''),flags=re.I).casefold())
def document(raw,kind):
    if not isinstance(raw,str):return None
    objects=[]
    for block in re.findall(r'<script[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>',raw,re.S):
        try:
            obj=json.loads(block);objects.extend(obj.get('@graph',[obj]))
        except(ValueError,AttributeError):continue
    rows=[o for o in objects if isinstance(o,dict)and o.get('@type')==('Movie'if kind=='movie'else'TVSeries')]
    titles=re.findall(r'<title>(.*?)</title>',raw,re.S);year=re.search(r'\((19\d{2}|20\d{2})\)',html.unescape(titles[0]))if titles else None
    return (rows[0],year[1])if len(rows)==1 and year else None

def verify(ref,url,zh_raw,en_raw,checked):
    u=urlsplit(url);typ='movie'if ref.get('kind')=='movie'else'show'
    if u.scheme!='https'or u.hostname!='watch.plex.tv'or u.username or u.password or not re.fullmatch('/zh/'+typ+r'/[a-z0-9-]{1,180}',u.path):return None
    z=document(zh_raw,ref['kind']);e=document(en_raw,ref['kind'])
    if not z or not e or z[1]!=e[1]or e[1]!=str(ref['year']):return None
    from douban_mobile import title_queries,work_title
    expected={norm(work_title(t))for t in title_queries(ref['english_title'])}
    if norm(e[0].get('name'))not in expected:return None
    people=lambda d:{norm(p.get('name'))for p in d.get('actor',[])if isinstance(p,dict)and p.get('name')}
    if len(people(z[0])&people(e[0]))<2:return None
    title=CC.convert(z[0].get('name',''))
    if not re.search(r'[\u3400-\u9fff]',title)or len(title)>100:return None
    # A series-wide Plex page verifies a first-season work name only. It cannot
    # relabel a later season or manufacture a season-specific Douban packet.
    if typ=='show'and int(ref.get('season')or 1)!=1:return None
    return {'metadataPolicy':'mainland-v1','display_name_zh':title,'aliases_zh':[title],'name_status':'verified_title_sources','name_checked_at':checked,'sources':[{'type':'plex_public_identity','url':url},{'type':'plex_original_identity','url':url.replace('/zh/','/en/',1)}]}

class PlexNames:
    def __init__(self,pages):self.pages=pages
    def lookup(self,ref,checked,hits=()):
        get=getattr(self.pages,'get',None)
        if not callable(get):return None
        typ='movie'if ref.get('kind')=='movie'else'show';paths=[]
        for hit in hits:
            u=urlsplit(hit.get('url',''))
            if u.hostname=='watch.plex.tv'and re.fullmatch('/zh/'+typ+r'/[a-z0-9-]{1,180}',u.path):paths.append(u.path)
        raw=get('https://watch.plex.tv/zh/search',params={'query':ref['english_title']})
        if isinstance(raw,str):paths+=re.findall(r'href=[\"\'](/zh/'+typ+r'/[a-z0-9-]{1,180})[\"\']',html.unescape(raw))
        matches=[]
        for path in list(dict.fromkeys(paths))[:3]:
            url='https://watch.plex.tv'+path;zh=get(url);en=get(url.replace('/zh/','/en/',1))
            patch=verify(ref,url,zh,en,checked)
            if patch:matches.append(patch)
        return matches[0]if len(matches)==1 else None
