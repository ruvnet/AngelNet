import contextlib
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cc_static as s


class Response(io.BytesIO):
    def __init__(self, body, status=206, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


class StaticTests(unittest.TestCase):
    def test_domain_interval_includes_preceding_block_and_subdomains(self):
        keys = ['org,aaa)/ 20260101000000', 'org,example)/a 20260101000000',
                'org,example,clinic)/ 20260101000000', 'org,examplex)/ 20260101000000',
                'org,zzz)/ 20260101000000']
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cluster.idx'
            path.write_text(''.join(f'{key}\tcdx-00000.gz\t{i * 100}\t100\t{i}\n'
                                    for i, key in enumerate(keys)))
            selected, counts = s.select_blocks(path, ['example.org'], 10)
            self.assertEqual([b['offset'] for b in selected['example.org']], [0, 100, 200])
            self.assertEqual(counts['example.org'], 3)
            www, _ = s.select_blocks(path, ['www.example.org'], 10)
            self.assertEqual(www['www.example.org'], selected['example.org'])
            selected, counts = s.select_blocks(path, ['example.org'], 1)
            self.assertEqual(len(selected['example.org']), 1)
            self.assertEqual(counts['example.org'], 3)

    def test_unrelated_large_blocks_do_not_invalidate_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cluster.idx'
            path.write_text(f'org,aaa)/ 20260101000000\tcdx-00000.gz\t0\t{s.BLOCK_CAP + 1}\n'
                            'org,bbb)/ 20260101000000\tcdx-00001.gz\t0\t100\n'
                            'org,zzz)/ 20260101000000\tcdx-00001.gz\t100\t100\n')
            selected, _ = s.select_blocks(path, ['example.org'], 1)
            self.assertEqual(selected['example.org'][0]['filename'], 'cdx-00001.gz')

    def test_unsorted_or_unsafe_cluster_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cluster.idx'
            for body in ['org,z)/ 20260101000000\t../../x.gz\t0\t100\n',
                         'org,z)/ 20260101000000\tcdx-00000.gz\t0\t100\n'
                         'org,a)/ 20260101000000\tcdx-00000.gz\t100\t100\n']:
                path.write_text(body)
                with self.assertRaises(ValueError):
                    s.select_blocks(path, ['example.org'], 1)

    def test_cdxj_timestamp_and_gzip_integrity(self):
        payload = b'org,example)/index.php 20060101120000 {"url":"https://example.org/index.php","status":"200","mime":"text/html"}\n'
        compressed = gzip.compress(payload)
        self.assertEqual(list(s.decode_block(compressed))[0]['timestamp'], '20060101120000')
        with self.assertRaises(EOFError):
            list(s.decode_block(compressed[:-5]))
        with patch.object(s, 'INFLATED_CAP', 10), self.assertRaisesRegex(ValueError, 'inflated_block'):
            list(s.decode_block(compressed))

    def test_range_and_resource_contract(self):
        client = s.StaticClient(1000, 2, 10)
        url = s.BASE + 'CC-MAIN-2026-43/indexes/cdx-00000.gz'
        for status, headers in [(200, {}), (206, {'Content-Range': 'bytes 1-3/10'})]:
            with patch.object(client.opener, 'open', return_value=Response(b'abc', status, headers)):
                with self.assertRaisesRegex(ValueError, 'range_not_honored'):
                    client.fetch(url, io.BytesIO(), 100, (0, 3))
        self.assertEqual(client.bytes, 0)
        with self.assertRaisesRegex(ValueError, 'resource_not_allowed'):
            client.fetch('https://example.org/index.php', io.BytesIO(), 100)

    def test_valid_range_and_download_budget(self):
        client = s.StaticClient(3, 2, 10)
        response = Response(b'abc', headers={'Content-Range': 'bytes 4-6/10', 'Content-Length': '3'})
        url = s.BASE + 'CC-MAIN-2026-43/indexes/cdx-00000.gz'
        out = io.BytesIO()
        with patch.object(client.opener, 'open', return_value=response):
            receipt = client.fetch(url, out, 3, (4, 3))
        self.assertEqual(out.getvalue(), b'abc')
        self.assertEqual(receipt['bytes'], 3)
        with self.assertRaisesRegex(ValueError, 'download_budget_exhausted'):
            client.fetch(url, io.BytesIO(), 3, (7, 3))

    def test_end_to_end_scope_and_error_receipt(self):
        body = b''.join((f'org,example)/{name}.php 20060101120000 '+json.dumps(dict(
            url=f'https://{host}/{name}.php?session=private', status='200', mime='text/html'))+'\n').encode()
            for name, host in [('clinic', 'example.org'), ('outside', 'example.org.evil.test')])
        compressed = gzip.compress(body)
        cluster = f'org,aaa)/ 20060101120000\tcdx-00000.gz\t0\t{len(compressed)}\n'.encode()

        def fetch(client, url, sink, cap, byte_range=None):
            data = cluster if url.endswith('cluster.idx') else compressed
            sink.write(data)
            client.requests += 1
            client.bytes += len(data)

        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            args = ['--domain', 'example.org', '--collection', 'CC-MAIN-2026-43', '--out', tmp]
            with patch.object(s.StaticClient, 'fetch', fetch):
                self.assertEqual(s.main(args), 0)
            receipt = json.loads((Path(tmp) / 'static-run.json').read_text())
            self.assertEqual(receipt['scoped_records'], 1)
            self.assertEqual(receipt['observations_added'], 1)
            export = (Path(tmp) / 'sites.jsonl').read_text()
            self.assertNotIn('private', export)
            self.assertNotIn('evil.test', export)
            self.assertEqual(json.loads(export)['vulnerability_status'], 'not_assessed')
            with patch.object(s.StaticClient, 'fetch', side_effect=TimeoutError):
                self.assertEqual(s.main(args), 2)
            receipt = json.loads((Path(tmp) / 'static-run.json').read_text())
            self.assertEqual(receipt['status'], 'partial')
            self.assertTrue(receipt['cluster']['cache_hit'])
            self.assertEqual(receipt['observations_added'], 0)


if __name__ == '__main__':
    unittest.main()
