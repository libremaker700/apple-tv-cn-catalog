"""Reuse verified homepage name cache; fresh lookups run only through the You.com pipeline."""
import copy
from datetime import datetime,timezone
from title_sources import Lookup
from title_lookup import read,dump
def remember(home,root):
    from metadata_policy import clean_zh
    path=root/'data/home-title-cache.json';cache=read(path,{'records':{}})
    for w in home.get('works',[]):
        zh=clean_zh(w.get('zh')or{})
        if w.get('knownCatalog')or not w.get('year')or not zh or zh.get('name_status')!='verified_title_sources' or not zh.get('name_sources'):continue
        cache['records'][w['officialId']]={'en':w['en'],'kind':w['kind'],'year':str(w['year']),'verifiedZh':copy.deepcopy(zh)}
    dump(path,cache)
def enrich(home,root,now):
    path=root/'data/home-title-cache.json';cache=read(path,{'records':{}});lookup=Lookup(cache_path=root/'data/source-cache.json');attempted=0
    for work in home['works']:
        if work.get('knownCatalog') or not work.get('year'):continue
        key=work['officialId'];old=cache['records'].get(key,{})
        if old.get('en')==work['en']and old.get('kind')==work['kind']and str(old.get('year'))==str(work['year'])and old.get('verifiedZh'):
            work['zh']=copy.deepcopy(old['verifiedZh']);continue
        if old.get('en')==work['en'] and old.get('year')==work['year'] and old.get('patch'):
            patch=old['patch']
        else:patch=None
        if patch:
            work['zh']={'metadataPolicy':'mainland-v1','title':patch['display_name_zh'],'aliases':patch.get('aliases_zh',[]),'summary':patch.get('summary_zh',''),'name_status':'verified_title_sources','name_sources':patch['sources'],'_identityYear':int(work['year'])}
    dump(path,cache)
