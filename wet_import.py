#!/usr/bin/env python3
"""Import bounded local Common Crawl WET files into Angel Index."""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.parse

import angel_index as a


class WetError(ValueError):
    pass


class Reader:
    def __init__(self, stream, max_bytes, max_seconds):
        self.stream, self.max_bytes = stream, max_bytes
        self.count = 0
        self.deadline = time.monotonic() + max_seconds

    def read(self, n, line=False):
        if time.monotonic() > self.deadline:
            raise WetError('time_budget')
        n = min(n, self.max_bytes - self.count + 1)
        result = self.stream.readline(n) if line else self.stream.read(n)
        self.count += len(result)
        if self.count > self.max_bytes:
            raise WetError('decompressed_byte_budget')
        return result


def records(reader, max_records=10000, max_record_bytes=2_000_000):
    """Read WARC 1.0/1.1 framing by bytes, never by text markers in bodies."""
    for number in range(max_records):
        line = reader.read(8193, line=True)
        while line in (b'\r\n', b'\n'):
            line = reader.read(8193, line=True)
        if not line:
            return
        if line.rstrip(b'\r\n') not in (b'WARC/1.0', b'WARC/1.1'):
            raise WetError('invalid_warc_version_or_boundary')
        headers, header_bytes = {}, 0
        while True:
            line = reader.read(8193, line=True)
            header_bytes += len(line)
            if header_bytes > 65536 or len(line) > 8192 or not line:
                raise WetError('invalid_or_oversized_headers')
            if line in (b'\r\n', b'\n'):
                break
            if b':' not in line:
                raise WetError('invalid_header')
            key, value = line.decode('utf-8', errors='strict').split(':', 1)
            key = key.strip().lower()
            if key in headers:
                raise WetError('duplicate_header')
            headers[key] = value.strip()
        length = headers.get('content-length', '')
        if not length.isascii() or not length.isdigit() or len(length) > 12:
            raise WetError('invalid_content_length')
        length = int(length)
        if length > max_record_bytes:
            raise WetError('record_byte_budget')
        body = reader.read(length)
        if len(body) != length:
            raise WetError('truncated_body')
        yield number, headers, body


def document(headers, body, source, scope, all_text=False):
    if headers.get('warc-type', '').lower() != 'conversion':
        return None
    if headers.get('content-type', '').lower().split(';')[0].strip() != 'text/plain':
        return None
    try:
        url, host = a.clean_url(headers.get('warc-target-uri', ''))
        if scope and not any(host == d or host.endswith('.' + d) for d in scope):
            return None
        captured = dt.datetime.fromisoformat(headers.get('warc-date', '').replace('Z', '+00:00'))
        if captured.tzinfo is None or captured > dt.datetime.now(dt.timezone.utc):
            return None
    except ValueError:
        return None
    php = bool(a.PHP_PATH.search(urllib.parse.urlsplit(url).path))
    if not php and not all_text:
        return None
    text = body.decode('utf-8', errors='strict').strip()
    if not text:
        return None
    digest = hashlib.sha256(body).hexdigest()
    stamp = captured.astimezone(dt.timezone.utc).strftime('%Y%m%d%H%M%S')
    identity = hashlib.sha256((url + '\n' + stamp + '\n' + digest).encode()).hexdigest()
    return dict(id=identity, host=host, url=url, captured_at=stamp, source=source,
                warc_record_id=headers.get('warc-record-id', '')[:300],
                warc_refers_to=headers.get('warc-refers-to', '')[:300],
                payload_sha256=digest, text=text[:8000], text_truncated=len(text) > 8000,
                php_signal='archived_php_path' if php else 'none', http_status='not_in_wet',
                maintenance_status='unknown', runtime_version='unknown', vulnerability_status='not_assessed')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wet', type=Path, required=True)
    p.add_argument('--out', type=Path, default=Path('output'))
    p.add_argument('--domain', action='append', default=[])
    p.add_argument('--all-text', action='store_true', help='Include non PHP documents for text retrieval; do not classify them as PHP')
    p.add_argument('--max-records', type=a.bounded_int(1, 1000000), default=10000)
    p.add_argument('--max-documents', type=a.bounded_int(1, 10000), default=1000)
    p.add_argument('--max-bytes', type=a.bounded_int(1024, 1024**3), default=64*1024**2)
    p.add_argument('--max-seconds', type=a.bounded_int(1, 900), default=120)
    args = p.parse_args(argv)
    try:
        scope = [a.domain(d) for d in args.domain]
    except ValueError as exc:
        p.error(str(exc))
    os.umask(0o077)
    args.out.mkdir(parents=True, exist_ok=True)
    try:
        lock = os.open(args.out / '.lock', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        p.error('Output locked; inspect the earlier process before removing .lock')
    started = time.monotonic()
    report = dict(input_name=args.wet.name, format='WET', scanned_records=0, documents_matched=0,
                  documents_added=0, target_requests=0, provider_requests=0, error=None,
                  max_records=args.max_records, max_documents=args.max_documents, max_bytes=args.max_bytes,
                  source_identity='compressed_or_plain_file_sha256', coverage='bounded_sample')
    db, reader = None, None
    try:
        # File hash is bounded independently from decompression; large files must be sampled/split explicitly.
        if args.wet.stat().st_size > args.max_bytes:
            raise WetError('input_file_byte_budget')
        h = hashlib.sha256()
        with args.wet.open('rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        report['input_sha256'] = h.hexdigest()
        source = 'wet:' + h.hexdigest()
        db = a.init_db(args.out / 'index.sqlite3')
        db.execute('CREATE TABLE IF NOT EXISTS wet_documents (id TEXT PRIMARY KEY, json TEXT NOT NULL)')
        opener = gzip.open if args.wet.suffix == '.gz' else open
        with opener(args.wet, 'rb') as f:
            reader = Reader(f, args.max_bytes, args.max_seconds)
            for number, headers, body in records(reader, args.max_records):
                report['scanned_records'] += 1
                doc = document(headers, body, source, scope, args.all_text)
                if doc:
                    report['documents_matched'] += 1
                    with db:
                        result = db.execute('INSERT OR IGNORE INTO wet_documents VALUES (?,?)',
                                            (doc['id'], json.dumps(doc, sort_keys=True)))
                        report['documents_added'] += result.rowcount
                        if doc['php_signal'] != 'none':
                            db.execute('INSERT OR IGNORE INTO observations VALUES (?,?,?,?)',
                                       (doc['host'], doc['url'], doc['captured_at'], source))
                    if report['documents_matched'] >= args.max_documents:
                        report['stop_reason'] = 'document_limit'
                        break
            else:
                report['stop_reason'] = 'record_limit' if report['scanned_records'] >= args.max_records else 'eof'
    except Exception as exc:
        report['error'] = str(exc) if isinstance(exc, WetError) else type(exc).__name__
    finally:
        if db is not None:
            a.export(db, args.out, dt.datetime.now(dt.timezone.utc).date(), 20)
            with (args.out / 'wet-documents.jsonl.tmp').open('w', encoding='utf-8') as f:
                for (value,) in db.execute('SELECT json FROM wet_documents ORDER BY id'):
                    f.write(value + '\n')
            (args.out / 'wet-documents.jsonl.tmp').replace(args.out / 'wet-documents.jsonl')
            db.close()
        report['decompressed_bytes'] = reader.count if reader else 0
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        report['status'] = 'partial' if report['error'] else 'complete_bounded_sample'
        a.atomic_text(args.out / 'wet-run.json', json.dumps(report, indent=2) + '\n')
        os.close(lock)
        (args.out / '.lock').unlink()
    print(json.dumps(report, indent=2))
    return 2 if report['error'] else 0


if __name__ == '__main__':
    sys.exit(main())
