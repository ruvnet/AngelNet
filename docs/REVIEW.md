# Evidence review and improvement plan

AngelNet should measure whether it finds sites whose owners need maintenance help. The count of PHP paths does not answer that question. The current four verified hostnames belong to one organization, and none has a confirmed vulnerability or verified maintenance gap.

## Implemented review queue

The queue consumes local archive candidates and optional owner or hosting exports. It makes no network calls, performs no version probes and makes no changes to a website.

```sh
python3 review_queue.py \
  --sites samples/review-sites.example.jsonl \
  --out output/review-example
```

That input is a synthetic example, clearly labelled as such. Its expected stage is `needs_owner_inventory`. For real data, use the `sites.jsonl` exported by discovery. Always use a new output directory; an existing directory is rejected to preserve earlier assessments.

When an owner supplies deployment evidence:

```sh
python3 review_queue.py \
  --sites output/static/sites.jsonl \
  --inventory owner-inventory.json \
  --out output/review-with-inventory
```

The [inventory template](../samples/owner-inventory.example.json) is illustrative. Replace the placeholders and supply real facts; leaving runtime scope unknown and PHP facts empty intentionally keeps the record incomplete. One inventory binds to one exact hostname. An extra hostname or duplicate inventory is rejected, rather than implicitly applying a parent domain's runtime to every subdomain.

Required inventory facts are a timestamp with timezone, export type and reference. Progressing to advisory review also requires an authorization record reference, evidence about the web runtime, PHP version, vendor, package build and an evidence reference for those facts. The stable numeric PHP version goes in `version`; distribution suffixes and revisions belong in `package_build`. Unsupported version formats fail explicitly.

The software records supplied assertions. It does not authenticate the owner, prove the referenced authorization exists, verify an export against a server or check that a referenced artifact exists. An arbitrary string is not proof. Every supplied inventory is labelled `supplied_not_independently_verified`, including complete records.

## Review stages

| Stage | Missing fact or next action |
| :--- | :--- |
| `needs_owner_inventory` | Obtain an owner or hosting export for this hostname |
| `needs_authorization_record` | Record the applicable authorization reference |
| `needs_web_runtime_evidence` | Establish the serving runtime; the command line executable can be a different installation |
| `needs_fresh_inventory` | Refresh deployment observations outside the chosen age window |
| `needs_build_provenance` | Supply version, vendor, package build and evidence reference |
| `ready_for_advisory_review` | Compare the supplied deployment with applicable vendor advisories and verify prerequisites |

All gaps are retained, while the first gap becomes the displayed stage. All stages retain `vulnerability_status=not_assessed`, `patch_status=not_assessed`, `maintenance_status=unknown` and `owner_identity=not_verified`. A caller supplied security label cannot override these fields.

The default review policies accept inventory up to seven days old and mark archive observations older than ninety days as outside the freshness window. A fresh deployment export can still be reviewed when its earlier discovery capture is old. These windows are tunable assumptions, not guarantees that a server has stayed unchanged.

The input cap is 5 MiB per file, with at most 10,000 site records and 10,000 inventories. Supplied observations from the future and timestamps without a timezone are rejected. Outputs are private by default through the process file mode mask; the usual `output/` directory remains ignored by Git. Export references and package information should stay private.

## PHP support is a separate dimension

[The official PHP lifecycle table](https://www.php.net/supported-versions.php) distinguishes active support, security fixes and branch end of life. The bundled [support snapshot](../data/php-support.json) records the source, observation date and expiry date. After expiry, the queue emits `snapshot_not_current` until an operator refreshes the file from the authoritative source.

A version in a supported branch can still lack a security fix. An unlisted branch may have vendor support or patches that this snapshot does not describe. The queue therefore reports `not_listed_in_upstream_snapshot`, without claiming vulnerability. Version comparison alone is insufficient for distributions that package their own fixes; review the exact vendor build.

The next matching layer should identify packages by ecosystem and name, keep affected ranges and withdrawn advisories, then verify installation and configuration prerequisites. The [OSV schema](https://ossf.github.io/osv-schema/) provides a standard representation for package identities, affected versions and references. OSV matching and vendor advisory ingestion are planned, not implemented here.

## Ranked improvement plan

Scores below are engineering judgment on a scale of 1 to 5, with 5 representing the highest value or effort. They are priorities, not measured model performance.

| Priority | Improvement | Accuracy value | Effort | Acceptance evidence |
| :--- | :--- | ---: | ---: | :--- |
| 1 | Owner supplied web runtime and build evidence | 5 | 2 | Ten consenting organizations with independently checked inventories |
| 2 | Advisory matching with vendor patch provenance | 5 | 4 | Known affected and fixed builds handled correctly; unknowns stay unknown |
| 3 | Verified charity registry plus a labelled evaluation corpus | 4 | 3 | Separate organization identity, topic relevance and maintenance need labels |
| 4 | Archived WARC response enrichment | 3 | 3 | Headers tied to capture timestamps, never silently treated as current |
| 5 | RuVector topic retrieval and broader WET processing | 3 | 4 | Retrieval evaluated on held out labels, with bytes and latency measured |

The first pilot target is ten consenting organizations, covering more than a single large institution. A planning allowance of 15 to 30 minutes per organization for inventory review totals 2.5 to 5 hours of analyst work, excluding owner response time. This is an estimate. The implemented offline queue uses no paid API and no new infrastructure, but analyst and existing compute costs remain real.

Measure three denominators separately: organizations whose identity and mission are established; inventories independently checked; and deployments with an applicable advisory or other verified maintenance need. Report false positives, false negatives and unknowns against owner supplied ground truth. A ten organization pilot is useful for finding workflow errors and is too small to establish reliable population accuracy.

Automated patching should follow a separate acceptance: an owner authorized copy, repeatable backup restoration, regression tests and a deployable reviewed change. Producing more candidate URLs does not make a patch safe.

## Validation

Eleven new tests cover incorrect vulnerability labels, old captures, web versus command line scope, duplicate hosts, dates, provenance gaps, snapshot expiry and output preservation. All eleven passed locally and on ruOS. The full local suite now contains 45 Python tests plus the existing native RuVector integration test.

The real four hostname pilot produced four `needs_owner_inventory` records and zero confirmed vulnerabilities with zero network requests, both locally and on ruOS. That is the correct outcome for the evidence available. It does not mean four safe systems or four vulnerable systems. See the [sanitized validation receipt](evidence/review-pilot.json).

Acceptance command:

```sh
python3 -m unittest discover -s tests -p test_review.py -v
```

All eleven tests must pass. In particular, neither an old capture nor a complete supplied inventory can automatically become a confirmed vulnerability.
