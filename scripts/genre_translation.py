"""Translate unknown official genre labels once. Never infer a title or change an identity."""
import hashlib,re
from title_lookup import read,dump

def apply(main,home,root,translator):
    from home_copy import GENRES
    known={k.casefold():v for k,v in GENRES.items()};path=root/'data/genre-translation-cache.json';cache=read(path,{'labels':{}})
    works=main['entries']+home['works'];pending={}
    for work in works:
        for genre in work.get('genres',[]):
            key=str(genre).casefold()
            if key not in known and key not in cache['labels']:pending[key]=str(genre)
    rows=[{'id':hashlib.sha256(k.encode()).hexdigest()[:16],'text':'影视类型：'+v}for k,v in list(pending.items())[:8]]
    if rows:
        try:
            result=translator.translate(rows)
            for key,original in list(pending.items())[:8]:
                identity=hashlib.sha256(key.encode()).hexdigest()[:16];label=re.sub(r'^影视类型\s*[:：]\s*','',result.get(identity,'')).strip()
                if 1<len(label)<=20 and re.fullmatch(r'[\u3400-\u9fff、与及和 ]+',label):cache['labels'][key]=label
        except Exception:pass  # Existing catalog and known labels remain usable.
    dump(path,cache)
    for work in works:
        labels=[known.get(str(g).casefold())or cache['labels'].get(str(g).casefold())for g in work.get('genres',[])]
        if labels and all(labels):work['genresZh']=list(dict.fromkeys(labels))
        else:work.pop('genresZh',None)
    return {'knownLabels':len(known),'translatedUnknownLabels':len(cache['labels']),'pendingUnknownLabels':len(pending)-sum(k in cache['labels']for k in pending)}
