"""Human-reviewed name/alias corrections, separate from resource counts and synopsis translation."""
import copy,re,unicodedata
from urllib.parse import urlsplit
from title_lookup import read
from metadata_policy import allowed_source

def norm(s):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',s).casefold())
def apply(value,root,home=False):
    out=copy.deepcopy(value);records=read(root/'data/reviewed-name-aliases.json',{'records':[]})['records']
    for r in records:
        assert re.fullmatch(r'umc\.cmc\.[a-z0-9]+',r['officialId'])and r['kind']in('movie','series')and 1900<=r['year']<=2099
        assert r['title']and all(isinstance(s,str)and len(s)<=100 for s in r['aliases'])and r['sources']and all(allowed_source(s['url'])for s in r['sources'])
        for w in out.get('works'if home else'entries',[]):
            identity=w.get('officialId')or urlsplit((w.get('officialIdentity')or{}).get('watchUrl','')).path.rstrip('/').split('/')[-1]
            if identity!=r['officialId']:
                if home or w.get('slug')!=r.get('slug') or identity.startswith('umc.cmc.'):continue
                url=r.get('watchUrl','')
                assert re.fullmatch(r'https://tv\.apple\.com/us/(movie|show)/[^/?#]+/'+re.escape(r['officialId']),url)
                w['officialIdentity']={'watchUrl':url,'year':str(r['year'])}

            assert norm(w['en'])==norm(r['en'])and w['kind']==r['kind']
            zh=w.get('zh')or{};w['zh']=zh
            zh.update(metadataPolicy='mainland-v1',title=r['title'],aliases=list(dict.fromkeys([r['title']]+r['aliases']+[r['en']]+zh.get('aliases',[]))),name_status='verified_title_sources',name_sources=r['sources'],provenance='reviewed_name_alias',searchYear=r['year'],_identityYear=r['year'])
            if home and not w.get('year'):w['year']=str(r['year'])
    return out
