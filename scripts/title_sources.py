"""Source verification adapted from the Prime Video title lookup. Snippets never define identity."""
import hashlib, re, unicodedata
from urllib.parse import urlsplit, unquote
import requests
from metadata_policy import POLICY,allowed_source
from summary_cache import valid_summary
from public_sources import PublicPages,plain_html

def complete_patch(patch,record):
    return bool(patch and (record.get('name_verified') or chinese(patch.get('display_name_zh'))) and (not record.get('want_summary') or valid_summary(patch.get('summary_zh'))))

def merge_patches(first,second):
    if not first:return second
    if not second:return first
    # Each patch has independently passed the original-title, type and identity gates.
    out=dict(first)
    if norm(first.get('display_name_zh')) in {norm(n) for n in [second.get('display_name_zh','')]+second.get('aliases_zh',[])}:
        for key in ('douban_id','douban_url','rating_status','douban_rating','douban_rating_count','rating_checked_at'):
            if key in second:out[key]=second[key]
    if not valid_summary(out.get('summary_zh')) and valid_summary(second.get('summary_zh')):
        out.update({k:second[k] for k in ('summary_zh','summary_sources','summary_checked_at') if k in second})
    return out

def synopsis_patch(patch,text,url,checked_at):
    """Only attach a Chinese synopsis after the containing page passed identity gates."""
    text=re.sub(r'\[\d+\]|<[^>]*>','',str(text or ''))
    text=re.sub(r'\s+',' ',text).strip()[:600]
    if valid_summary(text):patch.update(summary_zh=text,summary_sources=[source('verified_page_synopsis',url,checked_at)],summary_checked_at=checked_at)
    return patch

def plot_section(raw):
    match=re.search(r'(?:^|\n)[ \t]*(?:[#=]{1,4}[ \t]*)?(?:[^\n]{1,80}的)?(?:剧情简介|剧情梗概|剧情|故事梗概)[ \t·:：=]*\n+([\s\S]*?)(?=\n[ \t]*(?:[#=]{1,4}\s+|演职员|演员表|角色介绍|短评|获奖|参考资料|播出信息|分集剧情)|\Z)',raw)
    return match.group(1).strip()[:600] if match else ''
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
    display=page.get('mainland_title','')
    if not chinese(display) and record.get('name_verified'):display=record.get('display_name_zh','')
    if not chinese(display):return None
    return synopsis_patch({'display_name_zh': display, 'aliases_zh': [display], 'metadataPolicy':POLICY,
            'name_status': 'verified_title_sources', 'name_checked_at': checked_at,
            'sources': [source('wikipedia_mainland_title', url, checked_at)]},plot_section(page.get('extract','')) or lead,url,checked_at)

def bangumi_patch(record, subject, checked_at):
    expected = year(record)
    if record.get('kind') != 'anime' or not expected or subject.get('type') != 2 or subject.get('platform') not in ('TV','WEB'):
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
    url=f"https://bangumi.tv/subject/{int(subject['id'])}"
    return synopsis_patch({'display_name_zh': display, 'aliases_zh': [display], 'metadataPolicy':POLICY, 'name_status': 'verified_title_sources',
            'name_checked_at': checked_at, 'sources': [source('bangumi_title',url,checked_at)]},subject.get('summary',''),url,checked_at)

class Lookup:
    def __init__(self, key='', session=None, cache_path=None):
        self.key = key
        self.session = session or requests.Session()
        self.requests = 0
        self.network_errors = 0
        self.diagnostics = []
        self.stopped = False
        self.pages=PublicPages(self.session,cache_path)
        self.stages=[]

    def get_json(self, url, **kwargs):
        return self.pages.json(url,**kwargs) if allowed_source(url) else {}

    def douban(self,record,checked_at):
        from douban_mobile import DoubanMobile
        lookup=DoubanMobile(self.pages);patch=lookup.lookup(record,checked_at)
        self.diagnostics.extend(lookup.diagnostics)
        return patch

    def wiki_page(self, record, title, checked_at):
        payload = self.get_json('https://zh.wikipedia.org/w/api.php', params={
            'action': 'query', 'prop': 'extracts|info|revisions', 'rvprop':'content', 'rvslots':'main', 'exchars': 5000, 'explaintext': 1,
            'inprop': 'url', 'redirects': 1, 'titles': title, 'format': 'json', 'variant': 'zh-hans'})
        patches=[]
        for page in payload.get('query',{}).get('pages',{}).values():
            revision=(page.get('revisions') or [{}])[0];raw=revision.get('slots',{}).get('main',{}).get('*',revision.get('*',''))
            field=re.search(r'\|\s*(?:cn_name|中国大陆片名|中國大陸片名|中国大陆|中國大陸)\s*=\s*([^\n|<]{1,80})',raw,re.I)
            if field:page['mainland_title']=field.group(1).strip(' 《》[]*')
            patch=wiki_patch(record,page,checked_at)
            if patch:patches.append(patch)
        return patches[0] if len(patches) == 1 else None

    def wikipedia(self, record, checked_at):
        title = record.get('english_title') or record.get('original_title')
        hint = {'movie': '电影', 'tv': '电视剧', 'anime': '电视动画'}.get(record.get('kind'), '')
        payload = self.get_json('https://zh.wikipedia.org/w/api.php', params={'action': 'query', 'list': 'search', 'srsearch': f'{title} {hint}', 'srlimit': 2, 'format': 'json'})
        patches = [p for hit in payload.get('query', {}).get('search', []) if (p := self.wiki_page(record, hit['title'], checked_at))]
        return patches[0] if len(patches) == 1 else None

    def direct(self,record,checked_at):
        self.stages=[]
        patch=self.douban(record,checked_at);self.stages.append({'source':'douban','name':bool(patch),'synopsis':bool(patch and patch.get('summary_zh'))})
        if complete_patch(patch,record):return patch
        wiki=self.wikipedia(record,checked_at);self.stages.append({'source':'wikipedia','name':bool(wiki),'synopsis':bool(wiki and wiki.get('summary_zh'))})
        return merge_patches(patch,wiki)

    def search(self, record, checked_at):
        title = record.get('english_title') or record.get('original_title')
        hint = {'movie': '电影', 'tv': '电视剧', 'anime': '电视动画'}.get(record.get('kind'), '')
        query = f'{title} {year(record) or ""} {hint} {record.get("search_name_hint", "")} 中文名 中国大陆译名 剧情简介'.strip()
        # One basic search, no retry or automatic upgrade; caller reserves budget first.
        self.requests += 1
        try:
            response = self.session.post('https://api.tavily.com/search', headers={'Authorization': 'Bearer ' + self.key},
                json={'query': query, 'search_depth': 'basic', 'auto_parameters': False, 'max_results': 6,
                      'include_answer': False, 'include_raw_content': 'text', 'include_images': False, 'include_usage': True,
                      'country': 'china', 'language': 'zh-cn', 'filter_by_language': True,
                      'include_domains': ['zh.wikipedia.org','baike.baidu.com','movie.douban.com','bgm.tv'], 'include_domains_mode': 'prefer'},
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
            if not allowed_source(url):
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
            if not allowed_source(url):continue
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
        if len(unique)!=1:return None
        # Keep matching names consistent; prefer the verified page with a usable synopsis.
        return next((p for p in patches if p.get('summary_zh')),patches[0])

def structured_patch(record,item,checked_at):
    """Verify fields in a fetched Chinese identity page, never a search headline/snippet."""
    raw=item.get('identity_text','');parts=urlsplit(item.get('url',''));expected=year(record)
    english=record.get('english_title') or record.get('original_title') or ''
    if not raw or not expected or not english:return None
    name='';aliases=[];source_year=str(expected)
    if parts.hostname=='movie.douban.com' and re.fullmatch(r'/subject/\d+/?',parts.path):
        head=next((line.strip(' #*') for line in raw[:1800].splitlines() if mentions_original(english,line) and re.search(r'\(\s*(?:19|20)\d{2}\s*\)',line)), '')
        if not head or re.search(r'第[二三四五六七八九十2-9]+季|Season\s*[2-9]',head,re.I):return None
        source_year=re.search(r'\(\s*((?:19|20)\d{2})\s*\)',head)[1]
        # Release postponements can change years; an independently known exact IMDb ID is required.
        if source_year!=str(expected) and (not re.fullmatch(r'tt\d{7,10}',record.get('imdb_id','')) or not re.search(r'(?i)IMDb\s*[:：]?\s*'+re.escape(record['imdb_id'])+r'\b',raw)):return None
        # A television subject exposes a first-air field; a movie exposes a release-date field.
        label=r'首播|首播日期' if record.get('kind') in ('tv','anime') else r'上映日期'
        if not re.search(label+r'[^\n]{0,20}(?:\n[^\n]{0,40})?'+source_year,raw):return None
        match=re.search(r'^(.*?)\s*'+re.escape(english),head,re.I)
        name=match.group(1).strip('《》:： ') if match else ''
        alt=re.search(r'又名\s*[:：]\s*([^\n]{1,250})',raw)
        if alt:aliases=[s.strip() for s in re.split(r'[/、,，;；]',alt.group(1)) if chinese(s) and not re.search(r'[（(](?:港|台|香港|台湾|臺灣)[）)]',s)]
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
    patch=synopsis_patch({'display_name_zh':cc.convert(name),'aliases_zh':names,'metadataPolicy':POLICY,'name_status':'verified_title_sources','name_checked_at':checked_at,
            'sources':[source(kind,item['url'],checked_at)]},cc.convert(plot_section(raw)),item['url'],checked_at)
    if source_year!=str(expected):patch['release_year']=int(source_year)
    return patch
