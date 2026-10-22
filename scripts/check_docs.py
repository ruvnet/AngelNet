#!/usr/bin/env python3
"""Check local documentation links and standalone SVG accessibility and animation."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    checked = 0
    for path in [ROOT/'README.md', ROOT/'CONTRIBUTING.md', ROOT/'SECURITY.md', *sorted((ROOT/'docs').glob('*.md'))]:
        text = re.sub(r'```.*?```', '', path.read_text(), flags=re.S)
        targets = re.findall(r'\]\(([^)]+)\)', text) + re.findall(r'src="([^"]+)"', text)
        for target in targets:
            if target.startswith(('https://','http://','#','mailto:')):
                continue
            assert (path.parent / target.split('#')[0]).exists(), f'Broken link: {path.name}: {target}'
            checked += 1
    assets = list((ROOT/'docs/assets').glob('*.svg'))
    assert len(assets) == 3
    for path in assets:
        text = path.read_text()
        root = ET.fromstring(text)
        assert root.attrib.get('viewBox')
        assert root.find('{http://www.w3.org/2000/svg}title') is not None
        assert root.find('{http://www.w3.org/2000/svg}desc') is not None
        assert '@keyframes' in text and 'prefers-reduced-motion:reduce' in text
        for node in root.iter():
            assert node.tag.rsplit('}',1)[-1] not in ('script','foreignObject','image')
            assert not any(k.lower().startswith('on') for k in node.attrib)
            assert not any('http' in v for k,v in node.attrib.items() if k.endswith('href'))
    print(f'Documentation checks passed: {checked} local links, {len(assets)} animated SVGs')


if __name__ == '__main__':
    main()
