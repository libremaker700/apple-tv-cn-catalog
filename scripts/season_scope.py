"""Identity-bound PR subseries scopes; never renumber a verified Apple season."""
import json

def apply(entry,root):
    path=root/'data/season-scopes.json'
    if not path.exists():return entry
    config=json.loads(path.read_text(encoding='utf8'))
    assert config.get('schema')==1
    rule=config.get('works',{}).get(entry['slug'])
    if not rule:return entry
    show=(entry.get('officialIdentity')or{}).get('watchUrl','').rstrip('/').split('/')[-1]
    if entry.get('kind')!='series'or entry.get('en')!=rule['englishTitle']or show!=rule['showId']:
        raise ValueError('Scoped series identity changed: '+entry['slug'])
    row=next((s for s in entry.get('seasons',[])if s.get('season')==rule['season']),{})
    if row.get('metadataStatus')!='verified'or row.get('officialId')!=rule['seasonId']or row.get('showId')!=show or str(row.get('year'))!=rule['year']or row.get('releaseDate')!=rule['releaseDate']:
        raise ValueError('Scoped season identity changed: '+entry['slug'])
    # The PR page restarts its image folders at season-01; Apple TV and Douban
    # identify this as season 3. Keep the real numbering and earlier seasons
    # under the original parent catalog entry rather than relabeling them.
    entry['seasons']=[row]
    entry.update(seasonNumber=rule['season'],artworkSeasonNumber=rule['season'],heroSeasonNumber=rule['season'],artworkSeasonYear=rule['year'],releaseDate=rule['releaseDate'],artwork=row['artwork'],heroArtwork=row['artwork'])
    entry['officialIdentity']['year']=rule['year']
    zh=entry.setdefault('zh',{})or{};entry['zh']=zh
    zh.update(_identityYear=int(rule['year']),officialReleaseYear=int(rule['year']),douban_id=rule['subjectId'])
    zh['sourceSeason']={'policy':'verified-subseries-v1','season':rule['season'],'year':rule['year'],'subjectId':rule['subjectId'],'titles':rule['unnumberedTitles']}
    check=zh.get('sourceCheck')
    if check and (check.get('season')!=rule['season']or str(check.get('year'))!=rule['year']):zh.pop('sourceCheck',None)
    return entry
