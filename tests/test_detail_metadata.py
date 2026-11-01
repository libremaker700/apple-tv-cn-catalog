import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from douban_mobile import verify_payload,DoubanMobile
from detail_metadata import valid,from_patch,attach,remember,apply_cached
from metadata_policy import clean_zh

SUMMARY='第六季的间谍团队面临全新的秘密任务，老成员与新成员需要一起调查幕后势力，在行动过程中找出隐藏的真相并保护同伴。'
NOW='2026-11-01T03:00:00+00:00'
REF={'english_title':'Slow Horses','kind':'tv','year':'2026','season':6}
SUBJECT={'id':'37234567','title':'流人 第六季','original_title':'Slow Horses Season 6','type':'tv','year':'2026','intro':SUMMARY,'aka':[],'rating':{'value':9.1,'count':1234}}

class AtomicDetails(unittest.TestCase):
    def packet(self):return verify_payload(REF,SUBJECT,'37234567','tv',NOW)['detailMetadata']
    def test_one_subject_response_produces_title_summary_rating_packet(self):
        packet=self.packet();self.assertTrue(valid(packet,'series'))
        self.assertEqual((packet['title'],packet['summary'],packet['rating']),('流人',SUMMARY,9.1));self.assertNotIn('ratingCount',packet)
        without_count=copy.deepcopy(SUBJECT);without_count['rating'].pop('count')
        self.assertEqual(verify_payload(REF,without_count,'37234567','tv',NOW)['detailMetadata']['rating'],9.1)
        self.assertEqual((packet['season'],packet['year']),(6,2026))
    def test_season_identity_conflicts_and_unnumbered_series_are_rejected(self):
        for payload in [dict(SUBJECT,title='流人 第五季'),dict(SUBJECT,original_title='Slow Horses Season 1'),dict(SUBJECT,title='流人',original_title='Slow Horses')]:
            self.assertIsNone(verify_payload(REF,payload,'37234567','tv',NOW))
        self.assertIsNone(verify_payload(dict(REF,year='2025'),SUBJECT,'37234567','tv',NOW))
    def test_missing_score_is_explicit_and_never_uses_provider_rating(self):
        packet=verify_payload(REF,dict(SUBJECT,rating={}), '37234567','tv',NOW)['detailMetadata']
        self.assertEqual(packet['ratingStatus'],'NO_RATING');self.assertNotIn('rating',packet);self.assertTrue(valid(packet,'series'))
    def test_missing_intro_is_atomic_pending_not_another_sources_summary(self):
        result=verify_payload(REF,dict(SUBJECT,intro=''), '37234567','tv',NOW)
        packet=result['detailMetadata'];self.assertEqual(packet['summary'],'');self.assertEqual(packet['summaryStatus'],'PENDING')
        result.update(summary_zh=SUMMARY,summary_sources=[{'url':'https://zh.wikipedia.org/wiki/Example'}])
        self.assertEqual(from_patch(result,REF)['summary'],'')
    def test_a_subject_cannot_be_relabelled_as_another_season(self):
        packet=self.packet();work={'kind':'series','en':'Slow Horses','slug':'slow-horses','zh':{}}
        self.assertTrue(attach(work,packet));self.assertFalse(attach(work,dict(packet,season=5)))
        self.assertEqual(len(work['zh']['detailSeasons']),1)
    def test_cache_keeps_packet_when_legacy_gemini_summary_changes(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);work={'kind':'series','en':'Slow Horses','slug':'slow-horses','officialId':'umc.cmc.test','zh':{'summary':'官网翻译的另一段中文简介'}}
            remember(work,self.packet(),root)
            restored=apply_cached({'entries':[dict(work,zh={'summary':'新官网译文'})]},root)['entries'][0]
            self.assertEqual(restored['zh']['summary'],'新官网译文');self.assertEqual(restored['zh']['detailMetadata']['summary'],SUMMARY)
            self.assertNotIn('detailMetadata',apply_cached({'entries':[dict(work,en='Wrong show',zh={})]},root)['entries'][0]['zh'])
    def test_metadata_boundary_rejects_mixed_or_invalid_packets(self):
        packet=self.packet();self.assertIsNotNone(clean_zh({'metadataPolicy':'mainland-v1','detailMetadata':packet,'detailSeasons':[packet]}))
        for broken in [dict(packet,source='cms'),dict(packet,sourceUrl='https://example.com/'),dict(packet,rating=11),dict(packet,checkedAt='2026-11-01'),dict(packet,season=-1)]:
            self.assertIsNone(clean_zh({'metadataPolicy':'mainland-v1','detailMetadata':broken}))
        self.assertIsNone(clean_zh({'metadataPolicy':'mainland-v1','detailSeasons':[packet,dict(packet,season=5)]}))
    def test_movies_have_no_tv_season(self):
        payload=dict(SUBJECT,title='电影中文名',original_title='Exact Movie',type='movie')
        packet=verify_payload({'english_title':'Exact Movie','kind':'movie','year':'2026'},payload,'37234567','movie',NOW)['detailMetadata']
        self.assertEqual(packet['season'],0);self.assertTrue(valid(packet,'movie'));self.assertFalse(valid(packet,'series'))
    def test_localized_query_is_bounded_and_still_verifies_english_identity(self):
        class Pages:
            def __init__(self):self.queries=[]
            def json(self,url,**kw):
                if 'subject_suggest'in url:
                    self.queries.append(kw['params']['q'])
                    return [{'id':'37234567'}]if kw['params']['q']=='流人 第六季'else[]
                return SUBJECT
        pages=Pages();result=DoubanMobile(pages).lookup(dict(REF,display_name_zh='流人'),NOW)
        self.assertEqual(pages.queries,['Slow Horses Season 6','流人 第六季']);self.assertEqual(result['detailMetadata']['season'],6)
    def test_existing_chinese_name_with_no_packet_still_enters_atomic_queue(self):
        from unittest.mock import Mock,patch
        from mainland_names import run
        from title_lookup import dump
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);work={'kind':'series','en':'Slow Horses','slug':'slow-horses','artworkSeasonNumber':6,'seasons':[{'season':6,'year':'2026'}],'zh':{'metadataPolicy':'mainland-v1','name_status':'verified_title_sources','title':'流人','_identityYear':2022}}
            dump(root/'docs/catalog.json',{'entries':[work]});dump(root/'docs/home/home.json',{'works':[]});dump(root/'docs/version.json',{})
            client=Mock(events=[]);probe=Mock(return_value=({'title':'流人第六季','routes':1},[]))
            with patch('mainland_names.DoubanMobile')as mobile,patch('mainland_names.publish'),patch('mainland_names.republish_home'):
                mobile.return_value.lookup.return_value=verify_payload(REF,SUBJECT,'37234567','tv',NOW)
                report=run(root,client=client,lookup=Mock(),probe=probe)
            self.assertEqual(report['changed'],['slow-horses']);self.assertEqual(report['records'][0]['detailMetadata']['season'],6)
            packet=json.loads((root/'data/detail-metadata-cache.json').read_text(encoding='utf8'))['works']['pr:slow-horses']['details'][0]
            self.assertEqual((packet['title'],packet['summary'],packet['rating']),('流人',SUMMARY,9.1))

if __name__=='__main__':unittest.main()
