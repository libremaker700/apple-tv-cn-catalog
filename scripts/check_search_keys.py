"""Validate configured search keys via the usage endpoint; never print key values or accounts."""
import json,os,requests
results=[];seen=set()
for name in ('TAVILY_API_KEY_1','TAVILY_API_KEY_2','TAVILY_API_KEY'):
    key=os.getenv(name,'').strip()
    if not key or key in seen:continue
    seen.add(key)
    try:r=requests.get('https://api.tavily.com/usage',headers={'Authorization':'Bearer '+key},timeout=(8,20),allow_redirects=False);status=r.status_code
    except requests.RequestException:status=0
    results.append({'secret_name':name,'http_status':status})
print(json.dumps({'key_checks':results}))
