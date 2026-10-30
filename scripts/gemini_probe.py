"""Manual smoke test; writes only a review report, never the public catalog or credentials."""
import argparse,json,os
from pathlib import Path
from catalog import ROOT,load
from title_lookup import identity
from gemini_titles import GeminiTitles,DEFAULT_MODEL

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--slug',default='being-heumann');parser.add_argument('--model',default=DEFAULT_MODEL);args=parser.parse_args()
    entry=next(e for e in load(ROOT/'docs/catalog.json')['entries'] if e['slug']==args.slug)
    ident=identity(entry,{})
    ref={'english_title':entry['en'],'kind':entry['kind'],'year':ident['year'],'official_url':entry['officialUrl']}
    key=os.getenv('GEMINI_API_KEY','');discovery=GeminiTitles(key).models();available={row['name'] for row in discovery['models'] if 'generateContent' in row['methods']}
    preferred=[args.model,'gemini-3.5-flash-lite','gemini-3.8-flash','gemini-3.6-flash','gemini-3.1-flash-lite','gemini-2.5-flash-lite','gemini-2.5-flash']
    model=next((name for name in preferred if name in available),None)
    ordinary={'status':'model_not_available','api_http':discovery['api_http'],'candidate_titles':[]}
    grounded=dict(ordinary)
    if model:
        client=GeminiTitles(key,model);ordinary=client.search(ref,grounded=False)
        if ordinary['api_http']==200:grounded=client.search(ref)
        else:grounded={'status':'not_attempted_after_plain_failure','api_http':0,'candidate_titles':[]}
    report={'identity':ident,'reference':ref,'model_discovery':discovery,'ordinary':ordinary,'gemini':grounded,
            'catalog_modified':False,'next_step':'Probe these candidate titles through the installed app source matcher; stop if a correct source is found, otherwise try Douban/Wikipedia then Tavily'}
    target=ROOT/'logs/gemini-probe.json';target.parent.mkdir(exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'slug':args.slug,'selected_model':model,'model_list_http':discovery['api_http'],'ordinary':{k:ordinary.get(k) for k in ('status','api_http','api_error_code','candidate_titles')},'search':{k:grounded.get(k) for k in ('status','api_http','api_error_code','grounded','candidate_titles','model_version')}},ensure_ascii=False))
    return 2 if ordinary.get('api_http')!=200 or grounded.get('api_http')!=200 else 0
if __name__=='__main__':raise SystemExit(main())
