"""Reuse strict public-source verification for new homepage works; no AI keys or budget here."""
import copy
from datetime import datetime,timezone
from title_sources import Lookup
from title_lookup import read,dump
def enrich(home,root,now):
    path=root/'data/home-title-cache.json';cache=read(path,{'records':{}});lookup=Lookup(cache_path=root/'data/source-cache.json');attempted=0
    for work in home['works']:
        if work.get('knownCatalog') or not work.get('year'):continue
        key=work['officialId'];old=cache['records'].get(key,{})
        if old.get('en')==work['en'] and old.get('year')==work['year'] and old.get('patch'):
            patch=old['patch']
        elif attempted<5 and now>=old.get('nextRetry',0):
            attempted+=1;ref={'english_title':work['en'],'original_title':work['en'],'kind':'movie'if work['kind']=='movie'else'tv','year':work['year'],'want_summary':True}
            try:patch=lookup.direct(ref,datetime.fromtimestamp(now,timezone.utc).isoformat())
            except Exception:patch=None
            cache['records'][key]={'en':work['en'],'year':work['year'],'patch':patch,'nextRetry':now+86400};dump(path,cache)
        else:patch=None
        if patch:
            work['zh']={'metadataPolicy':'mainland-v1','title':patch['display_name_zh'],'aliases':patch.get('aliases_zh',[]),'summary':patch.get('summary_zh',''),'name_status':'verified_title_sources','name_sources':patch['sources'],'_identityYear':int(work['year'])}
    dump(path,cache)
