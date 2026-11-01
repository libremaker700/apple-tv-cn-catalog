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
        if 'seasons' in w:
            assert w['kind']=='series' and 0<len(w['seasons'])<=100
            assert len({s['season']for s in w['seasons']})==len(w['seasons']) and len({s['officialId']for s in w['seasons']})==len(w['seasons'])
            for season in w['seasons']:
                assert type(season['season'])is int and 1<=season['season']<=100 and re.fullmatch(r'umc\.cmc\.[a-z0-9]+',season['officialId']) and re.fullmatch(r'(19|20)\d{2}',str(season['year']))
                assert not any(k in season for k in ('id','sourceIds','headers','token','playUrl','utsk','utscf'))
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

def validate_pages(value):
    from home_pages import page_url
    assert value.get('schema')==3 and value.get('source')==CHANNEL and 3<=len(value['hero'])<=12
    assert 3<=len(value['works'])<=1000 and 1<=len(value['pages'])<=40 and 1<=len(value['shelves'])<=80
    works={};page_ids={p['id']for p in value['pages']};assert len(page_ids)==len(value['pages'])
    for w in value['works']:
        assert re.fullmatch(r'[a-z0-9-]{1,150}',w['slug'])and w['slug']not in works
        assert re.fullmatch(r'umc\.cmc\.[a-z0-9]+',w['officialId'])and w['kind']in('movie','series')and 0<len(w['en'])<=200
        watch_url(w['watchUrl'],w['officialId'],w['kind']);works[w['slug']]=w
        assert not any(k in w for k in ('id','sourceIds','headers','token','playUrl'))
        assert not w.get('year')or re.fullmatch(r'(19|20)\d{2}',str(w['year']))
        if w.get('landscapeArtwork'):assert re.fullmatch(re.escape(BASE)+r'images/[a-f0-9]{64}\.jpg',w['landscapeArtwork'])
        if 'seasons' in w:
            assert w['kind']=='series' and 0<len(w['seasons'])<=100
            assert len({s['season']for s in w['seasons']})==len(w['seasons']) and len({s['officialId']for s in w['seasons']})==len(w['seasons'])
            for season in w['seasons']:
                assert type(season['season'])is int and 1<=season['season']<=100 and re.fullmatch(r'umc\.cmc\.[a-z0-9]+',season['officialId']) and re.fullmatch(r'(19|20)\d{2}',str(season['year']))
                assert not any(k in season for k in ('id','sourceIds','headers','token','playUrl','utsk','utscf'))
        if w.get('zh'):
            from metadata_policy import clean_zh
            from detail_metadata import valid as valid_detail
            zh=w['zh'];assert clean_zh(zh)is not None and zh.get('metadataPolicy')==POLICY and (not zh.get('title')or zh.get('name_status')=='verified_title_sources'and zh.get('name_sources')and all(allowed_source(s.get('url',''))for s in zh['name_sources'])) and all(allowed_source(s.get('url',''))for s in zh.get('summary_sources',[]))
            assert all(valid_detail(packet,w['kind'])for packet in zh.get('detailSeasons',[]))and(not zh.get('detailMetadata')or valid_detail(zh['detailMetadata'],w['kind']))
    def rows(rows,w,h,topics=False):
        seen=set()
        for r in rows:
            identity=r.get('pageId')if topics else r.get('slug');assert identity and identity not in seen;seen.add(identity)
            assert identity in page_ids if topics else r['officialId']==works[identity]['officialId']
            assert (r['width'],r['height'])==(w,h)and re.fullmatch(re.escape(BASE)+r'images/[a-f0-9]{64}\.jpg',r['artwork'])
            assert not any(k in r for k in ('id','sourceIds','headers','token','playUrl'))
            if 'copy'in r:
                from home_copy import validate_copy
                assert not topics and (w,h)==(1920,1080)
                validate_copy(r['officialId'],r['copy'])
    for page in [value]+value['pages']:
        if page is not value:assert re.fullmatch(r'[a-z0-9-]{1,100}',page['id'])and page['title']and page_url(page['source'])==page['source']
        assert len(page['hero'])<=12 and 1<=len(page['shelves'])<=80
        rows(page['hero'],1920,1080)
        for shelf in page['shelves']:
            assert shelf['title']and shelf['officialTitle']and page_url(shelf['source'])==shelf['source']and shelf['layout']in('portrait','landscape')and 0<len(shelf['items'])<=600
            if shelf.get('morePageId'):assert shelf['morePageId']in page_ids
            rows(shelf['items'],*((640,360)if shelf['layout']=='landscape'else(400,600)),shelf.get('kind')=='topics')
    assert value['shelves'][-1]['title']=='即将上线'
    assert len({s['id']for s in value['shelves']})==len(value['shelves'])
    assert all(s['officialTitle']!='Watch Premieres for Free'for p in [value]+value['pages']for s in p['shelves'])
