# Common Crawl WET with RuVector

This extension adds local WET parsing and native RuVector retrieval to Angel Index. It follows the archive ingestion architecture in [RuVector ADR 120](https://github.com/ruvnet/RuVector/blob/46d816ddc4c2a8a06cd3613534a79b1d557d858b/docs/adr/ADR-120-wet-processing-pipeline.md). The inspected upstream revision was `46d816ddc4c2a8a06cd3613534a79b1d557d858b`.

The upstream importer targets a shared brain service and detects record starts by lines. This implementation uses local storage, byte lengths, explicit provenance and bounded reads. No shared brain injection, training, messaging, infrastructure provisioning or recurring job is enabled.

## Run

Install the pinned native vector dependency in this directory if it is not already available:

```sh
npm ci --ignore-scripts --no-audit --no-fund
```

Parse a downloaded segment, keeping PHP URL candidates only:

```sh
python3 wet_import.py --wet segment.warc.wet.gz --out output
node wet_vectors.mjs build --input output/wet-documents.jsonl --store output/vectors
node wet_vectors.mjs search --store output/vectors --query 'community discussion forum' --k 5
```

An optional `--domain example.org` filter includes that domain and its subdomains. `--all-text` includes non PHP documents for text retrieval, while leaving them out of the PHP site index. The vector store must be a new directory for each build, which avoids mixing models or presenting interrupted builds as complete. Existing SQLite observations and WET documents deduplicate on repeated imports.

## Data and evidence

WET contains extracted text plus WARC URL, date and record metadata. It does not contain original HTTP headers or full HTML. Use WAT or WARC for those signals. Common Crawl's CDX offsets refer to WARC records; do not reuse them as WET byte offsets. See [Common Crawl's format guide](https://commoncrawl.org/get-started) and [official Python tour](https://github.com/commoncrawl/whirlwind-python).

`wet_import.py` reads gzip members sequentially, recognizes WARC 1.0 and 1.1, parses case insensitive headers, consumes the declared body byte length and skips non conversion records. Embedded `WARC/1.0` text does not split a page. Malformed, truncated or oversized records stop the import with a partial receipt. This is a strict WET subset, not a general purpose WARC implementation: repeated headers and invalid UTF8 are rejected.

Each document includes the sanitized URL, UTC capture date, WARC record ID, refers to ID, source file hash, payload hash and text truncation flag. URL queries and fragments are stripped. Text and URL paths may still contain identifiers; outputs remain local and private. Archive text is untrusted data, never executable instructions.

WET has no HTTP status field, so documents explicitly record `http_status=not_in_wet`; the importer never invents a 200 response. Existing CDX imports retain their separate success response filtering. A PHP suffix is a candidate signal. Runtime version, maintenance state and vulnerability remain unknown or not assessed. No site age or maintenance inference comes from vector similarity.

Outputs add `wet-documents.jsonl`, `wet-run.json` and a `wet_documents` SQLite table to the original site exports. A partial run can retain successfully processed records. The latest WET receipt is replaced on each run; preserve it separately when maintaining an audit history. A record or document cap is labeled as a bounded sample. Gzip integrity beyond the consumed prefix is not verified when a limit stops processing early.

## Retrieval status

Native RuVector 0.2.25 stores 384 dimensional normalized character trigram vectors using its `LocalNGramProvider`. This is lexical similarity, not transformer semantic search. Every build and search reports `semantic_model=false`. The model identity, package version and dimension are pinned in the manifest and checked before querying. Scores are library retrieval scores, not probabilities or security confidence.

The documented ONNX path was checked. The installed root embedder lacks its bundled runtime, and the installed standalone `ruvector-onnx-embeddings-wasm` 0.1.2 loader fails because its binding uses CommonJS inside a package marked as ES modules. No model download or semantic embedding was claimed successful. A future semantic backend needs a corrected, pinned runtime and retrieval tests; it must build a separate store rather than silently changing embeddings in an existing index.

## Bounds and costs

Defaults: scan at most 10,000 records, retain at most 1,000 matched documents, read at most 64 MiB of decompressed data and retain 8,000 text characters per document. The compressed or plain input file itself is also limited to 64 MiB by default. Increase `--max-bytes` explicitly for full segments, up to 1 GiB. Reads are sequential with one body of at most 2 MB in memory. SQLite export scans the accumulated document store without loading all text into Python memory.

Vector builds examine at most 1,000 JSONL lines by default, at most 10,000 with `--limit`, and reject input files above 100 MiB. One million 384 dimensional float32 vectors require 1.536 GB for raw vector values alone, before graph, metadata and page text. Filter records before embedding and partition larger runs. That arithmetic is a storage lower bound, not a measured capacity claim.

There are no paid API calls. Existing ruOS host charges and archive transfer costs depend on the execution environment. No whole crawl download was launched. Downloaded real evidence is only the official 3,006 byte `whirlwind.warc.wet.gz` sample. The sample is a Wikipedia page and validates parsing, not discovery of neglected PHP sites.

## Acceptance

```sh
python3 -m unittest discover -s tests -v
node --test tests/wet_vectors.test.mjs
python3 wet_import.py --wet samples/whirlwind.warc.wet.gz --all-text --out sample-output
node wet_vectors.mjs build --input sample-output/wet-documents.jsonl --store sample-output/vectors
node wet_vectors.mjs search --store sample-output/vectors --query Escopete --k 1
```

Expected: 27 Python tests and one native vector integration test pass. The real sample has two WARC records, one text document and zero PHP candidates. A second import adds zero documents. The vector test verifies persistence and known text ranking across separate processes, provenance retention and rejection of a model mismatch. It does not measure semantic relevance on an independently labeled corpus.
