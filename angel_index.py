#!/usr/bin/env python3
"""Build a passive PHP review index from public archive metadata. Python 3.10+."""
import argparse
import csv
import datetime as dt
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = '0.1.0'
ALLOWED = {'index.commoncrawl.org', 'web.archive.org'}
PHP_PATH = re.compile(r'\.php(?:[34578])?(?:/|$)', re.I)
MAX_BODY = 2_000_000


def domain(value):
    value = value.strip().lower().rstrip('.').encode('idna').decode('ascii')
    if len(value) > 253 or '.' not in value or not all(
        re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', x)
        for x in value.split('.')
    ):
        raise ValueError('Expected a domain such as example.org, without a URL or wildcard')
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise ValueError('IP addresses are not supported')


def clean_url(value):
    if not isinstance(value, str) or len(value) > 8192 or any(ord(c) < 32 for c in value):
        raise ValueError('invalid URL')
    p = urllib.parse.urlsplit(value)
    if p.scheme not in ('http', 'https') or p.username or p.password or p.port not in (None, 80, 443):
        raise ValueError('unsupported URL')
    host = domain(p.hostname or '')
    path = p.path or '/'
    # Deliberately remove query strings and fragments; never persist session tokens there.
    return urllib.parse.urlunsplit((p.scheme, host, path, '', '')), host


def cutoff_date(today, years):
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


def observation(row, source, scope, today):
    if not isinstance(row, dict):
        return None
    try:
        url, host = clean_url(row.get('url', row.get('original', '')))
        stamp = str(row['timestamp'])
        if not re.fullmatch(r'\d{14}', stamp):
            return None
        captured = dt.datetime.strptime(stamp, '%Y%m%d%H%M%S')
        if captured.date() > today or not PHP_PATH.search(urllib.parse.urlsplit(url).path):
            return None
        if scope and not any(host == d or host.endswith('.' + d) for d in scope):
            return None
        if str(row.get('status', row.get('statuscode', ''))) != '200':
            return None
        if row.get('mime', row.get('mimetype', '')) not in ('text/html', 'application/xhtml+xml'):
            return None
        return (host, url, stamp, source)
    except (ValueError, KeyError, TypeError):
        return None


class RefuseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('provider_redirect_refused')


class Client:
    def __init__(self, max_requests=20, delay=2.0, timeout=15, max_seconds=180):
        self.max_requests, self.delay, self.timeout = max_requests, delay, timeout
        self.deadline = time.monotonic() + max_seconds
        self.count, self.last = 0, 0.0
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RefuseRedirect())

    def get(self, url):
        p = urllib.parse.urlsplit(url)
        if p.scheme != 'https' or p.hostname not in ALLOWED or p.port or p.username or p.password:
            raise ValueError('provider_not_allowed')
        if self.count >= self.max_requests:
            raise ValueError('request_budget_exhausted')
        pause = max(0, self.delay - (time.monotonic() - self.last))
        if time.monotonic() + pause >= self.deadline:
            raise ValueError('time_budget_exhausted')
        time.sleep(pause)
        self.count += 1
        self.last = time.monotonic()
        req = urllib.request.Request(url, headers={'User-Agent': 'AngelIndex/0.1 (archive metadata research)',
                                                  'Accept-Encoding': 'identity'})
        timeout = max(0.1, min(self.timeout, self.deadline - time.monotonic()))
        with self.opener.open(req, timeout=timeout) as response:
            chunks, size = [], 0
            while True:
                if time.monotonic() >= self.deadline:
                    raise ValueError('time_budget_exhausted')
                chunk = response.read1(min(65536, MAX_BODY + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_BODY:
                    raise ValueError('provider_response_too_large')
            return b''.join(chunks).decode('utf-8')


def cc_query(collection, host, limit, page):
    if not re.fullmatch(r'CC-MAIN-\d{4}-\d{2}', collection):
        raise ValueError('invalid_collection')
    params = [('url', host), ('matchType', 'domain'), ('output', 'json'),
              ('filter', '=status:200'), ('filter', '=mime:text/html'),
              ('filter', r'url:.*\.php[34578]?([/?#].*)?$'),
              ('page', str(page)), ('pageSize', '1'), ('limit', str(limit))]
    return 'https://index.commoncrawl.org/' + collection + '-index?' + urllib.parse.urlencode(params)


def wayback_query(host, cutoff, limit, match_type='host'):
    params = [('url', host), ('matchType', match_type), ('output', 'json'),
              ('fl', 'timestamp,original,statuscode,mimetype'), ('filter', 'statuscode:200'),
              ('filter', 'mimetype:text/html'), ('filter', r'original:.*\.php[34578]?([/?#].*)?$'),
              ('to', cutoff.strftime('%Y%m%d') + '235959'), ('limit', str(limit))]
    return 'https://web.archive.org/cdx/search/cdx?' + urllib.parse.urlencode(params)


def init_db(path):
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS observations (host TEXT, url TEXT, captured_at TEXT, '
               'source TEXT, PRIMARY KEY(url,captured_at,source))')
    db.execute('CREATE INDEX IF NOT EXISTS observations_host ON observations(host)')
    return db


def save(db, rows):
    before = db.total_changes
    with db:
        db.executemany('INSERT OR IGNORE INTO observations VALUES (?,?,?,?)', rows)
    return db.total_changes - before


def sites(db, today, years):
    cutoff = cutoff_date(today, years).strftime('%Y%m%d') + '235959'
    for host, first, last, count in db.execute(
        'SELECT host, MIN(captured_at), MAX(captured_at), COUNT(DISTINCT url) '
        'FROM observations GROUP BY host ORDER BY MIN(captured_at),host'
    ):
        old = first <= cutoff
        yield dict(host=host, php_signal='archived_php_path', first_observed=first,
                   last_observed=last, archived_php_url_count=count,
                   archive_age_at_least_years=years if old else None,
                   review_priority='historical_php_review' if old else 'php_review',
                   maintenance_status='unknown', runtime_version='unknown',
                   vulnerability_status='not_assessed', current_reachability='not_checked',
                   identity_continuity='unknown',
                   evidence=[dict(url=u, captured_at=t, source=s) for u,t,s in db.execute(
                       'SELECT url,captured_at,source FROM observations WHERE host=? '
                       'ORDER BY captured_at,url,source LIMIT 5', (host,))])


def atomic_text(path, text):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def export(db, out, today, years):
    records = list(sites(db, today, years))
    atomic_text(out / 'sites.jsonl', ''.join(json.dumps(r, sort_keys=True) + '\n' for r in records))
    fields = ['host', 'php_signal', 'first_observed', 'last_observed', 'archived_php_url_count',
              'archive_age_at_least_years', 'review_priority', 'maintenance_status',
              'runtime_version', 'vulnerability_status', 'current_reachability', 'identity_continuity']
    with (out / 'sites.csv.tmp').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
    (out / 'sites.csv.tmp').replace(out / 'sites.csv')
    return records


def bounded_int(low, high):
    def parse(value):
        n = int(value)
        if not low <= n <= high:
            raise argparse.ArgumentTypeError(f'Expected {low} to {high}')
        return n
    return parse


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', action='append', default=[], help='Domain scope; includes subdomains. Repeat up to 20 times.')
    parser.add_argument('--input', type=Path, help='Offline JSONL of CDX records. No discovery calls in this mode.')
    parser.add_argument('--collection', default='latest', help='Common Crawl collection ID, or latest')
    parser.add_argument('--source', choices=['commoncrawl', 'wayback'], default='commoncrawl',
                        help='Discovery provider. Wayback discovers historical PHP paths directly.')
    parser.add_argument('--page', type=bounded_int(0, 10000), default=0, help='One CC page per domain; record the page for coverage')
    parser.add_argument('--wayback', action='store_true', help='Enrich up to ten indexed hosts with old Wayback metadata')
    parser.add_argument('--out', type=Path, default=Path('output'))
    parser.add_argument('--limit', type=bounded_int(1, 10000), default=100, help='Maximum input records examined this run')
    parser.add_argument('--max-requests', type=bounded_int(1, 50), default=20)
    parser.add_argument('--max-seconds', type=bounded_int(1, 900), default=180)
    parser.add_argument('--years', type=bounded_int(1, 100), default=20)
    args = parser.parse_args(argv)
    try:
        scope = sorted(set(domain(d) for d in args.domain))
    except ValueError as exc:
        parser.error(str(exc))
    if len(scope) > 20 or (not scope and not args.input):
        parser.error('Supply 1 to 20 domains, or a local JSONL input file')
    os.umask(0o077)
    args.out.mkdir(parents=True, exist_ok=True)
    # Prevent concurrent writers and inconsistent CSV/JSONL exports. Stale locks need review.
    lock_path = args.out / '.lock'
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        parser.error('Output is locked; inspect the previous process before removing .lock')
    try:
        return run(args, scope)
    finally:
        os.close(lock_fd)
        lock_path.unlink()


def run(args, scope):
    started = time.monotonic()
    today = dt.datetime.now(dt.timezone.utc).date()
    client = Client(max_requests=args.max_requests, max_seconds=args.max_seconds)
    db = init_db(args.out / 'index.sqlite3')
    receipt = dict(version=VERSION, started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                   domains=scope, collection=args.collection, page=args.page,
                   limit=args.limit, max_requests=args.max_requests, max_seconds=args.max_seconds,
                   years=args.years, target_requests=0, provider_requests=0, records_examined=0,
                   observations_added=0, errors=[], coverage='bounded_sample',
                   input_sha256=None, wayback_requested=args.wayback)
    receipt['discovery_source'] = 'import' if args.input else args.source

    def ingest(rows, source, budget):
        accepted = []
        for i, row in enumerate(rows):
            if i >= budget:
                break
            receipt['records_examined'] += 1
            item = observation(row, source, scope, today)
            if item:
                accepted.append(item)
        receipt['observations_added'] += save(db, accepted)

    def record_error(provider, exc):
        # Do not echo raw server responses, URLs, input lines or exception text.
        code = f'http_{exc.code}' if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
        if isinstance(exc, ValueError) and str(exc) in {
            'request_budget_exhausted', 'time_budget_exhausted', 'provider_response_too_large',
            'provider_redirect_refused', 'provider_not_allowed', 'invalid_collection'}:
            code = str(exc)
        receipt['errors'].append(dict(provider=provider, error=code))

    try:
        if args.input:
            digest = hashlib.sha256()
            rows = []
            with args.input.open('rb') as f:
                for _ in range(args.limit):
                    line = f.readline(65537)
                    if not line:
                        break
                    if len(line) > 65536:
                        raise ValueError('input_line_too_long')
                    digest.update(line)
                    rows.append(json.loads(line))
            receipt['input_sha256'] = digest.hexdigest()
            receipt['input_hash_scope'] = 'consumed_prefix'
            ingest(rows, 'import:' + digest.hexdigest(), args.limit)
        elif args.source == 'wayback':
            receipt['collection'] = None
            for host in scope:
                remaining = args.limit - receipt['records_examined']
                if remaining <= 0:
                    break
                try:
                    body = json.loads(client.get(wayback_query(host, cutoff_date(today, args.years), remaining, 'domain')))
                    if body:
                        ingest((dict(zip(body[0], row)) for row in body[1:]), 'wayback:cdx', remaining)
                except Exception as exc:
                    record_error('wayback:' + host, exc)
                    if isinstance(exc, urllib.error.HTTPError) and exc.code in (429, 503):
                        break
        else:
            collection = args.collection
            if collection == 'latest':
                catalog = json.loads(client.get('https://index.commoncrawl.org/collinfo.json'))
                collection = catalog[0]['id']
            receipt['collection'] = collection
            discovery_limit = args.limit if not args.wayback else max(1, args.limit - min(50, args.limit // 2))
            for host in scope:
                remaining = discovery_limit - receipt['records_examined']
                if remaining <= 0:
                    break
                try:
                    body = client.get(cc_query(collection, host, remaining, args.page))
                    ingest((json.loads(line) for line in body.splitlines() if line.strip()),
                           'commoncrawl:' + collection, remaining)
                except Exception as exc:
                    record_error('commoncrawl:' + host, exc)
                    if isinstance(exc, urllib.error.HTTPError) and exc.code in (429, 503):
                        break
        if args.wayback and (args.input or args.source != 'wayback'):
            hosts = [r['host'] for r in sites(db, today, args.years)
                     if not scope or any(r['host'] == d or r['host'].endswith('.' + d) for d in scope)][:10]
            for host in hosts:
                remaining = args.limit - receipt['records_examined']
                if remaining <= 0:
                    receipt['errors'].append(dict(provider='wayback', error='record_budget_exhausted'))
                    break
                try:
                    body = json.loads(client.get(wayback_query(host, cutoff_date(today, args.years), min(5, remaining))))
                    if body:
                        ingest((dict(zip(body[0], row)) for row in body[1:]), 'wayback:cdx', remaining)
                except Exception as exc:
                    record_error('wayback:' + host, exc)
                    if isinstance(exc, urllib.error.HTTPError) and exc.code in (429, 503):
                        break
    except Exception as exc:
        record_error('input_or_catalog', exc)
    records = export(db, args.out, today, args.years)
    db.close()
    receipt.update(provider_requests=client.count, sites_total=len(records),
                   historical_sites_total=sum(r['archive_age_at_least_years'] is not None for r in records),
                   elapsed_seconds=round(time.monotonic() - started, 3),
                   status='partial' if receipt['errors'] else 'complete_bounded_sample')
    run_id = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    (args.out / 'runs').mkdir(exist_ok=True)
    atomic_text(args.out / 'runs' / (run_id + '.json'), json.dumps(receipt, indent=2) + '\n')
    atomic_text(args.out / 'last_run.json', json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    return 2 if receipt['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
