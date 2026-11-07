"""Identity-bound PR subseries scopes; never renumber a verified Apple season."""
import copy,json
from season_sync import base_title,season_synopsis_identity

def work_show_id(work):
    from urllib.parse import urlsplit
    return work.get('officialId') or urlsplit((work.get('officialIdentity')or{}).get('watchUrl','')).path.rstrip('/').split('/')[-1]

def rules(root):
    path=root/'data/season-scopes.json'
    if not path.exists():return {}
    config=json.loads(path.read_text(encoding='utf8'))
    assert config.get('schema')==1
    return config.get('works',{})

def same_family_title(work,title,scopes):
    show=work_show_id(work)
    if work.get('kind')!='series' or not show:return False
    for scoped_slug,rule in scopes.items():
        if show!=rule['showId'] or not rule.get('parentSlug') or not rule.get('parentTitle'):continue
        scoped=(scoped_slug,rule['englishTitle'])
        parent=(rule['parentSlug'],rule['parentTitle'])
        actual=(work.get('slug'),work.get('en'))
        if actual==scoped and title==parent[1] or actual==parent and title==scoped[1]:return True
    return False

def aliases(values):
    return list(dict.fromkeys(value.strip() for value in values if isinstance(value,str) and 0<len(value.strip())<=200))

def apply(entry,root,entries=None):
    rule=rules(root).get(entry['slug'])
    if not rule:return entry
    show=work_show_id(entry)
    if entry.get('kind')!='series'or entry.get('en')!=rule['englishTitle']or show!=rule['showId']:
        raise ValueError('Scoped series identity changed: '+entry['slug'])
    row=next((s for s in entry.get('seasons',[])if s.get('season')==rule['season']),{})
    if row.get('metadataStatus')!='verified'or row.get('officialId')!=rule['seasonId']or row.get('showId')!=show or str(row.get('year'))!=rule['year']or row.get('releaseDate')!=rule['releaseDate']:
        raise ValueError('Scoped season identity changed: '+entry['slug'])
    # Keep the PR installment as the default and borrow only verified seasons
    # from the same Apple show, with the parent's own display and search names.
    parent=(entries or {}).get(rule.get('parentSlug'))
    previous=[]
    if parent and parent.get('en')==rule.get('parentTitle') and parent.get('kind')=='series' and work_show_id(parent)==show:
        parent_title=base_title(parent)
        parent_aliases=aliases([parent_title]+(parent.get('zh')or{}).get('aliases',[]))
        for season in parent.get('seasons',[]):
            identity=season_synopsis_identity(season,show)
            if identity and identity[2]<rule['season'] and season.get('showId')==show and season.get('artwork'):
                previous.append(dict(copy.deepcopy(season),title=parent_title+' 第'+str(identity[2])+'季',
                                     originalTitle=parent['en'],aliases=parent_aliases))
    current_title=base_title(entry)
    current_aliases=aliases([current_title]+rule['unnumberedTitles'])
    row.update(title=current_title+' 第'+str(rule['season'])+'季',originalTitle=entry['en'],aliases=current_aliases)
    entry['seasons']=sorted(previous+[row],key=lambda season:season['season'])
    entry.update(seasonNumber=rule['season'],artworkSeasonNumber=rule['season'],heroSeasonNumber=rule['season'],artworkSeasonYear=rule['year'],releaseDate=rule['releaseDate'],artwork=row['artwork'],heroArtwork=row['artwork'])
    entry['officialIdentity']['year']=rule['year']
    zh=entry.setdefault('zh',{})or{};entry['zh']=zh
    zh.update(_identityYear=int(rule['year']),officialReleaseYear=int(rule['year']),douban_id=rule['subjectId'])
    zh['sourceSeason']={'policy':'verified-subseries-v1','season':rule['season'],'year':rule['year'],'subjectId':rule['subjectId'],'titles':rule['unnumberedTitles']}
    check=zh.get('sourceCheck')
    if check and (check.get('season')!=rule['season']or str(check.get('year'))!=rule['year']):zh.pop('sourceCheck',None)
    return entry
