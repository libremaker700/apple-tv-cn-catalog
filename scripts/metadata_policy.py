"""The active catalog accepts mainland presentation metadata only."""
import copy,re
from urllib.parse import urlsplit
POLICY='mainland-v1'

def allowed_source(url):
    try:
        u=urlsplit(url)
        if u.scheme!='https' or not u.hostname or u.username or u.password:return False
        if u.hostname.endswith(('.hk','.tw')):return False
        if u.hostname=='tv.apple.com':return bool(re.match(r'^/(?:us/)?(?:show|movie)/',u.path))
        if u.hostname.endswith('apple.com') and re.match(r'^/(hk|tw|mo)(/|$)',u.path):return False
        return True
    except ValueError:return False

def clean_zh(value):
    if not isinstance(value,dict) or value.get('metadataPolicy')!=POLICY:return None
    for link in value.get('sources',[]):
        if not allowed_source(link):return None
    for item in value.get('name_sources',[])+value.get('summary_sources',[]):
        if not allowed_source(item.get('url','')):return None
    if value.get('watchUrl') and not allowed_source(value['watchUrl']):return None
    return copy.deepcopy(value)

def clean_entry(entry):
    out=copy.deepcopy(entry);out['zh']=clean_zh(out.get('zh'))
    if out['zh'] is None:
        out.pop('nameStatus',None);out.pop('titleIdentity',None)
    out['chinesePending']=not bool(out['zh'] and out['zh'].get('title'))
    return out
