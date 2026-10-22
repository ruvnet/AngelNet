# Operating AngelNet

Use [static discovery](STATIC.md) for the tested direct index path, [WET ingestion](WET.md) for downloaded text and [evidence review](REVIEW.md) for owner supplied inventories. This guide covers metadata APIs, offline imports, ruOS execution and recovery.

## Metadata API discovery

```sh
python3 angel_index.py \
  --domain example.org \
  --wayback \
  --out output/api
```

The default source is the latest Common Crawl collection. `--wayback` adds historical enrichment for up to ten indexed hosts. Repeat `--domain` for up to 20 scopes, including their subdomains. Requests go to archive providers, not candidate websites.

To discover historical PHP paths directly through Wayback:

```sh
python3 angel_index.py \
  --source wayback --domain example.org \
  --years 20 --out output/historical
```

`historical_php_review` means a retained capture exceeds the selected age threshold. It does not mean the site has gone without maintenance. `first_observed` is the earliest retained observation, not necessarily the first capture ever made.

Both providers failed during the initial live controls: Common Crawl returned HTTP 504 and Wayback returned HTTP 503. Those runs were recorded as partial. The later static index pilot succeeded. Provider availability remains independent of local parser correctness.

## Repeatable sampling and offline import

Pin the Common Crawl collection and change the page deliberately:

```sh
python3 angel_index.py \
  --domain example.org --collection CC-MAIN-2026-43 \
  --page 1 --out output/api
```

Pages can overlap after filtering. Observations deduplicate, but each run remains a bounded sample. For broad discovery, prepare a selection using the [Common Crawl columnar index](https://index.commoncrawl.org/) instead of looping over the public query service.

Import a local CDX JSONL export when the provider is unavailable or discovery happened elsewhere:

```sh
python3 angel_index.py \
  --input captures.jsonl --limit 1000 \
  --out output/import
```

Each line needs `url` or `original`, `timestamp` as UTC `YYYYMMDDhhmmss`, `status` or `statuscode`, and `mime` or `mimetype`. The importer retains status 200 HTML records with eligible PHP paths. Input provenance includes the hash of the consumed prefix. Preserve the original source separately.

## Budgets and completion

| Metadata API default | Bound |
| :--- | :--- |
| Examined records | 100 |
| Provider requests | 20 |
| Request spacing | At least 2 seconds between starts |
| Run budget | 180 seconds |
| Socket timeout | 15 seconds |
| Response body | 2 MB |

Exit code `0` means the bounded sample completed, including an empty sample. Exit code `2` means invalid arguments or partial work. Read `last_run.json` or `static-run.json` before interpreting counts. A failed request followed by an empty export does not establish that no sites exist.

Time budgets are cooperative. A blocking read can exceed the deadline by a socket timeout. Use a process supervisor for a stricter deadline. Exports include prior records in the same database, so compare `observations_added` with `sites_total`.

## Run on ruOS

ruOS provides the execution host and command channel. It does not change the discovery or assessment contract.

1. Use `desktop_status` to select a running desktop. A provisioning flag alone does not establish availability.
2. Clone the repository into a task directory on that desktop. Install the pinned Node dependencies only if vector retrieval is needed.
3. Use `desktop_exec` with an explicit machine ID and a bounded command. For example, from the repository directory:

```sh
python3 angel_index.py --domain example.org --max-seconds 90 --max-requests 6 --out output/api
```

4. Set the executor timeout to 120 seconds for that command. Verify completion and inspect the resulting receipt. Choose limits appropriate to static discovery when using `cc_static.py` instead.

The scripts do not provision machines or create schedules. Keep credentials, machine identifiers and private execution transcripts out of the repository.

## Recovery

| Symptom | Next action |
| :--- | :--- |
| HTTP 429 or 503 | Stop calls to that provider and inspect the partial receipt |
| HTTP 504 or timeout | Treat coverage as incomplete; use static discovery or a local export |
| Output lock exists | Check the earlier process before removing `.lock` |
| Vector directory exists | Choose a new store directory and retain the previous result |
| Review directory exists | Choose a new review directory for a separate receipt |
| Native backend unavailable | Check platform support and reinstall from the lockfile |
| WET record or byte budget exceeded | Inspect the partial receipt; deliberately increase the bound or choose smaller input |

SQLite observations commit in batches. Exports are individually replaced atomically, so interruption can leave exports from different runs until a successful rerun. A vector directory without its manifest is incomplete. The latest WET receipt is replaced on each import; preserve copies when retaining a run history.

The largest operational uncertainty is archive coverage. Keep the scope, collection, selected blocks or pages, limits and failures beside each export. Do not use a completed bounded sample as a claim of exhaustive coverage.

## Acceptance

From a fresh checkout, run this offline review demonstration:

```sh
python3 review_queue.py \
  --sites samples/review-sites.example.jsonl \
  --out output/operations-check
```

Expect one synthetic candidate in `needs_owner_inventory`, zero network requests and no confirmed vulnerability. Inspect `output/operations-check/review-run.json` and `review.jsonl`. Run `npm test` and `npm run check:docs` for the fixture suite and documentation checks.
