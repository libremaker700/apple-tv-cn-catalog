"""Remove retired rating-count fields from active metadata; immutable releases stay immutable."""
import argparse,csv,io,json
from pathlib import Path

RETIRED={'ratingCount','rating_count','douban_rating_count'}
def clean(value):
    if isinstance(value,dict):return {key:clean(item)for key,item in value.items()if key not in RETIRED}
    if isinstance(value,list):return [clean(item)for item in value]
    return value

def run(root,publish_changes=True):
    changed=[]
    for name in('data/detail-metadata-cache.json','data/mainland-name-cache.json','data/title-cache.json','data/home-title-cache.json','data/mainland-catalog.json','data/seed.json','docs/title-map.json'):
        path=root/name
        if not path.exists():continue
        value=json.loads(path.read_text(encoding='utf-8-sig'));next_value=clean(value)
        if value!=next_value:path.write_text(json.dumps(next_value,ensure_ascii=False,indent=2)+'\n',encoding='utf8');changed.append(name)
    path=root/'docs/title-map.csv'
    if path.exists():
        rows=csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig')));fields=[key for key in rows.fieldnames if key not in RETIRED];out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows({key:row[key]for key in fields}for row in rows);path.write_text(out.getvalue(),encoding='utf8')
    if publish_changes:
        from catalog import load,publish
        from mainland_names import republish_home
        publish(clean(load(root/'docs/catalog.json')),load(root/'docs/version.json').get('checked_at'),'rating-only-detail-contract')
        republish_home(clean(load(root/'docs/home/home.json')),root)
    return {'changedFiles':changed,'ratingCountPublished':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--no-publish',action='store_true');args=parser.parse_args()
    print(json.dumps(run(Path(__file__).resolve().parents[1],not args.no_publish)))
