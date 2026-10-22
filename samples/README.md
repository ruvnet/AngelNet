# Sample provenance

Run `python3 scripts/fetch_sample.py` from the repository root to obtain the official Common Crawl format sample. The downloaded file is ignored by Git.

Source: https://github.com/commoncrawl/whirlwind-python/blob/main/whirlwind.warc.wet.gz

Expected SHA256: `b2f1db3943b2bfbb34ad807c36e5eff315cc28efd474edf5a91cbb4962a1deef`

Expected size: 3,006 bytes compressed. The sample contains two WARC records and one extracted text document from https://an.wikipedia.org/wiki/Escopete, captured in May 2024. It is a format control, not a legacy PHP candidate.

Common Crawl's tutorial repository is distributed under Apache 2.0. Archived third party content retains its original rights and attribution requirements. The fetch script verifies a fixed digest so a changing upstream branch cannot silently change the acceptance input.
