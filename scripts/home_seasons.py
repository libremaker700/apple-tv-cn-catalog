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
                options, params, _ = parse_show(get(work['watchUrl']).text, identity)
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
        report.append({'officialId': identity, 'status': status, 'seasons': [r['season'] for r in rows]})
    dump(path, cache)
    return report
