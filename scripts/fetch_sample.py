#!/usr/bin/env python3
"""Fetch and verify the small official Common Crawl WET format sample."""
import hashlib
from pathlib import Path
import urllib.request

URL = 'https://raw.githubusercontent.com/commoncrawl/whirlwind-python/main/whirlwind.warc.wet.gz'
SHA256 = 'b2f1db3943b2bfbb34ad807c36e5eff315cc28efd474edf5a91cbb4962a1deef'
destination = Path(__file__).resolve().parents[1] / 'samples/whirlwind.warc.wet.gz'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Sample source redirected; review the source before changing it')


def main():
    if destination.exists():
        data = destination.read_bytes()
    else:
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(URL, timeout=20) as response:
            data = response.read(1024 * 1024 + 1)
    if len(data) != 3006 or hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('Sample checksum mismatch; no output written')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_bytes(data)
    print('Verified official Common Crawl sample: 3006 bytes')


if __name__ == '__main__':
    main()
