import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from provider_adapters import Shared, AdapterError


class SharedRoutesTest(unittest.TestCase):
    def test_exact_order_and_pairs(self):
        hosts = ['qvfic.com', 'zwtlzch.cn', 'mjrlin.cn', 'shkjbd.com']
        expected = [('https://vlogic.' + host, 'https://vcache.' + host) for host in hosts]
        expected.append(('https://43.248.100.71:51010', 'https://43.248.100.71:51020'))
        self.assertEqual(Shared.ROUTES, expected)

    def test_failure_fallback_and_cache_pair(self):
        class FakeTransport:
            addresses = []
            def fetch(self, address, **kwargs):
                self.addresses.append(address)
                if not address.startswith(Shared.ROUTES[-1][1]):
                    raise AdapterError('network')
                return json.dumps({'code': 200, 'data': {'id': 'fixture'}}).encode(), {}
        settings = dict(appId='fixture', apiVer='1', appVersion='1', package='fixture',
                        signKeyHex='00' * 32, responseKeyHex='00' * 32, responseIvHex='00' * 16,
                        guest=dict(id='fixture', channelId='1', level=1, token='fixture'))
        transport = FakeTransport()
        result = Shared(transport, settings).call('/fixture', {}, cache=True)
        self.assertEqual(result, {'id': 'fixture'})
        self.assertEqual(transport.addresses, [cache + '/fixture' for _, cache in Shared.ROUTES])


if __name__ == '__main__':
    unittest.main()
