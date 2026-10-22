# Static archive discovery

The query API is optional. AngelNet can read Common Crawl's published CDXJ files directly, select blocks covering a domain scope, and feed captures into the existing candidate index. This keeps discovery usable when the query service returns gateway errors.

Common Crawl publishes its sorted index as independently compressed blocks, with a companion `cluster.idx` file identifying each block's starting key, filename, offset and length. These are metadata index offsets, not WET offsets. [Official CDXJ documentation](https://commoncrawl.org/cdxj-index)

## Run a bounded discovery pass

```sh
python3 cc_static.py \
  --domain example.org \
  --collection CC-MAIN-2026-43 \
  --blocks-per-domain 10 \
  --max-requests 31 \
  --max-bytes 150994944 \
  --max-seconds 120 \
  --out output/static
```

Repeat `--domain` for up to 20 scopes. Pin the collection explicitly. There is no catalog request, automatic provider fallback, automatic retry or paid API.

1. Download and cache the collection's `cluster.idx`. The cache lives under the selected output directory. This collection's file is 104,520,381 bytes. Other collections can differ; files above 128 MiB are rejected by this implementation.
2. Scan the sorted block keys and select intervals overlapping each domain and its subdomains. Include the preceding block because a domain may start in the middle of a block. Leading `www` scopes search a broader parent interval, then enforce the original scope on capture URLs.
3. Read at most the specified number of blocks per domain, serially. Each request must return HTTP 206 with the exact requested range. Each compressed block is limited to 2 MiB, and its decompressed body to 16 MiB. An oversized block outside the selected scope does not invalidate the index.
4. Validate captures using the existing PHP path, HTTP status, HTML MIME, date and domain rules. Save normalized observations with query strings removed. Export the same SQLite, CSV and JSONL candidate formats as the API path.

The only network destination is `data.commoncrawl.org`, restricted to pinned collection index paths. Redirects are refused. Candidate websites receive no requests. Every successful download records its URL, range, SHA256 and available ETag. The cached cluster is hashed again on each run; its hash identifies the bytes used, rather than serving as an independent authenticity signature.

## Read the receipt

`static-run.json` records the latest attempt, and `runs/` preserves individual receipts. Both successful and failed attempts produce receipts when normal exception handling can complete.

1. `overlapping_blocks` is the total number of blocks intersecting the domain interval in this collection.
2. `selected_blocks` applies the per domain block cap.
3. `blocks_read` counts blocks actually downloaded and decoded.
4. `scoped_records` counts captures whose original URL passes the domain boundary check, before PHP and response filtering.
5. `observations_added` counts newly inserted PHP observations. `sites_total` includes earlier rows in the output database.

Overlapping input scopes can process a capture more than once. SQLite deduplicates identical observations, while processing counts can include repeated work. Prefer disjoint domain scopes for comparable measurements.

`complete_bounded_sample` means the selected blocks completed. It does not mean every website page, every monthly crawl or every block in a capped domain was searched. Compare all three block counts before interpreting an empty result. Any request failure stops the run, retains committed observations and produces `partial` with exit code 2.

## Measured pilot

The initial API pilot failed across WHO, Médecins Sans Frontières and IFRC. A followup exact URL API probe also returned HTTP 504, while the static data host returned HTTP 206. This establishes a usable alternate access path, not the root cause of the API failure.

The first successful static run on ruOS measured:

| Measure | Result |
| :--- | ---: |
| Domain scopes | 3 |
| Index blocks decoded | 7 |
| Captures decoded, including block neighbors | 21,000 |
| Captures inside scope | 13,465 |
| PHP observations added | 43 |
| Indexed hostnames | 4 |
| Downloaded bytes | 106,578,043 |
| Archive requests | 8 |
| Candidate website requests | 0 |
| Elapsed time | 7.319 seconds |

All overlapping blocks for these three scopes were selected in this collection. The retained captures range from October 5 to October 15, 2026. None establish historical age or maintenance status. The local and ruOS candidate exports matched byte for byte. Generated host lists remain private; only aggregate validation is published. See [the sanitized evidence](evidence/static-pilot.json).

A local pass using an existing cluster cache downloaded 2,057,662 bytes in seven requests and took 4.153 seconds. These are single runs on the tested hosts, not throughput guarantees. There were no paid API calls or newly provisioned machines; existing compute charges were not measured.

## How this fits the larger system

Use static CDXJ discovery to establish URL candidates and capture dates. Use WET text and RuVector for topic retrieval in a separately downloaded corpus. A medical topic match cannot establish charitable purpose, and an old capture cannot establish an old runtime. [Common Crawl format guide](https://commoncrawl.org/get-started)

For a small scoped corpus, a future WARC range reader could retrieve original archived response evidence without downloading entire WET segments. That reader is not implemented here. WET offsets cannot be inferred from CDXJ WARC offsets.

The biggest remaining product uncertainty is precision against actual maintenance need. The next useful validation is an owner supplied set of known legacy PHP sites, with deployment history and runtime versions as ground truth. For broad discovery, start from a verified charity or health organization registry; this pilot's three large organizations are not a representative charity sample.

For bulk filtering across thousands of domains, evaluate Common Crawl's columnar index rather than scaling this serial pilot unboundedly. Common Crawl itself recommends the columnar index for bulk queries. No paid query engine is configured by AngelNet. [Index server guidance](https://index.commoncrawl.org/)

## Acceptance

```sh
python3 -m unittest discover -s tests -v
```

Then run the scoped command above in a fresh output directory. A successful live acceptance requires a complete receipt, zero target requests, decoded in scope captures and preserved source hashes. A PHP discovery acceptance additionally requires at least one retained PHP observation. An empty export alone is not a failure or a success claim about maintenance need.
