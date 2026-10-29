"""Source verification adapted from the Prime Video title lookup. Snippets never define identity."""
import hashlib, re, unicodedata
from urllib.parse import urlsplit, unquote
import requests
def norm(value):
    return re.sub(r'[^a-z0-9\u3400-\u9fff]', '', unicodedata.normalize('NFKC', str(value or '')).casefold())
def chinese(value):
    return isinstance(value, str) and bool(re.search(r'[\u3400-\u9fff]', value))

def year(record):
    value = record.get('details', {}).get('first_air_year') or record.get('year')
    return int(value) if re.fullmatch(r'(19|20)\d{2}', str(value)) else None

def source(kind, url, checked_at):
    return {'type': kind, 'url': url, 'retrieved_at': checked_at}

def mentions_original(title, text):
    title = unicodedata.normalize('NFKC', title or '').casefold()
    text = unicodedata.normalize('NFKC', text).casefold()
    if re.search(r'[a-z]', title):
        words = re.findall(r'\w+', title)
        return bool(words and re.search(r'(?<![a-z0-9])' + r'\W+'.join(map(re.escape, words)) + r'(?![a-z0-9])', text))
    return bool(norm(title) and norm(title) in norm(text))

def wiki_patch(record, page, checked_at):
    """Verify the defining paragraph, never an unrelated mention later in an article."""
    lead = page.get('extract', '').split('\n', 1)[0][:1000]
    names = [record.get(k) for k in ('original_title', 'english_title') if record.get(k)]
    expected = year(record)
    if not names or not expected or not any(mentions_original(n, lead[:500]) for n in names):
        return None
    if str(expected) not in lead:
        return None
    words = {'movie': ('电影', '電影', '影片'), 'tv': ('电视剧', '電視劇', '影集', '剧集', '劇集', '情境喜剧', '情境喜劇', '情景喜剧', '情景喜劇'), 'anime': ('电视动画', '電視動畫', '动画影集', '動畫影集', '动画剧集', '動畫劇集')}.get(record.get('kind'), ())
    title = re.match(r'^《([^》]{1,90})》', lead)
    url = page.get('fullurl', '')
    if not title or not chinese(title[1]) or not any(w in lead for w in words) or urlsplit(url).hostname != 'zh.wikipedia.org':
        return None
    # A combined manga article starts by defining a manga; don't pass it as animation.
    if record.get('kind') == 'anime' and re.search(r'漫画|漫畫', lead[:150]) and not re.search(r'电视动画|電視動畫', lead[:150]):
        return None
    display = title[1]
    old = record.get('display_name_zh', '')
    if chinese(old):
        if norm(old) not in norm(lead):
            return None  # Different regional name: retain old display until reviewed.
        display = old
    return {'display_name_zh': display, 'aliases_zh': [title[1]],
            'name_status': 'verified_title_sources', 'name_checked_at': checked_at,
            'sources': [source('wikipedia_title', url, checked_at)]}

def bangumi_patch(record, subject, checked_at):
    expected = year(record)
    if record.get('kind') != 'anime' or not expected or subject.get('type') != 2 or subject.get('platform') != 'TV':
        return None
    if str(subject.get('date', ''))[:4] != str(expected):
        return None
    # Exact original Japanese/English title; no fuzzy match to manga or another season.
    originals = {norm(record.get(k)) for k in ('original_title', 'english_title')} - {''}
    if norm(subject.get('name')) not in originals or not chinese(subject.get('name_cn')):
        return None
    display = subject['name_cn']
    old = record.get('display_name_zh', '')
    if chinese(old) and norm(old) != norm(display):
        return None
    return {'display_name_zh': display, 'aliases_zh': [display], 'name_status': 'verified_title_sources',
            'name_checked_at': checked_at, 'sources': [source('bangumi_title', f"https://bangumi.tv/subject/{int(subject['id'])}", checked_at)]}

class Lookup:
    def __init__(self, key='', session=None):
        self.key = key
        self.session = session or requests.Session()
        self.requests = 0
        self.network_errors = 0
        self.diagnostics = []
        self.stopped = False

    def get_json(self, url, **kwargs):
        try:
            response = self.session.get(url, headers={'User-Agent': 'AppleTVCnCatalog/1.0 (public title verification)'}, timeout=(8, 20), allow_redirects=False, **kwargs)
            if response.status_code == 200:
                return response.json()
            self.diagnostics.append({'host': urlsplit(url).hostname, 'http_status': response.status_code})
        except (requests.RequestException, ValueError):
            pass
        self.network_errors += 1
        return {}

    def wiki_page(self, record, title, checked_at):
        payload = self.get_json('https://zh.wikipedia.org/w/api.php', params={
            'action': 'query', 'prop': 'extracts|info', 'exintro': 1, 'explaintext': 1,
            'inprop': 'url', 'redirects': 1, 'titles': title, 'format': 'json', 'variant': 'zh-hans'})
        patches = [p for page in payload.get('query', {}).get('pages', {}).values() if (p := wiki_patch(record, page, checked_at))]
        return patches[0] if len(patches) == 1 else None

    def direct(self, record, checked_at):
        title = record.get('english_title') or record.get('original_title')
        hint = {'movie': '电影', 'tv': '电视剧', 'anime': '电视动画'}.get(record.get('kind'), '')
        if record.get('kind') == 'anime':
            original = record.get('original_title') or title
            payload = self.get_json('https://api.bgm.tv/search/subject/' + requests.utils.quote(original, safe=''), params={'type': 2, 'responseGroup': 'small', 'max_results': 5})
            patches = []
            for candidate in payload.get('list', [])[:5]:
                if not str(candidate.get('id', '')).isdigit():
                    continue
                subject = self.get_json(f"https://api.bgm.tv/v0/subjects/{int(candidate['id'])}")
                patch = bangumi_patch(record, subject, checked_at)
                if patch:
                    patches.append(patch)
            if len(patches) == 1:
                return patches[0]
        payload = self.get_json('https://zh.wikipedia.org/w/api.php', params={'action': 'query', 'list': 'search', 'srsearch': f'{title} {hint}', 'srlimit': 2, 'format': 'json'})
        patches = [p for hit in payload.get('query', {}).get('search', []) if (p := self.wiki_page(record, hit['title'], checked_at))]
        return patches[0] if len(patches) == 1 else None

    def search(self, record, checked_at):
        title = record.get('english_title') or record.get('original_title')
        hint = {'movie': '电影', 'tv': '电视剧', 'anime': '电视动画'}.get(record.get('kind'), '')
        query = f'{title} {year(record) or ""} {hint} {record.get("search_name_hint", "")} 中文名 中国大陆译名'.strip()
        # One basic search, no retry or automatic upgrade; caller reserves budget first.
        self.requests += 1
        try:
            response = self.session.post('https://api.tavily.com/search', headers={'Authorization': 'Bearer ' + self.key},
                json={'query': query, 'search_depth': 'basic', 'auto_parameters': False, 'max_results': 6,
                      'include_answer': False, 'include_raw_content': 'text', 'include_images': False, 'include_usage': True,
                      'country': 'china', 'language': 'zh-cn', 'filter_by_language': True,
                      'include_domains': ['zh.wikipedia.org','baike.baidu.com','movie.douban.com','tv.apple.com','bgm.tv'], 'include_domains_mode': 'prefer'},
                timeout=(8, 45), allow_redirects=False)
            if response.status_code != 200:
                self.stopped = True
                return None, {'query': query, 'error': 'HTTP ' + str(response.status_code), 'results': []}
            payload = response.json()
        except (requests.RequestException, ValueError):
            self.stopped = True
            return None, {'query': query, 'error': 'search_unavailable', 'results': []}
        results = []
        for item in payload.get('results', [])[:6]:
            url = item.get('url', '')
            if urlsplit(url).scheme != 'https' or urlsplit(url).username or urlsplit(url).password:
                continue
            results.append({'title': str(item.get('title', ''))[:200], 'url': url, 'score': item.get('score')})
            if urlsplit(url).hostname in ('baike.baidu.com','movie.douban.com') and item.get('raw_content'):
                results[-1]['identity_text'] = str(item['raw_content'])[:14000]
                results[-1]['page_sha256'] = hashlib.sha256(item['raw_content'].encode()).hexdigest()
            if urlsplit(url).hostname == 'zh.wikipedia.org' and item.get('raw_content'):
                # Only the first defining paragraph, not snippets or a later mention.
                paragraphs = [p.strip() for p in str(item['raw_content']).split('\n') if p.strip().startswith('《')]
                if paragraphs:
                    results[-1]['definition'] = paragraphs[0][:1000]
                    results[-1]['page_sha256'] = hashlib.sha256(item['raw_content'].encode()).hexdigest()
        patch = self.verify_results(record, results, checked_at)
        return patch, {'query': query, 'usage': payload.get('usage'), 'results': results,
                       'status': 'verified' if patch else 'pending_review'}

    def verify_results(self, record, results, checked_at):
        patches = []
        for item in results:
            url = item.get('url', '')
            parts = urlsplit(url)
            # Search only locates a page. The page API must independently pass identity gates.
            if parts.hostname == 'zh.wikipedia.org':
                candidate = unquote(parts.path.rsplit('/', 1)[-1])
                patch = wiki_patch(record, {'extract': item.get('definition', ''), 'fullurl': url}, checked_at) or self.wiki_page(record, candidate, checked_at)
                if patch and patch not in patches:
                    patches.append(patch)
            elif parts.hostname in ('bgm.tv', 'bangumi.tv') and re.fullmatch(r'/subject/\d+', parts.path):
                subject = self.get_json('https://api.bgm.tv/v0/subjects/' + parts.path.rsplit('/', 1)[-1])
                patch = bangumi_patch(record, subject, checked_at)
                if patch and patch not in patches:
                    patches.append(patch)
            elif parts.hostname in ('baike.baidu.com','movie.douban.com'):
                patch=structured_patch(record,item,checked_at)
                if patch and patch not in patches:patches.append(patch)
        unique = {norm(p['display_name_zh']) for p in patches}
        return patches[0] if len(unique) == 1 else None

def structured_patch(record,item,checked_at):
    """Verify fields in a fetched Chinese identity page, never a search headline/snippet."""
    raw=item.get('identity_text','');parts=urlsplit(item.get('url',''));expected=year(record)
    english=record.get('english_title') or record.get('original_title') or ''
    if not raw or not expected or not english:return None
    name='';aliases=[]
    if parts.hostname=='movie.douban.com' and re.fullmatch(r'/subject/\d+/?',parts.path):
        head=next((line.strip(' #*') for line in raw[:1800].splitlines() if mentions_original(english,line) and re.search(r'\(\s*'+str(expected)+r'\s*\)',line)), '')
        if not head or re.search(r'第[二三四五六七八九十2-9]+季|Season\s*[2-9]',head,re.I):return None
        # A television subject exposes a first-air field; a movie exposes a release-date field.
        label=r'首播|首播日期' if record.get('kind') in ('tv','anime') else r'上映日期'
        if not re.search(label+r'[^\n]{0,20}(?:\n[^\n]{0,40})?'+str(expected),raw):return None
        match=re.search(r'^(.*?)\s*'+re.escape(english),head,re.I)
        name=match.group(1).strip('《》:： ') if match else ''
        alt=re.search(r'又名\s*[:：]\s*([^\n]{1,250})',raw)
        if alt:aliases=[s.strip() for s in re.split(r'[/、,，;；]',alt.group(1)) if chinese(s)]
        kind='douban_title_fields'
    elif parts.hostname=='baike.baidu.com' and parts.path.startswith('/item/'):
        original=re.search(r'(?:外文名|英文名|原文名)\s*[:：]?\s*(?:\n\s*)?([^\n]{1,120})',raw)
        if not original or norm(original.group(1).strip(' *'))!=norm(english):return None
        label=r'首播时间|首播日期' if record.get('kind') in ('tv','anime') else r'上映时间|上映日期'
        if not re.search(r'(?:'+label+r')\s*[:：]?\s*(?:\n\s*)?'+str(expected),raw):return None
        if record.get('kind') in ('tv','anime') and not re.search(r'电视剧|電視劇|电视动画|电视系列|影集|剧集',raw[:3000]):return None
        if record.get('kind')=='movie' and '电影' not in raw[:3000]:return None
        name=re.sub(r'[_\- ]*(?:百度百科|\(.*?\)|（.*?）).*$', '',item.get('title','')).strip()
        if re.search(r'第[二三四五六七八九十2-9]+季',name):return None
        kind='baidu_title_fields'
    else:return None
    if not chinese(name) or len(name)>80:return None
    from opencc import OpenCC
    cc=OpenCC('t2s');names=list(dict.fromkeys([cc.convert(s) for s in [name]+aliases if chinese(s) and len(s)<80]))
    return {'display_name_zh':cc.convert(name),'aliases_zh':names,'name_status':'verified_title_sources','name_checked_at':checked_at,
            'sources':[source(kind,item['url'],checked_at)]}
