"""Refresh actual season identity for a bounded list of channel-only shows."""
from catalog import ROOT,load,get
from home_seasons import enrich
from mainland_names import republish_home
from title_lookup import dump

def refresh(root=ROOT):
    home=load(root/'docs/home/home.json')
    targets=[w for w in home['works']if w['slug']=='home-4ym1omzf14f4jwcmb7lnu91o0']
    cache_path=root/'data/home-season-cache.json'
    if cache_path.exists():
        cache=load(cache_path)
        for w in targets:
            if w['officialId']in cache.get('records',{}):cache['records'][w['officialId']]['checkedAt']=0
        dump(cache_path,cache)
    report=enrich({'works':targets},root,get)
    republish_home(home,root);dump(root/'logs/identity-season-refresh.json',{'records':report})
    return report
if __name__=='__main__':print(refresh())
