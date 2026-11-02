"""Repair a missing PR show identity only from an already verified same-show home entry."""
import copy,re
def reconcile(main,home,slugs):
    homes={w['slug']:w for w in home.get('works',[])if w.get('knownCatalog')};changed=[]
    for w in main.get('entries',[]):
        if w['slug']not in slugs or w.get('kind')!='series'or(w.get('officialIdentity')or{}).get('watchUrl'):continue
        other=homes.get(w['slug'],{});url=other.get('watchUrl','');oid=other.get('officialId','');rows=other.get('seasons',[])
        if other.get('en')!=w['en']or other.get('kind')!='series'or not re.fullmatch(r'https://tv\.apple\.com/us/show/[^/]+/'+re.escape(oid),url)or not re.fullmatch(r'umc\.cmc\.[a-z0-9]+',oid)or not rows or not all(s.get('metadataStatus')=='verified'for s in rows):continue
        chosen=[s for s in rows if s.get('releaseDate')==w.get('releaseDate')and re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(s.get('releaseDate','')))]
        if len(chosen)!=1:continue
        w['officialIdentity']={'watchUrl':url,'year':str(other.get('year')or min(s['year']for s in rows))};w['seasons']=copy.deepcopy(rows)
        for s in w['seasons']:s.update(showId=oid,artwork=w['artwork'],artworkScope='show_fallback',title=w['en']+' 第'+str(s['season'])+'季')
        target=chosen[0];w.update(artworkSeasonNumber=target['season'],artworkSeasonYear=str(target['year']),heroSeasonNumber=target['season'],seasonNumber=target['season'],seasonStatus='verified');w.pop('seasonError',None)
        z=other.get('zh')or{}
        if z.get('name_status')=='verified_title_sources'and z.get('name_sources')and re.search(r'[\u3400-\u9fff]',z.get('title','')):
            dest=w.setdefault('zh',{});dest.update(title=z['title'],aliases=copy.deepcopy(z.get('aliases',[])),name_status='verified_title_sources',name_sources=copy.deepcopy(z['name_sources']),metadataPolicy='mainland-v1',nameOnlyScope='series_name_only')
            for key in ['douban_id','douban_title','detailMetadata','detailSeasons']:dest.pop(key,None)
        changed.append(w['slug'])
    return changed
if __name__=='__main__':
    from catalog import ROOT,load,publish
    main=load(ROOT/'docs/catalog.json');home=load(ROOT/'docs/home/home.json');items=load(ROOT/'data/douban-candidate-review.json')['records']
    changed=reconcile(main,home,[r['slug']for r in items if r.get('slug')])
    if changed:publish(main,load(ROOT/'docs/version.json').get('checked_at'),'verified-home-series-identity-repair')
    print({'reconciled':changed})
