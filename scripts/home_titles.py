"""Reuse verified homepage name cache; fresh lookups run only through the You.com pipeline."""
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
        else:patch=None
        if patch:
            work['zh']={'metadataPolicy':'mainland-v1','title':patch['display_name_zh'],'aliases':patch.get('aliases_zh',[]),'summary':patch.get('summary_zh',''),'name_status':'verified_title_sources','name_sources':patch['sources'],'_identityYear':int(work['year'])}
    dump(path,cache)
