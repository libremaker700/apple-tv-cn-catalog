"""Reviewed Chinese synopses are independent of title verification and playback bindings."""
import copy,json,re
from metadata_policy import POLICY,allowed_source

def valid_summary(value):
    return isinstance(value,str) and 35<=len(value)<=600 and len(re.findall(r'[\u3400-\u9fff]',value))>=20 and not re.search(r'https?://|<[^>]+>',value)

def apply_summary(entry,cached,ident):
    if cached.get('identity')!=ident or cached.get('status')!='verified':return entry
    patch=cached.get('patch') or {};sources=patch.get('summary_sources') or []
    if patch.get('metadataPolicy')!=POLICY or not valid_summary(patch.get('summary_zh')) or not sources or any(not allowed_source(s.get('url','')) for s in sources):return entry
    if re.search(r'[\u3400-\u9fff]',(entry.get('zh') or {}).get('summary','')):return entry
    out=copy.deepcopy(entry);zh=out.get('zh') or {};out['zh']=zh
    out['summaryIdentity']=ident
    zh.update(metadataPolicy=POLICY,summary=patch['summary_zh'],summary_status='verified_summary_sources',summary_sources=sources,summary_checked_at=patch.get('summary_checked_at'))
    if not zh.get('watchUrl'):zh['watchUrl']=(out.get('officialIdentity') or {}).get('watchUrl','')
    return out

def reapply_summaries(catalog,root,identity):
    path=root/'data/summary-cache.json'
    if not path.exists():return catalog
    data=json.loads(path.read_text(encoding='utf8'));assert data.get('schema')==1
    for i,e in enumerate(catalog['entries']):catalog['entries'][i]=apply_summary(e,data.get('records',{}).get(e['slug'],{}),identity(e,{}))
    return catalog
