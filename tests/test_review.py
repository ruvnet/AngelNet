import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest

import review_queue as q


NOW = dt.datetime(2026, 10, 22, 12, tzinfo=dt.timezone.utc)
SUPPORT = json.loads(q.SNAPSHOT.read_text())


def site():
    return dict(host='example.org', first_observed='20060101120000', last_observed='20261021120000',
                vulnerability_status='confirmed', runtime_version='5.3.0',
                evidence=[dict(url='https://example.org/index.php?session=secret',
                               captured_at='20060101120000', source='synthetic_fixture')])


def inventory(**kw):
    result = dict(host='example.org', observed_at='2026-10-22T10:00:00Z',
                  source=dict(kind='owner_export', reference='owner-export-1'),
                  runtime_scope='web_runtime', authorization_reference='consent-1',
                  php=dict(version='8.3.0', vendor='example vendor', package_build='vendor-build-1',
                           evidence_reference='package-inventory-1'))
    result.update(kw)
    return result


def parse_inventory(record):
    return q.inventories(dict(schema_version=1, inventories=[record]), NOW)['example.org']


def review(record=None, now=NOW):
    return q.review(q.archive_site(site(), now), record, SUPPORT, now, 7, 90)


class ReviewTests(unittest.TestCase):
    def test_archive_age_and_injected_labels_never_confirm_vulnerability(self):
        row = review()
        self.assertEqual(row['review_stage'], 'needs_owner_inventory')
        self.assertEqual(row['vulnerability_status'], 'not_assessed')
        self.assertEqual(row['maintenance_status'], 'unknown')
        self.assertEqual(row['upstream_php_support'], 'unknown')
        self.assertNotIn('secret', json.dumps(row))
        self.assertNotIn('runtime_version', row)

    def test_cli_version_is_not_web_runtime_evidence(self):
        row = review(parse_inventory(inventory(runtime_scope='cli_only')))
        self.assertEqual(row['review_stage'], 'needs_web_runtime_evidence')
        self.assertEqual(row['inventory_trust'], 'supplied_not_independently_verified')

    def test_stale_inventory_and_missing_build_are_independent_gaps(self):
        row = review(parse_inventory(inventory(observed_at='2026-09-01T00:00:00Z', php={'version': '8.3.0'})))
        self.assertEqual(row['missing_evidence'], ['needs_fresh_inventory', 'needs_build_provenance'])

    def test_complete_supplied_inventory_only_enables_advisory_review(self):
        record = inventory(vulnerability_status='confirmed')
        row = review(parse_inventory(record))
        self.assertEqual(row['review_stage'], 'ready_for_advisory_review')
        self.assertEqual(row['upstream_php_support'], 'security_fixes_only')
        self.assertEqual(row['vulnerability_status'], 'not_assessed')
        self.assertEqual(row['patch_status'], 'not_assessed')
        self.assertEqual(row['owner_identity'], 'not_verified')

    def test_authorization_reference_is_recorded_not_verified(self):
        row = review(parse_inventory(inventory(authorization_reference=None)))
        self.assertEqual(row['review_stage'], 'needs_authorization_record')
        self.assertEqual(row['owner_identity'], 'not_verified')

    def test_support_snapshot_expires_and_unlisted_is_not_vulnerable(self):
        later = NOW + dt.timedelta(days=40)
        self.assertEqual(q.support_status('8.3.0', SUPPORT, later), 'snapshot_not_current')
        self.assertEqual(q.support_status('7.4.33', SUPPORT, NOW), 'not_listed_in_upstream_snapshot')
        row = inventory()
        row['php']['version'] = '7.4.33'
        self.assertEqual(review(parse_inventory(row))['vulnerability_status'], 'not_assessed')
        self.assertEqual(q.support_status('8.4.0', SUPPORT, NOW), 'active_support')

    def test_inventory_age_boundary(self):
        row = inventory(observed_at='2026-10-15T12:00:00Z')
        self.assertNotIn('needs_fresh_inventory', review(parse_inventory(row))['missing_evidence'])
        row['observed_at'] = '2026-10-15T11:59:59Z'
        self.assertIn('needs_fresh_inventory', review(parse_inventory(row))['missing_evidence'])

    def test_bad_inventory_and_duplicate_hosts_fail(self):
        for values in [dict(observed_at='2027-01-01T00:00:00Z'), dict(observed_at='2026-10-22T10:00:00'),
                       dict(php={'version': '8.3.0-vendor'}), dict(source={'kind': 'archive', 'reference': 'old'})]:
            with self.assertRaises(ValueError):
                parse_inventory(inventory(**values))
        with self.assertRaisesRegex(ValueError, 'duplicate_inventory'):
            q.inventories(dict(schema_version=1, inventories=[inventory(), inventory()]), NOW)

    def test_archive_host_mismatch_rejected(self):
        bad = site()
        bad['evidence'][0]['url'] = 'https://example.org.evil.test/index.php'
        with self.assertRaisesRegex(ValueError, 'archive_evidence_mismatch'):
            q.archive_site(bad, NOW)

    def test_cli_outputs_and_refuses_overwrite_or_scope_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            root = Path(tmp)
            source = root / 'sites.jsonl'
            # Old fixture works regardless of the wall clock after October 2026.
            source.write_text(json.dumps(site()) + '\n')
            args = ['--sites', str(source), '--out', str(root / 'review')]
            self.assertEqual(q.main(args), 0)
            self.assertEqual(q.main(args), 2)
            receipt = json.loads((root / 'review/review-run.json').read_text())
            self.assertEqual(receipt['network_requests'], 0)
            self.assertEqual(receipt['confirmed_vulnerabilities'], 0)
            self.assertEqual(receipt['stages'], {'needs_owner_inventory': 1})
            other = inventory(host='different.example.org', observed_at='2020-01-01T00:00:00Z')
            inv = root / 'inventory.json'
            inv.write_text(json.dumps(dict(schema_version=1, inventories=[other])))
            self.assertEqual(q.main(['--sites', str(source), '--inventory', str(inv), '--out', str(root/'other')]), 2)
            self.assertFalse((root/'other').exists())

    def test_csv_formula_neutralization(self):
        self.assertEqual(q.csv_cell('=HYPERLINK("x")')[0], "'")
        self.assertEqual(q.csv_cell('  @SUM(1)')[0], "'")
        self.assertEqual(q.csv_cell('example.org'), 'example.org')


if __name__ == '__main__':
    unittest.main()
