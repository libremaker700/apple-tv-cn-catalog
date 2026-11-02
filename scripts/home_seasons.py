"""Discover actual seasons for channel-only shows absent from the PR inventory."""
import copy, time
from urllib.parse import urlencode
from season_sync import parse_show, year_date
from title_lookup import read, dump


def enrich(home, root, get, now=None):
    now = int(now or time.time())
    path = root / 'data/home-season-cache.json'
    cache = read(path, {'records': {}})
    report = []
    for work in home.get('works', []):
        if work['kind'] != 'series' or work.get('knownCatalog'):
            continue
        identity = work['officialId']
        previous = cache['records'].get(identity, {})
        rows = copy.deepcopy(previous.get('seasons', []))
        status = 'cached'
        if now - previous.get('checkedAt', 0) >= 6 * 3600:
            try:
                options, params, _ = parse_show(get(work['watchUrl']).text, identity,allow_partial=True)
                verified = []
                for option in options:
                    meta = get('https://uts-api.itunes.apple.com/uts/v3/seasons/' + option['officialId'] + '/metadata?' + urlencode(params)).json()['data']
                    date = year_date(meta.get('releaseDate'))
                    if (meta.get('id') != option['officialId'] or meta.get('showId') != identity
                            or meta.get('seasonNumber') != option['season'] or not date):
                        raise ValueError('Season identity/date mismatch')
                    verified.append(dict(option, year=date[:4], releaseDate=date, metadataStatus='verified'))
                rows = verified
                cache['records'][identity] = {'checkedAt': now, 'seasons': rows}
                status = 'verified'
            except Exception:
                # Retain the last complete set; never infer another season from a title.
                status = 'retained' if rows else 'unavailable'
        if rows:
            work['seasons'] = rows
            bind_display_season(work)
        report.append({'officialId': identity, 'status': status, 'seasons': [r['season'] for r in rows]})
    dump(path, cache)
    return report

def bind_display_season(work):
    rows=[s for s in work.get('seasons',[])if s.get('metadataStatus')=='verified']
    exact=[s for s in rows if s.get('releaseDate')==work.get('releaseDate')]
    if len(exact)!=1:exact=[s for s in rows if str(s.get('year'))==str(work.get('year'))]
    if len(exact)==1:
        s=exact[0];work.update(artworkSeasonNumber=s['season'],artworkSeasonYear=str(s['year']),heroSeasonNumber=s['season'],seasonNumber=s['season'])
    return work


def reconcile(home, catalog):
    """Unify a PR show's latest-season year with the same show's first-season identity."""
    from home_pages import name_key
    replacements = {}
    for work in home.get('works', []):
        if work.get('knownCatalog') or not work.get('seasons'):
            continue
        years = {str(s['year']) for s in work['seasons']}
        candidates = [e for e in catalog['entries'] if e['kind'] == work['kind']
                      and name_key(e['en']) == name_key(work['en'])
                      and str(e.get('releaseDate', ''))[:4] in years
                      and not (e.get('officialIdentity') or {}).get('watchUrl', '').startswith('https://tv.apple.com/')]
        if len(candidates) != 1:
            continue
        entry = candidates[0]
        replacements[work['slug']] = entry['slug']
        work['slug'] = entry['slug']
        work['knownCatalog'] = True
    for page in [home] + home.get('pages', []):
        for row in page['hero'] + [r for shelf in page['shelves'] for r in shelf['items']]:
            if row.get('slug') in replacements:
                row['slug'] = replacements[row['slug']]
    return replacements
