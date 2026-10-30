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
    report={'identity':ident,'reference':ref,'gemini':GeminiTitles(os.getenv('GEMINI_API_KEY',''),args.model).search(ref),
            'catalog_modified':False,'next_step':'Probe these candidate titles through the installed app source matcher; stop if a correct source is found, otherwise try Douban/Wikipedia then Tavily'}
    target=ROOT/'logs/gemini-probe.json';target.parent.mkdir(exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'slug':args.slug,**{k:report['gemini'].get(k) for k in ('status','api_http','api_error_code','grounded','candidate_titles','model_version')}},ensure_ascii=False))
    return 2 if report['gemini']['status'] in ('api_error','missing_api_key','transport_or_json_error') else 0
if __name__=='__main__':raise SystemExit(main())
