import contextlib
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest

import wet_import as w


def record(text='A legacy community forum', url='https://forum.example.org/index.php?token=private', **updates):
    body = text.encode('utf-8')
    headers = {'WARC-Type':'conversion', 'WARC-Target-URI':url, 'WARC-Date':'2006-01-01T00:00:00Z',
               'Content-Type':'text/plain', 'WARC-Record-ID':'<urn:uuid:fixture>', 'Content-Length':str(len(body))}
    headers.update(updates)
    return b'WARC/1.0\r\n' + ''.join(k+': '+v+'\r\n' for k,v in headers.items()).encode() + b'\r\n' + body + b'\r\n\r\n'


def parse(data, **kwargs):
    return list(w.records(w.Reader(io.BytesIO(data), 1000000, 10), **kwargs))


class WetTests(unittest.TestCase):
    def test_payload_markers_are_not_boundaries(self):
        entries = parse(record('café\nWARC/1.0\nWARC-Target-URI: https://evil.test/a.php\n尾') + record('second'))
        self.assertEqual(len(entries), 2)
        self.assertIn('尾', entries[0][2].decode())
        self.assertEqual(entries[1][2], b'second')

    def test_header_order_case_and_version(self):
        data = record().replace(b'WARC/1.0',b'WARC/1.1').replace(b'WARC-Type:',b'warc-type:')
        _, headers, body = parse(data)[0]
        self.assertIsNotNone(w.document(headers,body,'fixture',[]))

    def test_truncation(self):
        with self.assertRaisesRegex(w.WetError,'truncated_body'):
            parse(record('hello')[:-8])

    def test_length_validation(self):
        for length in ['-1','NaN','999999999999999999999']:
            with self.assertRaises(w.WetError):
                parse(record(**{'Content-Length':length}))

    def test_record_and_decompression_limits(self):
        with self.assertRaisesRegex(w.WetError,'record_byte_budget'):
            parse(record('a'*100), max_record_bytes=10)
        with self.assertRaisesRegex(w.WetError,'decompressed_byte_budget'):
            list(w.records(w.Reader(io.BytesIO(record()),10,10)))

    def test_domain_boundary_and_php(self):
        _, h, b = parse(record())[0]
        doc = w.document(h,b,'fixture',['example.org'])
        self.assertNotIn('token', doc['url'])
        self.assertEqual(doc['http_status'],'not_in_wet')
        self.assertEqual(doc['vulnerability_status'],'not_assessed')
        self.assertIsNone(w.document(h,b,'fixture',['ample.org']))
        h['warc-target-uri']='https://example.org/page.html?next=index.php'
        self.assertIsNone(w.document(h,b,'fixture',[]))
        self.assertEqual(w.document(h,b,'fixture',[],True)['php_signal'],'none')

    def test_info_records_skipped_and_no_date_fabrication(self):
        _,h,b=parse(record())[0]
        h['warc-type']='warcinfo'
        self.assertIsNone(w.document(h,b,'fixture',[]))
        h['warc-type']='conversion'
        del h['warc-date']
        self.assertIsNone(w.document(h,b,'fixture',[]))

    def test_concatenated_gzip_and_dedup(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            root=Path(temp); source=root/'sample.wet.gz'
            source.write_bytes(gzip.compress(record())+gzip.compress(record('other page')))
            args=['--wet',str(source),'--out',str(root/'out')]
            self.assertEqual(w.main(args),0)
            self.assertEqual(w.main(args),0)
            receipt=json.loads((root/'out/wet-run.json').read_text())
            self.assertEqual(receipt['documents_added'],0)
            self.assertEqual(receipt['documents_matched'],2)
            self.assertEqual(len((root/'out/wet-documents.jsonl').read_text().splitlines()),2)
            self.assertFalse((root/'out/.lock').exists())

    def test_corrupt_stream_retains_partial_status(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            root=Path(temp); source=root/'bad.wet'
            source.write_bytes(record()+b'not a record\r\n')
            self.assertEqual(w.main(['--wet',str(source),'--out',str(root/'out')]),2)
            report=json.loads((root/'out/wet-run.json').read_text())
            self.assertEqual(report['status'],'partial')
            self.assertEqual(report['documents_added'],1)


if __name__ == '__main__':
    unittest.main()
