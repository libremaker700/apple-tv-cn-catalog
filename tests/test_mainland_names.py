import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from mainland_names import candidate_matches,source_count,independent_name
class Identity(unittest.TestCase):
    def test_year_season_medium_and_full_name_are_kept(self):
        ref={'kind':'series','year':'2026','season':2};row={'vod_name':'正确剧名第二季','vod_year':'2026','type_name':'欧美剧'}
        self.assertTrue(candidate_matches(ref,row,['正确剧名']));self.assertFalse(candidate_matches(ref,dict(row,vod_name='正确剧名第三季'),['正确剧名']));self.assertFalse(candidate_matches(ref,dict(row,vod_year='2025'),['正确剧名']));self.assertFalse(candidate_matches(ref,dict(row,vod_name='正确剧名的另一部'),['正确剧名']))
    def test_only_nonempty_web_media_groups_count(self):self.assertEqual(source_count({'vod_play_url':'正片$https://example.invalid/a.m3u8$$$正片$javascript:evil$$$'}),1)
    def test_review_links_and_search_headlines_are_not_identity_proof(self):
        class Fake:pass
        self.assertIsNone(independent_name({'english_title':'Now & Then','year':'2022'},[{'title':'过去如今之后','url':'https://movie.douban.com/subject/123/reviews'}],Fake(),0))

class UpcomingPolicy(unittest.TestCase):
    def test_direct_verified_name_and_source_skip_paid_search(self):
        import tempfile,json
        from unittest.mock import patch,Mock
        from mainland_names import run
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);(root/'docs/home').mkdir(parents=True);(root/'data').mkdir()
            entry={'slug':'women-in-blue-las-azules','en':'Women in Blue (Las Azules)','kind':'series','releaseDate':'2026-08-12','artworkSeasonNumber':2,'seasons':[{'season':2,'year':'2026','releaseDate':'2026-08-12'}],'zh':{'_identityYear':2024}}
            for path,value in [('docs/catalog.json',{'entries':[entry]}),('docs/home/home.json',{'works':[]}),('docs/version.json',{})]:(root/path).write_text(json.dumps(value),encoding='utf8')
            client=Mock(events=[]);probe=Mock(return_value=({'title':'女警出更第二季','routes':2,'provider':'hn'},[]))
            verified={'display_name_zh':'女警出更','aliases_zh':[],'sources':[{'url':'https://movie.douban.com/subject/35912846/'}]}
            with patch('mainland_names.DoubanMobile') as mobile,patch('mainland_names.publish'),patch('mainland_names.republish_home'):
                mobile.return_value.lookup.return_value=verified
                result=run(root,client=client,lookup=Mock(),probe=probe)
            client.search.assert_not_called();self.assertEqual(result['reservedThisMonth'],0)
            self.assertEqual(result['records'][0]['title'],'女警出更')
            self.assertEqual(probe.call_args.args[0],{'year':'2026','season':2,'kind':'series'})
    def test_future_and_unknown_announced_dates_defer_but_release_day_is_eligible(self):
        from mainland_names import source_deferred
        import calendar
        now=calendar.timegm((2026,10,31,12,0,0))
        self.assertTrue(source_deferred({'releaseDate':'2026-11-13'},now))
        self.assertTrue(source_deferred({'metadataStatus':'announced'},now))
        self.assertFalse(source_deferred({'releaseDate':'2026-10-31','upcoming':True},now))
    def test_name_only_does_not_call_source_probe_then_reuses_name_after_release(self):
        import tempfile,json
        from unittest.mock import patch,Mock
        from mainland_names import run
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);(root/'docs/home').mkdir(parents=True);(root/'data').mkdir()
            entry={'slug':'future-film','en':'Future Film','kind':'movie','releaseDate':'2099-11-13','zh':{'_identityYear':2026}}
            main={'entries':[entry]};home={'works':[]}
            def save():
                (root/'docs/catalog.json').write_text(json.dumps(main),encoding='utf-8')
                (root/'docs/home/home.json').write_text(json.dumps(home),encoding='utf-8')
                (root/'docs/version.json').write_text('{}',encoding='utf-8')
            save();client=Mock();client.search.return_value=([], 'ok');client.events=[];probe=Mock(return_value=({'title':'片源名称','routes':2,'provider':'lz'},[]))
            verified={'display_name_zh':'中文名称','aliases_zh':[],'sources':[{'url':'https://movie.douban.com/subject/123/','type':'douban_identity_fields'}]}
            with patch('mainland_names.independent_name',return_value=verified),patch('mainland_names.publish'),patch('mainland_names.republish_home'):
                result=run(root,client=client,lookup=Mock(),probe=probe)
                self.assertEqual(result['records'][0]['title'],'中文名称');self.assertEqual(result['records'][0]['sourcePolicy'],'deferred_until_release');probe.assert_not_called()
                # Simulate publication and later release without querying the name again.
                entry['zh']={'title':'中文名称','aliases':['中文名称'],'name_status':'verified_title_sources','name_sources':verified['sources'],'_identityYear':2026};entry['releaseDate']='2026-01-01';save();client.search.reset_mock()
                result=run(root,client=client,lookup=Mock(),probe=probe)
                probe.assert_called_once();client.search.assert_not_called();self.assertEqual(result['records'][0]['title'],'片源名称')
