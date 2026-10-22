import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse

import angel_index as a


TODAY = dt.date(2026, 10, 21)


def row(url='https://old.example.org/index.php?token=secret#private', timestamp='20060101120000', **kw):
    return dict(url=url, timestamp=timestamp, status='200', mime='text/html', **kw)


class IndexTests(unittest.TestCase):
    def test_redaction_and_scope(self):
        item = a.observation(row(), 'fixture', ['example.org'], TODAY)
        self.assertEqual(item[1], 'https://old.example.org/index.php')
        self.assertIsNone(a.observation(row(url='https://example.org.evil.test/x.php'), 'f', ['example.org'], TODAY))

    def test_url_validation(self):
        for url in ['file:///etc/passwd', 'http://127.0.0.1/x.php', 'https://user:pass@example.org/x.php',
                    'https://example.org:8000/x.php', 'https://example.org/x.php\n']:
            self.assertIsNone(a.observation(row(url=url), 'f', [], TODAY), url)

    def test_no_php_from_query_or_documentation(self):
        for url in ['https://example.org/?next=x.php', 'https://example.org/manual.php.html',
                    'https://example.org/php-history', 'https://example.org/index.php.txt']:
            self.assertIsNone(a.observation(row(url=url), 'f', [], TODAY), url)
        self.assertIsNotNone(a.observation(row(url='https://example.org/index.php/foo'), 'f', [], TODAY))

    def test_bad_status_dates_and_mime(self):
        for change in [dict(status='404'), dict(mime='application/json'), dict(timestamp='20270201120000'),
                       dict(timestamp='20060230120000'), dict(timestamp='2006')]:
            record = row()
            record.update(change)
            self.assertIsNone(a.observation(record, 'f', [], TODAY))

    def test_twenty_year_boundary_and_no_security_inference(self):
        db = a.init_db(':memory:')
        for host, stamp in [('old', '20061021120000'), ('new', '20061022120000')]:
            a.save(db, [a.observation(row(url=f'https://{host}.example.org/a.php', timestamp=stamp), 'f', [], TODAY)])
        records = list(a.sites(db, TODAY, 20))
        self.assertEqual([r['archive_age_at_least_years'] for r in records], [20, None])
        for r in records:
            self.assertEqual(r['maintenance_status'], 'unknown')
            self.assertEqual(r['vulnerability_status'], 'not_assessed')
            self.assertEqual(r['identity_continuity'], 'unknown')
        self.assertEqual(a.cutoff_date(dt.date(2024, 2, 29), 1), dt.date(2023, 2, 28))
        db.close()

    def test_dedup(self):
        db = a.init_db(':memory:')
        item = a.observation(row(), 'f', [], TODAY)
        self.assertEqual(a.save(db, [item]), 1)
        self.assertEqual(a.save(db, [item, item]), 0)
        db.close()

    def test_only_archive_providers(self):
        c = a.Client(delay=0)
        for url in ['http://index.commoncrawl.org/', 'https://example.org/',
                    'https://web.archive.org.evil.test/', 'https://user@web.archive.org/']:
            with self.assertRaises(ValueError):
                c.get(url)
        self.assertEqual(c.count, 0)

    def test_no_redirects(self):
        with self.assertRaisesRegex(ValueError, 'redirect'):
            a.RefuseRedirect().redirect_request(None, None, 302, '', {}, 'https://example.org/')

    def test_request_budget(self):
        c = a.Client(max_requests=0, delay=0)
        with self.assertRaisesRegex(ValueError, 'request_budget'):
            c.get('https://web.archive.org/')

    def test_time_budget(self):
        c = a.Client(max_seconds=0, delay=0)
        with self.assertRaisesRegex(ValueError, 'time_budget'):
            c.get('https://web.archive.org/')

    def test_response_limit(self):
        class Response(io.BytesIO):
            pass
        c = a.Client(delay=0)
        with patch.object(c.opener, 'open', return_value=Response(b'x' * (a.MAX_BODY + 1))):
            with self.assertRaisesRegex(ValueError, 'too_large'):
                c.get('https://web.archive.org/')

    def test_query_contract(self):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(a.cc_query('CC-MAIN-2026-43', 'example.org', 10, 2)).query)
        self.assertEqual(q['page'], ['2'])
        self.assertEqual(q['matchType'], ['domain'])
        self.assertEqual(q['limit'], ['10'])
        with self.assertRaises(ValueError):
            a.cc_query('../evil', 'example.org', 10, 0)

    def test_offline_cli_and_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'fixture.jsonl'
            source.write_text(json.dumps(row()) + '\n')
            args = ['--input', str(source), '--out', str(root / 'out')]
            with patch.object(a.Client, 'get', side_effect=AssertionError('network')), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(a.main(args), 0)
                self.assertEqual(a.main(args), 0)
            receipt = json.loads((root / 'out/last_run.json').read_text())
            self.assertEqual(receipt['observations_added'], 0)
            self.assertEqual(receipt['provider_requests'], 0)
            self.assertEqual(receipt['sites_total'], 1)
            self.assertNotIn('secret', (root / 'out/sites.jsonl').read_text())
            self.assertTrue((root / 'out/sites.csv').exists())
            self.assertEqual(len(list((root / 'out/runs').glob('*.json'))), 2)

    def test_error_receipt_not_empty_success(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            with patch.object(a.Client, 'get', side_effect=urllib.error.HTTPError('url', 429, 'limited', {}, None)):
                code = a.main(['--domain', 'example.org', '--out', temp])
            receipt = json.loads((Path(temp) / 'last_run.json').read_text())
            self.assertEqual(code, 2)
            self.assertEqual(receipt['status'], 'partial')
            self.assertEqual(receipt['errors'][0]['error'], 'http_429')

    def test_online_pipeline_with_wayback(self):
        responses = [json.dumps([{'id': 'CC-MAIN-2026-43'}]),
                     json.dumps(row(timestamp='20261001120000')),
                     json.dumps([['timestamp', 'original', 'statuscode', 'mimetype'],
                                 ['20060101120000', 'https://old.example.org/a.php', '200', 'text/html']])]
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            with patch.object(a.Client, 'get', side_effect=responses) as get:
                code = a.main(['--domain', 'example.org', '--wayback', '--out', temp])
            record = json.loads((Path(temp) / 'sites.jsonl').read_text())
            self.assertEqual(code, 0)
            self.assertEqual(record['archive_age_at_least_years'], 20)
            self.assertEqual(get.call_count, 3)
            self.assertEqual(record['current_reachability'], 'not_checked')

    def test_global_record_limit(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            with patch.object(a.Client, 'get', return_value='\n'.join(json.dumps(row()) for _ in range(20))):
                a.main(['--domain', 'example.org', '--collection', 'CC-MAIN-2026-43', '--limit', '3', '--out', temp])
            receipt = json.loads((Path(temp) / 'last_run.json').read_text())
            self.assertEqual(receipt['records_examined'], 3)

    def test_wayback_discovery_without_commoncrawl(self):
        body = json.dumps([['timestamp', 'original', 'statuscode', 'mimetype'],
                           ['20060101120000', 'https://old.example.org/a.php', '200', 'text/html']])
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            with patch.object(a.Client, 'get', return_value=body) as get:
                code = a.main(['--source', 'wayback', '--domain', 'example.org', '--out', temp])
            self.assertEqual(code, 0)
            self.assertEqual(get.call_count, 1)
            self.assertIn('web.archive.org', get.call_args.args[0])
            self.assertIn('matchType=domain', get.call_args.args[0])
            receipt = json.loads((Path(temp) / 'last_run.json').read_text())
            self.assertEqual(receipt['historical_sites_total'], 1)

    def test_throttle_stops_provider(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            with patch.object(a.Client, 'get', side_effect=urllib.error.HTTPError('url', 429, 'limited', {}, None)) as get:
                code = a.main(['--source', 'wayback', '--domain', 'example.org', '--domain', 'example.net', '--out', temp])
            self.assertEqual(code, 2)
            self.assertEqual(get.call_count, 1)


if __name__ == '__main__':
    unittest.main()
