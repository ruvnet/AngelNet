#!/usr/bin/env python3
"""Discover scoped PHP captures directly from Common Crawl's static CDXJ files."""
import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

import angel_index as index

BASE = 'https://data.commoncrawl.org/cc-index/collections/'
CLUSTER_CAP = 128 * 1024 * 1024
BLOCK_CAP = 2 * 1024 * 1024
INFLATED_CAP = 16 * 1024 * 1024


class StaticClient:
    def __init__(self, max_bytes, max_requests, max_seconds):
        self.max_bytes, self.max_requests = max_bytes, max_requests
        self.deadline = time.monotonic() + max_seconds
        self.requests = self.bytes = 0
        self.last = 0.0
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), index.RefuseRedirect())
        self.resources = []

    def fetch(self, url, sink, cap, byte_range=None):
        if not re.fullmatch(re.escape(BASE) + r'CC-MAIN-\d{4}-\d{2}/indexes/(cluster\.idx|cdx-\d+\.gz)', url):
            raise ValueError('resource_not_allowed')
        if self.requests >= self.max_requests:
            raise ValueError('request_budget_exhausted')
        pause = max(0.0, 0.25 - (time.monotonic() - self.last))
        if time.monotonic() + pause >= self.deadline:
            raise ValueError('time_budget_exhausted')
        if self.bytes >= self.max_bytes:
            raise ValueError('download_budget_exhausted')
        time.sleep(pause)
        headers = {'User-Agent': 'AngelNet/0.2 (passive archive research)', 'Accept-Encoding': 'identity'}
        if byte_range:
            start, length = byte_range
            if start < 0 or not 0 < length <= cap:
                raise ValueError('invalid_range')
            headers['Range'] = f'bytes={start}-{start + length - 1}'
        self.requests += 1
        self.last = time.monotonic()
        timeout = max(0.1, min(20, self.deadline - self.last))
        digest, size = hashlib.sha256(), 0
        request = urllib.request.Request(url, headers=headers)
        with self.opener.open(request, timeout=timeout) as response:
            if response.headers.get('Content-Encoding', 'identity') != 'identity':
                raise ValueError('unexpected_content_encoding')
            if byte_range:
                start, length = byte_range
                cr = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                if response.status != 206 or not cr or tuple(map(int, cr.groups()[:2])) != (start, start + length - 1) or int(cr[3]) <= start + length - 1:
                    raise ValueError('range_not_honored')
            elif response.status != 200:
                raise ValueError('unexpected_status')
            advertised = response.headers.get('Content-Length')
            expected = int(advertised) if advertised is not None else None
            if expected is not None and (expected < 0 or expected > cap or expected > self.max_bytes - self.bytes):
                raise ValueError('download_budget_exhausted')
            if byte_range and expected is not None and expected != byte_range[1]:
                raise ValueError('range_length_mismatch')
            while True:
                if time.monotonic() >= self.deadline:
                    raise ValueError('time_budget_exhausted')
                remaining = min(cap - size, self.max_bytes - self.bytes)
                if remaining == 0:
                    if expected == size or (byte_range and size == byte_range[1]):
                        break
                    raise ValueError('download_budget_exhausted')
                chunk = response.read1(min(65536, remaining))
                if not chunk:
                    break
                self.bytes += len(chunk)
                size += len(chunk)
                digest.update(chunk)
                sink.write(chunk)
            if expected is not None and size != expected:
                raise ValueError('truncated_response')
            if byte_range and size != byte_range[1]:
                raise ValueError('truncated_range')
        result = dict(url=url, bytes=size, sha256=digest.hexdigest(), byte_range=byte_range,
                      etag=response.headers.get('ETag'))
        self.resources.append(result)
        return result


def cluster(client, collection, cache):
    path = cache / (collection + '.idx')
    cache.mkdir(parents=True, exist_ok=True)
    downloaded = not path.exists()
    if downloaded:
        temporary = path.with_suffix('.part')
        try:
            with temporary.open('xb') as stream:
                client.fetch(BASE + collection + '/indexes/cluster.idx', stream, CLUSTER_CAP)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    if not 0 < path.stat().st_size <= CLUSTER_CAP:
        raise ValueError('invalid_cluster_size')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            if time.monotonic() >= client.deadline:
                raise ValueError('time_budget_exhausted')
            digest.update(chunk)
    return path, dict(url=BASE + collection + '/indexes/cluster.idx', bytes=path.stat().st_size,
                      sha256=digest.hexdigest(), cache_hit=not downloaded)


def select_blocks(path, domains, per_domain, deadline=float('inf')):
    """Intersect sorted block key intervals with the root and subdomain SURT range."""
    # SURT drops a leading www label. Search the wider parent interval for such
    # inputs, then enforce the original domain against each capture's real URL.
    lookup = {d: re.sub(r'^www\d*\.', '', d) if d.count('.') >= 2 else d for d in domains}
    bounds = {d: (','.join(reversed(host.split('.'))) + ')',
                  ','.join(reversed(host.split('.'))) + '-') for d, host in lookup.items()}
    selected, counts = {d: [] for d in domains}, dict.fromkeys(domains, 0)

    def consider(block, end):
        for d, (low, high) in bounds.items():
            if block['key'] < high and (end is None or end > low):
                counts[d] += 1
                if len(selected[d]) < per_domain:
                    selected[d].append(block)

    previous = None
    with path.open('r', encoding='utf-8') as stream:
        while True:
            if time.monotonic() >= deadline:
                raise ValueError('time_budget_exhausted')
            line = stream.readline(65537)
            if not line:
                break
            if len(line) > 65536 or not line.endswith('\n'):
                raise ValueError('invalid_cluster_line')
            fields = line.rstrip('\n').split('\t')
            if len(fields) not in (4, 5) or not re.fullmatch(r'cdx-\d+\.gz', fields[1]):
                raise ValueError('invalid_cluster_entry')
            block = dict(key=fields[0], filename=fields[1], offset=int(fields[2]), length=int(fields[3]))
            if not re.fullmatch(r'.+ \d{14}', block['key']) or block['offset'] < 0 or block['length'] <= 0:
                raise ValueError('invalid_cluster_entry')
            if previous:
                if block['key'] < previous['key']:
                    raise ValueError('unsorted_cluster')
                consider(previous, block['key'])
            previous = block
        if previous:
            consider(previous, None)
    return selected, counts


def decode_block(data):
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
        body = stream.read(INFLATED_CAP + 1)
    if len(body) > INFLATED_CAP:
        raise ValueError('inflated_block_too_large')
    for line in body.decode('utf-8').splitlines():
        if len(line) > 65536:
            raise ValueError('cdx_line_too_long')
        key, stamp, payload = line.split(' ', 2)
        row = json.loads(payload)
        if not isinstance(row, dict) or not re.fullmatch(r'\d{14}', stamp):
            raise ValueError('invalid_cdx_row')
        row.update(urlkey=key, timestamp=stamp)
        yield row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', action='append', required=True)
    parser.add_argument('--collection', required=True, help='Pinned CC-MAIN-YYYY-NN collection')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--blocks-per-domain', type=index.bounded_int(1, 100), default=10)
    parser.add_argument('--max-requests', type=index.bounded_int(1, 200), default=40)
    parser.add_argument('--max-bytes', type=index.bounded_int(1, 256 * 1024 * 1024), default=144 * 1024 * 1024)
    parser.add_argument('--max-seconds', type=index.bounded_int(1, 900), default=180)
    parser.add_argument('--years', type=index.bounded_int(1, 100), default=20)
    args = parser.parse_args(argv)
    try:
        domains = sorted(set(index.domain(d) for d in args.domain))
    except ValueError as exc:
        parser.error(str(exc))
    if len(domains) > 20 or not re.fullmatch(r'CC-MAIN-\d{4}-\d{2}', args.collection):
        parser.error('Supply at most 20 domains and a pinned collection')
    os.umask(0o077)
    args.out.mkdir(parents=True, exist_ok=True)
    lock = args.out / '.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        parser.error('Output is locked; inspect the previous process before removing .lock')
    try:
        return run(args, domains)
    finally:
        os.close(fd)
        lock.unlink()


def run(args, domains):
    started = time.monotonic()
    today = dt.datetime.now(dt.timezone.utc).date()
    client = StaticClient(args.max_bytes, args.max_requests, args.max_seconds)
    db = index.init_db(args.out / 'index.sqlite3')
    receipt = dict(source='commoncrawl_static_cdxj', started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                   collection=args.collection, domains=domains, target_requests=0, errors=[],
                   limits=dict(blocks_per_domain=args.blocks_per_domain, max_requests=args.max_requests,
                               max_bytes=args.max_bytes, max_seconds=args.max_seconds),
                   records_examined=0, scoped_records=0, observations_added=0, blocks_read=0,
                   coverage='bounded_block_sample', domain_results={})
    try:
        path, receipt['cluster'] = cluster(client, args.collection, args.out / 'cache')
        selected, counts = select_blocks(path, domains, args.blocks_per_domain, client.deadline)
        for domain in domains:
            receipt['domain_results'][domain] = dict(overlapping_blocks=counts[domain], selected_blocks=len(selected[domain]),
                                                    blocks_read=0, scoped_records=0, php_observations_added=0)
        # Domain order makes partial scope explicit when a request or time budget stops the run.
        for domain in domains:
            stats = receipt['domain_results'][domain]
            for block in selected[domain]:
                buffer = io.BytesIO()
                client.fetch(BASE + args.collection + '/indexes/' + block['filename'], buffer, BLOCK_CAP,
                             (block['offset'], block['length']))
                rows = list(decode_block(buffer.getvalue()))
                stats['blocks_read'] += 1
                receipt['blocks_read'] += 1
                receipt['records_examined'] += len(rows)
                accepted = []
                for row in rows:
                    try:
                        _, host = index.clean_url(row.get('url', ''))
                    except (ValueError, TypeError):
                        continue
                    if host != domain and not host.endswith('.' + domain):
                        continue
                    stats['scoped_records'] += 1
                    receipt['scoped_records'] += 1
                    item = index.observation(row, 'commoncrawl-static:' + args.collection, [domain], today)
                    if item:
                        accepted.append(item)
                added = index.save(db, accepted)
                stats['php_observations_added'] += added
                receipt['observations_added'] += added
    except Exception as exc:
        error = f'http_{exc.code}' if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
        if isinstance(exc, ValueError) and re.fullmatch(r'[a-z_]+', str(exc)):
            error = str(exc)
        receipt['errors'].append(dict(error=error))
    records = index.export(db, args.out, today, args.years)
    db.close()
    receipt.update(provider_requests=client.requests, downloaded_bytes=client.bytes, resources=client.resources,
                   sites_total=len(records), elapsed_seconds=round(time.monotonic() - started, 3),
                   status='partial' if receipt['errors'] else 'complete_bounded_sample')
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    (args.out / 'runs').mkdir(exist_ok=True)
    body = json.dumps(receipt, indent=2) + '\n'
    index.atomic_text(args.out / 'runs' / (stamp + '.json'), body)
    index.atomic_text(args.out / 'static-run.json', body)
    print(body)
    return 2 if receipt['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
