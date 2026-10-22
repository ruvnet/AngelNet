#!/usr/bin/env python3
"""Build an offline evidence queue without inferring vulnerabilities from archive age."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.parse

import angel_index as index

MAX_INPUT = 5 * 1024 * 1024
SNAPSHOT = Path(__file__).resolve().parent / 'data/php-support.json'


def load_bytes(path):
    with path.open('rb') as stream:
        data = stream.read(MAX_INPUT + 1)
    if len(data) > MAX_INPUT:
        raise ValueError('input_too_large')
    return data, hashlib.sha256(data).hexdigest()


def utc_stamp(value):
    if not isinstance(value, str):
        raise ValueError('invalid_timestamp')
    stamp = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('timestamp_requires_timezone')
    return stamp.astimezone(dt.timezone.utc)


def text(value, name, limit=1024):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError('invalid_' + name)
    return value


def archive_site(raw, now):
    if not isinstance(raw, dict):
        raise ValueError('invalid_site')
    host = index.domain(raw.get('host', ''))
    first = dt.datetime.strptime(raw['first_observed'], '%Y%m%d%H%M%S').replace(tzinfo=dt.timezone.utc)
    last = dt.datetime.strptime(raw['last_observed'], '%Y%m%d%H%M%S').replace(tzinfo=dt.timezone.utc)
    if not first <= last <= now:
        raise ValueError('invalid_archive_dates')
    evidence = raw.get('evidence', [])
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 100:
        raise ValueError('archive_evidence_required')
    cleaned = []
    for item in evidence:
        url, observed_host = index.clean_url(item['url'])
        captured = dt.datetime.strptime(item['captured_at'], '%Y%m%d%H%M%S').replace(tzinfo=dt.timezone.utc)
        if observed_host != host or not first <= captured <= last or not index.PHP_PATH.search(urllib.parse.urlsplit(url).path):
            raise ValueError('archive_evidence_mismatch')
        cleaned.append(dict(url=url, captured_at=item['captured_at'], source=text(item['source'], 'source')))
    return dict(host=host, first_observed=first.isoformat(), last_observed=last.isoformat(),
                archive_recency_days=(now.date() - last.date()).days, evidence=cleaned)


def inventories(raw, now):
    if not isinstance(raw, dict) or type(raw.get('schema_version')) is not int or raw['schema_version'] != 1 or not isinstance(raw.get('inventories'), list):
        raise ValueError('invalid_inventory_schema')
    if len(raw['inventories']) > 10000:
        raise ValueError('too_many_inventories')
    result = {}
    for item in raw['inventories']:
        host = index.domain(item['host'])
        if host in result:
            raise ValueError('duplicate_inventory_host')
        stamp = utc_stamp(item['observed_at'])
        if stamp > now:
            raise ValueError('future_inventory')
        source = item['source']
        if source.get('kind') not in ('owner_export', 'hosting_export'):
            raise ValueError('inventory_source_required')
        reference = text(source['reference'], 'inventory_reference')
        scope = item.get('runtime_scope', 'unknown')
        if scope not in ('web_runtime', 'cli_only', 'unknown'):
            raise ValueError('invalid_runtime_scope')
        authorization = item.get('authorization_reference')
        if authorization is not None:
            authorization = text(authorization, 'authorization_reference')
        runtime = item.get('php', {})
        if not isinstance(runtime, dict):
            raise ValueError('invalid_php_inventory')
        php = {}
        for field in ('version', 'vendor', 'package_build', 'evidence_reference'):
            value = runtime.get(field)
            if value is not None:
                php[field] = text(value, 'php_' + field)
        if 'version' in php and not re.fullmatch(r'\d+\.\d+\.\d+', php['version']):
            raise ValueError('php_version_requires_stable_numeric_release')
        result[host] = dict(observed_at=stamp.isoformat(), age_days=(now - stamp).total_seconds() / 86400,
                            source=dict(kind=source['kind'], reference=reference), runtime_scope=scope,
                            authorization_reference=authorization, php=php)
    return result


def support_status(version, snapshot, now):
    if not version:
        return 'unknown'
    today = now.date()
    if not dt.date.fromisoformat(snapshot['observed_on']) <= today <= dt.date.fromisoformat(snapshot['valid_until']):
        return 'snapshot_not_current'
    branch = '.'.join(version.split('.')[:2])
    support = snapshot['branches'].get(branch)
    if support is None:
        return 'not_listed_in_upstream_snapshot'
    if today > dt.date.fromisoformat(support['security_until']):
        return 'upstream_support_ended'
    if today > dt.date.fromisoformat(support['active_until']):
        return 'security_fixes_only'
    return 'active_support'


def review(site, inventory, snapshot, now, max_inventory_days, max_archive_days):
    gaps = []
    if inventory is None:
        gaps.append('needs_owner_inventory')
    else:
        if not inventory['authorization_reference']:
            gaps.append('needs_authorization_record')
        if inventory['runtime_scope'] != 'web_runtime':
            gaps.append('needs_web_runtime_evidence')
        if inventory['age_days'] > max_inventory_days:
            gaps.append('needs_fresh_inventory')
        if not all(inventory['php'].get(k) for k in ('version', 'vendor', 'package_build', 'evidence_reference')):
            gaps.append('needs_build_provenance')
    version = inventory['php'].get('version') if inventory else None
    return dict(**site, archive_freshness='within_window' if site['archive_recency_days'] <= max_archive_days else 'outside_window',
                inventory=inventory, review_stage=gaps[0] if gaps else 'ready_for_advisory_review',
                missing_evidence=gaps, upstream_php_support=support_status(version, snapshot, now),
                inventory_trust='supplied_not_independently_verified' if inventory else 'not_supplied',
                vulnerability_status='not_assessed', maintenance_status='unknown',
                patch_status='not_assessed', owner_identity='not_verified')


def csv_cell(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sites', type=Path, required=True, help='AngelNet sites.jsonl')
    parser.add_argument('--inventory', type=Path, help='Optional owner supplied inventory JSON')
    parser.add_argument('--out', type=Path, required=True, help='New private output directory')
    parser.add_argument('--inventory-max-age-days', type=index.bounded_int(1, 365), default=7)
    parser.add_argument('--archive-max-age-days', type=index.bounded_int(1, 3650), default=90)
    args = parser.parse_args(argv)
    now = dt.datetime.now(dt.timezone.utc)
    try:
        data, sites_hash = load_bytes(args.sites)
        rows = [json.loads(line) for line in data.decode('utf-8').splitlines() if line.strip()]
        if len(rows) > 10000:
            raise ValueError('too_many_sites')
        sites = [archive_site(row, now) for row in rows]
        if len({s['host'] for s in sites}) != len(sites):
            raise ValueError('duplicate_site_host')
        supplied, inventory_hash = {}, None
        if args.inventory:
            data, inventory_hash = load_bytes(args.inventory)
            supplied = inventories(json.loads(data), now)
            if set(supplied) - {s['host'] for s in sites}:
                raise ValueError('inventory_host_outside_site_list')
        data, snapshot_hash = load_bytes(SNAPSHOT)
        snapshot = json.loads(data)
        records = [review(s, supplied.get(s['host']), snapshot, now,
                          args.inventory_max_age_days, args.archive_max_age_days) for s in sites]
        os.umask(0o077)
        args.out.mkdir(parents=True, exist_ok=False)
        index.atomic_text(args.out / 'review.jsonl', ''.join(json.dumps(r, sort_keys=True) + '\n' for r in records))
        with (args.out / 'review.csv').open('w', newline='', encoding='utf-8') as stream:
            fields = ['host', 'review_stage', 'archive_freshness', 'upstream_php_support',
                      'inventory_trust', 'vulnerability_status', 'maintenance_status', 'patch_status']
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows({k: csv_cell(r[k]) for k in fields} for r in records)
        stages = {}
        for row in records:
            stages[row['review_stage']] = stages.get(row['review_stage'], 0) + 1
        receipt = dict(schema_version=1, created_at=now.isoformat(), sites=len(records), stages=stages,
                       network_requests=0, confirmed_vulnerabilities=0,
                       advisory_matching='not_implemented', owner_identity_verification='not_implemented',
                       inventory_max_age_days=args.inventory_max_age_days,
                       archive_max_age_days=args.archive_max_age_days,
                       input_sha256=sites_hash, inventory_sha256=inventory_hash,
                       support_snapshot_sha256=snapshot_hash, support_source=snapshot['source'],
                       support_snapshot_valid_until=snapshot['valid_until'])
        index.atomic_text(args.out / 'review-run.json', json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        # Input data and exception text may contain private references. Print only a safe category.
        code = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r'[a-z_]+', str(exc)) else type(exc).__name__
        print(json.dumps(dict(status='failed', error=code)), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
