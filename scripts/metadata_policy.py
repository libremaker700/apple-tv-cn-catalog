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
    if 'searchYear'in value and (type(value['searchYear'])is not int or not 1900<=value['searchYear']<=2099 or value.get('name_status')!='verified_title_sources'):return None
    check=value.get('sourceCheck')
    if check is not None:
        if not isinstance(check,dict)or set(check)!=set(('schema','en','kind','season','year','found','routes','checkedAt')):return None
        if check.get('schema')!=1 or not isinstance(check.get('en'),str)or not check['en']or check.get('kind')not in ('movie','series'):return None
        if type(check.get('season'))is not int or not (check['season']==0 if check['kind']=='movie'else 1<=check['season']<=100):return None
        if not re.fullmatch(r'(19|20)\d{2}',str(check.get('year','')))or type(check.get('found'))is not bool or type(check.get('routes'))is not int or not 0<=check['routes']<=1000 or check['found']!=(check['routes']>0)or type(check.get('checkedAt'))is not int or check['checkedAt']<=0:return None
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
