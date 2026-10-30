import re
from home_sources import CHANNEL,ROOM,watch_url
from metadata_policy import POLICY,allowed_source
BASE='https://libremaker700.github.io/apple-tv-cn-catalog/home/'
def validate_home(value):
    assert value.get('schema')==2 and value.get('source')==CHANNEL and value.get('sources')==[CHANNEL,ROOM]
    assert 3<=len(value['hero'])<=12 and 8<=len(value['shelves'])<=20 and 3<=len(value['works'])<=250
    works={}
    for w in value['works']:
        assert re.fullmatch(r'[a-z0-9-]{1,150}',w['slug']) and w['slug'] not in works
        assert re.fullmatch(r'umc\.cmc\.[a-z0-9]+',w['officialId']) and w['kind'] in ('movie','series') and 0<len(w['en'])<=200
        watch_url(w['watchUrl'],w['officialId'],w['kind']);works[w['slug']]=w
        assert not any(k in w for k in ('id','sourceIds','headers','token','playUrl'))
        assert not w.get('year') or re.fullmatch(r'(19|20)\d{2}',str(w['year']))
        if w.get('landscapeArtwork'):assert re.fullmatch(re.escape(BASE)+r'images/[a-f0-9]{64}\.jpg',w['landscapeArtwork'])
        if w.get('zh'):
            zh=w['zh'];assert zh.get('metadataPolicy')==POLICY and zh.get('name_status')=='verified_title_sources' and zh.get('name_sources') and all(allowed_source(s.get('url',''))for s in zh['name_sources'])
    for rows in [value['hero']]+[s['items']for s in value['shelves']]:
        seen=set()
        for row in rows:
            assert row['slug'] not in seen;seen.add(row['slug'])
            assert row['officialId']==works[row['slug']]['officialId']
            assert re.fullmatch(re.escape(BASE)+r'images/[a-f0-9]{64}\.jpg',row['artwork'])
            assert not any(k in row for k in ('id','sourceIds','headers','token','playUrl'))
    for r in value['hero']:assert (r['width'],r['height'])==(1920,1080)
    for s in value['shelves']:
        assert s['source'] in (CHANNEL,ROOM) and s['layout']=='portrait' and s.get('officialTitle') and s.get('title') and 0<len(s['items'])<=100
        for r in s['items']:assert (r['width'],r['height'])==(400,600) and r['rank']>0
