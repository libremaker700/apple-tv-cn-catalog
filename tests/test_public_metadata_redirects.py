import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from public_sources import PublicPages
from test_source_order import Session,Response

class MetadataRedirects(unittest.TestCase):
    def redirect(self,location):
        r=Response(301);r.headers={'Location':location};return r
    def test_same_host_redirect_is_bounded_and_not_a_host_access_failure(self):
        session=Session([self.redirect('/rexxar/api/v2/movie/12346'),Response(200,'{"id":"12346"}'),Response(200,'{"id":"99999"}')])
        reader=PublicPages(session)
        with patch('public_sources.time.sleep'):
            self.assertEqual(reader.json('https://m.douban.com/rexxar/api/v2/movie/12345')['id'],'12346')
            self.assertEqual(reader.json('https://m.douban.com/rexxar/api/v2/movie/99999')['id'],'99999')
        self.assertEqual(len(session.calls),3);self.assertNotIn('m.douban.com',reader.data['hosts'])
    def test_cross_host_login_and_redirect_loops_are_not_followed(self):
        for location in ['https://evil.invalid/private','http://m.douban.com/private','https://user:pass@m.douban.com/private','/accounts/login/','/captcha/']:
            session=Session([self.redirect(location)]);reader=PublicPages(session)
            with self.subTest(location=location),patch('public_sources.time.sleep'):
                self.assertIsNone(reader.get('https://m.douban.com/movie/subject/12345/'));self.assertEqual(len(session.calls),1)
        session=Session([self.redirect('/b'),self.redirect('/c'),self.redirect('/d')]);reader=PublicPages(session)
        self.assertIsNone(reader.get('https://m.douban.com/a'));self.assertEqual(len(session.calls),3)
    def test_old_redirect_cooldown_does_not_skip_other_subjects(self):
        session=Session([Response(200,'{"ok":true}')]);reader=PublicPages(session,clock=lambda:100)
        reader.data['hosts']['m.douban.com']={'status':301,'retry_at':99999}
        self.assertEqual(reader.json('https://m.douban.com/rexxar/api/v2/movie/12345'),{'ok':True})
    def test_one_transport_error_does_not_mark_entire_site_absent(self):
        class NetworkThenSuccess:
            calls=0
            def get(self,*args,**kwargs):
                self.calls+=1
                if self.calls==1:raise requests.ConnectionError()
                return Response(200,'{"ok":true}')
        reader=PublicPages(NetworkThenSuccess())
        with patch('public_sources.time.sleep'):
            self.assertIsNone(reader.get('https://m.douban.com/a'))
            self.assertEqual(reader.json('https://m.douban.com/b'),{'ok':True})
