"""Manual synopsis/genre translation check. No search, title resolution or publication."""
import json,os
from catalog import ROOT
from home_copy import Translator
from api_accounts import accounts
def main():
    translator=Translator('',os.getenv('HOME_COPY_MODEL')or None,max_length=1800)
    report={'role':'synopsis_and_genre_translation_only','configuredAccountNames':[name for name,_ in accounts('GEMINI')],'catalogModified':False}
    try:
        report['translations']=translator.translate([{'id':'synopsis','text':'A detective returns home to investigate a missing person.'},{'id':'genre','text':'影视类型：Crime / Thriller'}]);report['status']='ok'
    except Exception as e:report['status']='unavailable';report['error']=type(e).__name__
    report.update(attempts=getattr(translator,'account_attempts',[]),model=translator.model,http=translator.http)
    (ROOT/'logs').mkdir(exist_ok=True);(ROOT/'logs/translation-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
