"""Re-fetch candidate URLs. Model text and model-provided subject IDs are never evidence."""
import re
from urllib.parse import urlsplit,unquote
from douban_mobile import DoubanMobile
from public_sources import plain_html
from title_sources import norm,structured_patch,merge_patches

def verify_candidate(lookup,reference,candidate,checked_at):
    if norm(candidate.get('english_title'))!=norm(reference['english_title']):
        return None,'POSSIBLE_FALSE_POSITIVE'
    urls=candidate.get('sources')
    if not isinstance(urls,list):return None,'UNVERIFIED'
    patches=[]
    for url in list(dict.fromkeys(u for u in urls if isinstance(u,str)))[:4]:
        try:
            p=urlsplit(url)
            if p.scheme!='https' or p.username or p.password or p.port not in (None,443):continue
        except ValueError:continue
        patch=None
        if p.hostname in ('movie.douban.com','m.douban.com'):
            found=re.fullmatch(r'/subject/(\d{1,12})/?',p.path)
            if found:patch=DoubanMobile(lookup.pages).subject(reference,found[1],checked_at)
        elif p.hostname=='zh.wikipedia.org' and p.path.startswith(('/wiki/','/zh-hans/')):
            patch=lookup.wiki_page(reference,unquote(p.path.split('/',2)[2]),checked_at)
        elif p.hostname=='baike.baidu.com' and p.path.startswith('/item/'):
            raw=lookup.pages.get(url)
            if raw:
                heading=re.search(r'(?is)<h1\b[^>]*>(.*?)</h1>',raw)
                patch=structured_patch(reference,{'url':url,'title':plain_html(heading[1]) if heading else '',
                    'identity_text':plain_html(raw)},checked_at)
        if patch:patches.append(patch)
    if not patches:return None,'UNVERIFIED'
    names={norm(p['display_name_zh']) for p in patches}
    if len(names)!=1:return None,'DISPUTED'
    aliases={norm(n) for p in patches for n in [p['display_name_zh']]+p.get('aliases_zh',[])}
    if norm(candidate.get('chinese_title')) not in aliases:return None,'DISPUTED'
    result=patches[0]
    for patch in patches[1:]:result=merge_patches(result,patch)
    return result,'VERIFIED'
