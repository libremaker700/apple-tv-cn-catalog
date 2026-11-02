"""Narrow, evidence-bound handling of one-off specials and explicitly named editions."""
import re
def apply_kind(work,hint):
    e=hint.get('canonicalKindEvidence')or{};url=(work.get('officialIdentity')or{}).get('watchUrl')or work.get('watchUrl','')
    if hint.get('englishTitle')!=work.get('en')or e.get('kind')!='movie'or e.get('officialUrl')!=url or not re.fullmatch(r'https://tv\.apple\.com/us/movie/[^/]+/'+re.escape(hint.get('officialId','')),url)or e.get('releaseDate')!=work.get('releaseDate')or e.get('subjectId')not in hint.get('candidateSubjectIds',[]):return False
    if any(s.get('metadataStatus')=='verified'for s in work.get('seasons',[])):return False
    work.update(kind='movie',seasons=[],seasonNumber=0,kindPolicy='official-movie-identity-v1')
    for k in ['artworkSeasonNumber','artworkSeasonYear','heroSeasonNumber','seasonError','seasonStatus']:work.pop(k,None)
    return True
def name_only(ref,data,sid,checked):
    from douban_mobile import norm,mainland_name,CC
    rule=ref.get('candidate_name_rule')or{}
    if str(sid)not in ref.get('candidate_subject_ids',[])or not isinstance(data,dict)or ref.get('kind')!='movie'or not mainland_name(data.get('title','')):return None
    url='https://movie.douban.com/subject/'+str(sid)+'/'
    name=CC.convert(data['title']);scope=None
    if rule.get('policy')=='single_episode_special'and data.get('type')=='tv'and data.get('episodes_count')==1 and str(data.get('year'))==str(ref.get('year'))and norm(data.get('original_title'))==norm(ref.get('english_title')):
        from release_identity import regional_date
        if regional_date(ref,data.get('pubdate',[])):scope='single_episode_special'
    if rule.get('policy')=='director_cut'and data.get('type')=='movie'and str(data.get('year'))==str(rule.get('originalYear'))and str(ref.get('year'))==str(rule.get('platformYear')):
        base=re.sub(r':\s*(?:The\s+)?Director[’\x27]s Cut$','',ref.get('english_title',''),flags=re.I)
        minutes=rule.get('editionMinutes');added=ref.get('edition_added_minutes')
        versions=data.get('durations',[]);base_time=re.fullmatch(r'(\d+)分钟',versions[0])if versions else None
        version=any(re.fullmatch(str(minutes)+r'分钟[（(]导演剪辑版[）)]',v)for v in versions)
        if base!=ref.get('english_title')and norm(base)==norm(data.get('original_title'))and version and type(added)is int and base_time and int(base_time[1])+added==minutes:name+='：导演剪辑版';scope='director_cut'
    if not scope:return None
    return {'metadataPolicy':'mainland-v1','display_name_zh':name,'aliases_zh':[name],'name_status':'verified_title_sources','name_checked_at':checked,'name_only_scope':scope,'sources':[{'type':'douban_'+scope+'_name_only','url':url,'retrieved_at':checked}]}
