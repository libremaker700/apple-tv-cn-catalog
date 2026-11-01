import base64,copy,json,sys,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from provider_adapters import AdapterError,Transport,Ikanbot,Shared,Juzi,Fields,field,varint,create,provider_key
from mainland_names import public_sources,source_people
from source_votes import incomplete,usable_groups

def blob(number,raw):return varint(number*8+2)+varint(len(raw))+raw
def cms(**kw):return dict(vod_id='1',vod_name='夜曲第一季',vod_year='2026',type_name='欧美剧',vod_director='导演甲',vod_actor='演员甲,演员乙',vod_play_from='ffm3u8',vod_play_url='第1集$https://media.test/episode.m3u8',**kw)
SETTINGS={'appId':'fixture','apiVer':'1','appVersion':'1','package':'fixture','signKeyHex':'00'*16,'responseKeyHex':'01'*16,'responseIvHex':'02'*16,'guest':{'token':'fixture-private-token','id':'7','channelId':'2','level':1}}

class Registry(unittest.TestCase):
    def test_all_libraries_receive_fair_bounded_slots(self):
        deadlines=[];seen=[];deadline=time.monotonic()+90
        def adapter(provider,session,local):
            deadlines.append(local-time.monotonic());seen.append(provider['id']);value=Mock();value.search.return_value=[cms()];value.playable.side_effect=lambda row:row;return value
        providers=[{'id':str(i),'url':'https://source'+str(i)+'.test/api'}for i in range(33)]
        with patch('source_votes.create',side_effect=adapter):
            best,_=public_sources({'kind':'series','year':'2026','season':1,'actors':'演员甲,演员乙','directors':'导演甲'},['夜曲'],providers,session=Mock(),deadline=deadline)
        self.assertEqual(len(set(seen)),33);self.assertTrue(all(0<left<=10 for left in deadlines));self.assertEqual(best['libraries'],33);self.assertTrue(best['selection']['complete'])
    def test_all_33_app_libraries_and_protocol_types(self):
        rows=json.loads((Path(__file__).resolve().parents[1]/'data/public-source-providers.json').read_text(encoding='utf8'))
        self.assertEqual(len(rows),33);self.assertEqual(len({r['id']for r in rows}),33);self.assertEqual(len({provider_key(r)for r in rows}),33)
        kinds={r['id']:r.get('type','cms')for r in rows};self.assertEqual(sum(v=='cms'for v in kinds.values()),29)
        self.assertEqual({k:kinds[k]for k in('shared','ikanbot','shenhua','bblue')},{'shared':'shared','ikanbot':'ikanbot','shenhua':'juzi','bblue':'juzi'})
        self.assertFalse(any(key in json.dumps(rows)for key in('guest','signingSecret','bodyKey','responseKeyHex','token')))
    def test_missing_private_settings_are_pending_and_not_an_empty_library(self):
        with patch.dict('os.environ',{},clear=True):
            best,events=public_sources({'kind':'series','season':1,'year':'2026'},['夜曲'],[{'id':'shared','type':'shared'}])
        self.assertIsNone(best);self.assertEqual(events[0]['reason'],'needs_configuration');self.assertTrue(incomplete(events))
    def test_partial_scope_never_claims_all_libraries_checked(self):
        session=Mock();session.get.return_value=Mock(status_code=200,json=lambda:{'list':[dict(cms(),vod_douban_id='36229588')]})
        with patch.dict('os.environ',{},clear=True):best,events=public_sources({'kind':'series','season':1,'year':'2026','douban_id':'36229588'},['夜曲'],[{'id':'cms','url':'https://example.test/api'},{'id':'shared','type':'shared'}],session=session)
        self.assertEqual(best['libraries'],1);self.assertEqual(best['selection']['requestedLibraries'],2);self.assertEqual(best['selection']['checkedLibraries'],1);self.assertEqual(best['selection']['attemptedLibraries'],2);self.assertFalse(best['selection']['complete'])
        self.assertNotIn('fixture-private-token',json.dumps(events));self.assertNotIn('episode.m3u8',json.dumps(best))
    def test_people_are_supplied_for_records_without_douban_ids(self):
        ref=source_people({'kind':'series','season':1,'year':'2026'},{'directors':['导演甲'],'actors':['演员甲','演员乙']});session=Mock();session.get.return_value=Mock(status_code=200,json=lambda:{'list':[cms()]})
        best,_=public_sources(ref,['夜曲'],[{'id':'a','url':'https://example.test/api'}],session=session)
        self.assertEqual(best['libraries'],1)
    def test_unconfirmed_identity_cannot_be_mistaken_for_no_record(self):
        session=Mock();session.get.return_value=Mock(status_code=200,json=lambda:{'list':[cms()]})
        best,events=public_sources({'kind':'series','season':1,'year':'2026'},['夜曲'],[{'id':'a','url':'https://example.test/api'}],session=session)
        self.assertIsNone(best);self.assertTrue(incomplete(events));self.assertEqual(events[0]['reason'],'identity_pending')
    def test_conflicting_people_without_number_is_pending_not_absent(self):
        session=Mock();session.get.return_value=Mock(status_code=200,json=lambda:{'list':[cms()]})
        best,events=public_sources({'kind':'series','season':1,'year':'2026','actors':'演员丙,演员丁','directors':'导演乙'},['夜曲'],[{'id':'a','url':'https://example.test/api'}],session=session)
        self.assertIsNone(best);self.assertTrue(incomplete(events));self.assertEqual(events[0]['reason'],'identity_pending')

class Ikan(unittest.TestCase):
    def page(self,identity='12345'):
        return '<input id="current_id" value="'+identity+'"><input id="mtype" value="2"><input id="e_token" value="'+'a'*150+'"><h1 id="video_title">夜曲第一季</h1><h3 class="meta">别名</h3><h3 class="meta">2026</h3><h3 class="meta">美国</h3><h3 class="meta">导演甲 / 演员甲,演员乙</h3>'
    def test_search_metadata_and_page_token_resource_adapter(self):
        transport=Mock();transport.fetch.side_effect=lambda url,**kw:(('<a href="/play/12345" class="title-text">夜曲第一季 2026</a>'if '/search?'in url else self.page()).encode(),{})
        transport.json.return_value={'state':1,'data':{'list':[{'id':'9','resData':json.dumps([{'flag':'ffm3u8','url':'第1集$https://media.test/one.m3u8'}])}]}}
        adapter=Ikanbot(transport);row=adapter.describe(adapter.search('夜曲')[0]);self.assertEqual(row['type_name'],'电视剧');self.assertEqual(row['vod_director'],'导演甲');self.assertEqual(row['vod_actor'],'演员甲,演员乙')
        playable=adapter.playable(row);self.assertEqual(usable_groups(playable),1);self.assertEqual(len(transport.json.call_args.kwargs['params']['token']),32)
    def test_changed_record_and_access_challenges_are_not_bypassed(self):
        transport=Mock();transport.fetch.return_value=(self.page('99999').encode(),{});adapter=Ikanbot(transport)
        with self.assertRaises(AdapterError):adapter.describe({'vod_id':'12345'})
        transport.fetch.return_value=(b'<html>captcha</html>',{})
        with self.assertRaises(AdapterError):adapter.search('夜曲')

class SharedSession(unittest.TestCase):
    def test_signed_search_uses_private_headers_without_returning_them(self):
        transport=Mock();transport.fetch.return_value=(json.dumps({'code':200,'data':{'items':[{'id':1,'title':'夜曲第一季','year':{'name':'2026'},'channelId':2,'directors':[{'name':'导演甲'}],'actors':[{'name':'演员甲'},{'name':'演员乙'}]}]}}).encode(),{})
        adapter=Shared(transport,SETTINGS);rows=adapter.search('夜曲第一季');self.assertEqual(rows[0]['vod_actor'],'演员甲,演员乙')
        self.assertEqual(transport.fetch.call_args.kwargs['headers']['X-Token'],'fixture-private-token');self.assertRegex(transport.fetch.call_args.kwargs['headers']['sign'],r'^[a-f0-9]{40}$');self.assertNotIn('fixture-private-token',json.dumps(rows))
    def test_shared_catalog_is_one_library_and_omits_login_only_entries(self):
        transport=Mock();adapter=Shared(transport,SETTINGS);adapter.details['1']={'playSources':[{'siteId':'private','needLogin':1,'needAccelerate':0,'list':[{'m3u8Url':'https://media.test/private.m3u8'}]},{'siteId':'one','needLogin':0,'needAccelerate':0,'list':[{'title':'第1集','playUrls':[{'url':'https://media.test/one.m3u8'}]}]},{'siteId':'two','needLogin':0,'needAccelerate':0,'list':[{'title':'第1集','m3u8Url':'https://media.test/two.m3u8'}]}]}
        row=adapter.playable({'vod_id':'1'});self.assertEqual(usable_groups(row),2);self.assertNotIn('private.m3u8',row['vod_play_url']);transport.fetch.assert_not_called()
    def test_missing_session_fails_without_any_network_request(self):
        transport=Mock()
        with self.assertRaises(AdapterError):Shared(transport,{})
        transport.fetch.assert_not_called()

class JuziProtocol(unittest.TestCase):
    def adapter(self,line='qsvip'):return Juzi(Mock(),{'origin':Juzi.ORIGIN,'publicKey':'fixture','signingSecret':'0123456789abcdef','bodyKey':'0123456789abcdef','bootstrapUrls':['https://example.test/bootstrap'],'packageName':'test','versionCode':'1','versionName':'1','fakePosition':3},line)
    def test_protobuf_detail_medium_uses_field_15_not_field_14(self):
        row=Fields(field(4,1)+field(9,'夜曲第一季')+field(14,777)+field(15,21)+field(18,2026)+field(12,'导演甲')+field(25,'演员甲,演员乙'))
        adapter=self.adapter();adapter.request=Mock(return_value=row);out=adapter.describe({'vod_id':'1'})
        self.assertEqual((out['type_name'],out['vod_year']),('电视剧','2026'));self.assertEqual(out['vod_actor'],'演员甲,演员乙')
    def test_two_juzi_libraries_keep_their_line_selectors(self):
        eps=[field(3,'第1集')+field(4,'private-path-one')+field(9,'qsvip')+field(12,1),field(3,'第1集')+field(4,'private-path-two')+field(9,'bfzym3u8')+field(12,1)]
        detail=Fields(b''.join(blob(29,value)for value in eps))
        for line,wanted in [('qsvip','private-path-one'),('bfzym3u8','private-path-two')]:
            adapter=self.adapter(line);adapter.details['1']=detail;adapter.request=Mock(return_value=Fields(field(1,'https://media.test/real.m3u8')));row=adapter.playable({'vod_id':'1'})
            self.assertEqual(row['vod_play_from'],line);self.assertEqual(usable_groups(row),1);self.assertIn(wanted,adapter.request.call_args.args[1]);self.assertNotIn('private-path',json.dumps(row))
    def test_proto_rejects_truncation(self):
        with self.assertRaises(AdapterError):Fields(b'\x0a\x64\x01')
    def test_real_aes_rsa_primitives_match_protocol_padding(self):
        from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
        from cryptography.hazmat.primitives import padding,serialization
        from cryptography.hazmat.primitives.asymmetric import rsa,padding as rsa_padding
        value='searchKeys=夜曲&stamp=123';encrypted=base64.b64decode(Juzi.aes('0123456789abcdef',value));decrypt=Cipher(algorithms.AES(b'0123456789abcdef'),modes.ECB()).decryptor();padded=decrypt.update(encrypted)+decrypt.finalize();unpad=padding.PKCS7(128).unpadder();self.assertEqual((unpad.update(padded)+unpad.finalize()).decode(),value)
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048);public=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)).decode();cipher=base64.b64decode(Juzi.rsa(public,'123nonce1'));self.assertEqual(key.decrypt(cipher,rsa_padding.PKCS1v15()),b'123nonce1')

if __name__=='__main__':unittest.main()
