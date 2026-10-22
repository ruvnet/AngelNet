#!/usr/bin/env python3
"""Generate the five standalone animated README diagrams from local evidence."""
import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/assets'
PILOT = json.loads((ROOT / 'docs/evidence/static-pilot.json').read_text())
REVIEW = json.loads((ROOT / 'docs/evidence/review-pilot.json').read_text())
STYLE = '''
text{font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.ink{fill:#edf5ff}.muted{fill:#b0bfd0}.cyan{fill:#70ead6}.amber{fill:#ffd398}.lilac{fill:#b9b5ff}
.flow{stroke-dasharray:5 13;animation:flow 5s linear infinite}
.glow{animation:glow 6s ease-in-out infinite}
.orbit{transform-box:fill-box;transform-origin:center;animation:orbit 28s linear infinite}
.lift{animation:lift 7s ease-in-out infinite}
.phase{animation:phase 12s ease-in-out infinite}
.p2{animation-delay:3s}.p3{animation-delay:6s}.p4{animation-delay:9s}
@keyframes flow{to{stroke-dashoffset:-108}}
@keyframes glow{0%,100%{opacity:.45}50%{opacity:1}}
@keyframes orbit{to{transform:rotate(360deg)}}
@keyframes lift{0%,100%{transform:translateY(0)}50%{transform:translateY(-7px)}}
@keyframes phase{0%,30%,100%{stroke-opacity:.25}10%,20%{stroke-opacity:1}}
@media(prefers-reduced-motion:reduce){*{animation:none!important}.glow{opacity:1}.phase{stroke-opacity:1}}
'''


def text(x, y, value, size=18, cls='ink', weight=400, extra=''):
    return f'<text x="{x}" y="{y}" class="{cls}" font-size="{size}" font-weight="{weight}" {extra}>{escape(str(value))}</text>'


def rect(x, y, w, h, fill='#112333', stroke='#2b4358', rx=16, extra=''):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" {extra}/>'


def line(path, color='#70ead6'):
    return (f'<path d="{path}" fill="none" stroke="#2b4358" stroke-width="3"/>'
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2" class="flow"/>')


def pill(x, y, w, label, color='cyan'):
    return rect(x, y, w, 34, '#102932', '#34545c', 17) + text(x + 16, y + 23, label, 14, color, 650)


def heading(kicker, title, subtitle):
    return text(42, 40, kicker, 13, 'cyan', 700, 'letter-spacing="2"') + text(42, 83, title, 30, 'ink', 650) + text(42, 116, subtitle, 18, 'muted')


def frame(title, desc, height, body):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}" role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}</title>
<desc id="desc">{escape(desc)}</desc>
<defs>
<linearGradient id="bg" x2="1" y2="1"><stop stop-color="#101f30"/><stop offset="1" stop-color="#09131f"/></linearGradient>
<radialGradient id="halo"><stop stop-color="#269e99" stop-opacity=".26"/><stop offset="1" stop-color="#269e99" stop-opacity="0"/></radialGradient>
<pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse"><path d="M48 0H0V48" fill="none" stroke="#345267" stroke-width=".5"/></pattern>
<style>{STYLE}</style>
</defs>
<rect width="1200" height="{height}" rx="22" fill="url(#bg)"/>
<rect x="1" y="1" width="1198" height="{height-2}" rx="21" fill="url(#grid)" opacity=".3" stroke="#456073"/>
{body}
</svg>
'''


def write(name, title, desc, height, body):
    (OUT / name).write_text(frame(title, desc, height, body), encoding='utf-8')


OUT.mkdir(parents=True, exist_ok=True)

# Purpose, product identity, and a quiet network motif. No simulated live state.
hero = '<circle cx="964" cy="250" r="275" fill="url(#halo)"/>'
hero += text(46, 55, 'CARE FOR THE WEB THAT CARES FOR PEOPLE', 14, 'cyan', 700, 'letter-spacing="1.6"')
hero += text(42, 156, 'AngelNet', 82, 'ink', 750)
hero += text(46, 216, 'Find the sites worth helping.', 34, 'ink', 600)
hero += text(46, 263, 'Discover public archive evidence.', 22, 'muted')
hero += text(46, 297, 'Build a reviewable case for maintenance.', 22, 'muted')
hero += pill(46, 344, 164, 'DISCOVERY') + pill(222, 344, 164, 'RETRIEVAL', 'lilac') + pill(398, 344, 200, 'EVIDENCE REVIEW', 'amber')
hero += text(46, 440, 'Python + RuVector + ruOS', 17, 'muted')
hero += text(46, 469, 'Working early release · 0.2.0', 15, 'muted')
hero += '<g transform="translate(960 248)">'
hero += '<circle r="157" fill="none" stroke="#2c4e5c"/><circle r="119" fill="none" stroke="#36576a" stroke-dasharray="3 10"/>'
hero += '<g class="orbit"><circle r="157" fill="none" stroke="#70ead6" stroke-width="2" stroke-dasharray="72 915"/><circle r="119" fill="none" stroke="#b9b5ff" stroke-width="2" stroke-dasharray="42 705"/></g>'
hero += '<circle r="77" fill="#112e39" stroke="#5b9b9f"/><g class="lift">'
hero += '<ellipse cy="-46" rx="23" ry="8" fill="none" stroke="#ffd398" stroke-width="3"/>'
hero += '<path d="M-23 31L0-19L23 31M-13 9H13M-25-5L-58-24L-46 10L-25 23M25-5L58-24L46 10L25 23" fill="none" stroke="#70ead6" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></g>'
for x, y, color in [(-157, 0, '#70ead6'), (79, -136, '#b9b5ff'), (79, 136, '#ffd398')]:
    hero += f'<circle cx="{x}" cy="{y}" r="13" fill="#112333" stroke="{color}"/><circle cx="{x}" cy="{y}" r="5" fill="{color}" class="glow"/>'
hero += '</g>'
hero += text(960, 450, 'Archive → evidence → review', 17, 'muted', 500, 'text-anchor="middle"')
write('angelnet-hero.svg', 'AngelNet: care for the web that cares for people',
      'Find sites worth helping through public archive discovery, local retrieval and evidence review. Working early release 0.2.0. Orbiting signals surround an angel emblem; they are illustrative, not live activity.', 510, hero)

# Metadata and text retrieval have separate paths; review does not require vectors.
pipe = heading('01 / DISCOVER', 'Two inputs. Different jobs.', 'Metadata finds candidates. Page text supports retrieval.')
for x1, y1, x2 in [(354, 232, 440), (752, 232, 838), (354, 475, 440), (752, 475, 838)]:
    pipe += line(f'M{x1} {y1}H{x2}')
cards = [(42, 160, 'PUBLIC ARCHIVE', 'CDX metadata', 'Static files or query API', 'URLs · dates · source', 'cyan'),
         (440, 160, 'LOCAL INDEX', 'PHP candidates', 'SQLite + CSV + JSONL', 'Evidence stays attached', 'cyan'),
         (838, 160, 'REVIEW QUEUE', 'Missing facts', 'Deployment + build history', 'Assessment stays explicit', 'amber'),
         (42, 405, 'LOCAL FILE', 'WET page text', 'Bounded record parsing', 'Text · dates · hashes', 'lilac'),
         (440, 405, 'LOCAL CORPUS', 'Text documents', 'Normalized archive records', 'PHP paths also enter index', 'lilac'),
         (838, 405, 'RUVECTOR', 'Lexical retrieval', '384 dimensional vectors', 'Rank wording similarity', 'lilac')]
for x, y, label, title, detail, foot, color in cards:
    pipe += rect(x, y, 312, 160)
    pipe += text(x+20, y+29, label, 13, color, 700) + text(x+20, y+67, title, 26, 'ink', 650)
    pipe += text(x+20, y+101, detail, 18, 'muted') + text(x+20, y+135, foot, 16, 'muted')
pipe += line('M596 405V320', '#b9b5ff')
pipe += text(610, 369, 'PHP paths', 14, 'lilac')
pipe += line('M994 368V320', '#ffd398')
pipe += pill(847, 353, 294, 'OPTIONAL OWNER INVENTORY', 'amber')
pipe += text(42, 621, 'Discovery reads archive providers. Candidate websites receive zero requests.', 19, 'cyan', 500)
write('archive-pipeline.svg', 'The metadata and WET paths in AngelNet',
      'Archive metadata enters a PHP candidate index and review queue. Local WET files produce text documents for RuVector lexical retrieval, and PHP paths also enter the candidate index. Owner inventory can supplement review. Discovery does not contact candidate websites.', 655, pipe)

e = heading('02 / PRESERVE', 'A candidate is a question.', 'Each record distinguishes an observation, a supplied claim and an unknown.')
for x, label, title, lines, color in [
    (42, 'OBSERVED IN ARCHIVE', 'What was captured', ['PHP URL path', 'Capture timestamp', 'Source identity'], 'cyan'),
    (420, 'SUPPLIED BY OWNER', 'What needs checking', ['Web runtime and build', 'Export date and reference', 'Authorization reference'], 'lilac'),
    (798, 'STILL UNASSESSED', 'What remains open', ['Current vulnerability', 'Actual patch status', 'Maintenance history'], 'amber')]:
    e += rect(x, 163, 352, 232)
    e += text(x+20, 195, label, 13, color, 700) + text(x+20, 234, title, 23, 'ink', 650)
    for i, value in enumerate(lines):
        e += f'<circle cx="{x+25}" cy="{272+i*43}" r="4" class="{color} glow"/>' + text(x+42, 278+i*43, value, 18, 'muted')
e += rect(42, 425, 1108, 64, '#142936', '#43606b', 12)
e += text(64, 464, 'Evidence can support a review. It cannot silently become a security verdict.', 22, 'ink', 550)
write('evidence-boundary.svg', 'Three evidence categories: observed, supplied, unassessed',
      'Archive URLs, dates and sources are observations. Owner runtime and build exports are supplied claims that still need verification. Current vulnerability, patch status and maintenance history remain unassessed.', 520, e)

flow = heading('03 / REVIEW', 'Make the next step explicit.', 'Complete supplied facts prepare a case for advisory review. They do not confirm a flaw.')
for x in [300, 590, 880]:
    flow += line(f'M{x} 247H{x+30}', '#ffd398')
steps = [(42, '01', 'Owner inventory', 'Who supplied it?', 'Source + reference'),
         (332, '02', 'Web runtime', 'What serves this site?', 'Scope + observation date'),
         (622, '03', 'Build evidence', 'Which package is live?', 'Version + vendor + build'),
         (912, '04', 'Review readiness', 'Which advisory applies?', 'Matching is planned')]
for i, (x, number, title, question, detail) in enumerate(steps):
    width = 258 if i < 3 else 238
    flow += rect(x, 177, width, 183, '#112333', '#ffd398', 14, f'class="phase p{i+1}" stroke-width="2"')
    flow += text(x+18, 207, number, 15, 'amber', 700) + text(x+18, 247, title, 21, 'ink', 650)
    flow += text(x+18, 286, question, 16, 'muted') + text(x+18, 325, detail, 15, 'muted')
flow += line('M1040 378V411H171V378', '#b9b5ff')
flow += text(600, 451, 'Missing or stale facts stay in the queue.', 22, 'lilac', 550, 'text-anchor="middle"')
flow += text(600, 487, 'Owner identity, patch status and vulnerability are not verified by this workflow.', 17, 'muted', 400, 'text-anchor="middle"')
write('review-flow.svg', 'The evidence needed before advisory review',
      'The queue asks for an owner inventory, web runtime scope, current build evidence and review readiness. Missing or stale facts stay in the queue. The software does not verify owner identity, patch status or vulnerability, and advisory matching is planned.', 520, flow)

pilot = heading('MEASURED / RUOS PILOT', 'A working path through the archive.', 'One bounded discovery run · October 22, 2026 UTC · No throughput guarantee')
metrics = [(f"{PILOT['scoped_records']:,}", 'scoped captures'),
           (str(PILOT['observations_added']), 'PHP observations'),
           (str(PILOT['sites_total']), 'candidate hostnames'),
           (str(PILOT['target_requests']), 'target requests')]
for i, (value, label) in enumerate(metrics):
    x = 42 + i*282
    pilot += rect(x, 158, 262, 139)
    pilot += text(x+20, 223, value, 47, 'ink', 700) + text(x+20, 265, label, 18, 'muted')
    pilot += f'<path d="M{x+20} 285H{x+242}" stroke="#70ead6" stroke-width="2" class="phase p{i+1}"/>'
pilot += text(44, 343, f"{PILOT['elapsed_seconds']:.3f}s first run", 24, 'cyan', 650)
pilot += text(393, 343, f"{PILOT['downloaded_bytes']/1048576:.1f} MiB downloaded", 24, 'ink', 600)
pilot += text(822, 343, f"{PILOT['provider_requests']} archive requests", 24, 'ink', 600)
repeat = PILOT['final_script_recheck']
pilot += text(44, 382, f"Cached ruOS repeat: {repeat['elapsed_seconds']:.3f}s · {repeat['downloaded_bytes']/1048576:.2f} MiB · identical candidate export", 19, 'muted')
pilot += rect(42, 418, 1108, 72, '#2a2830', '#6f5d48', 12)
pilot += text(65, 449, f"{REVIEW['pilot_sites']} candidates still need owner inventory.", 24, 'amber', 650)
pilot += text(65, 477, 'No vulnerabilities or twenty year maintenance gaps were established.', 18, 'muted')
write('pilot-results.svg', 'Measured discovery results with explicit assessment limits',
      'A ruOS pilot examined 13,465 scoped captures, retained 43 PHP observations across four hostnames and made zero target website requests. The first run took 7.319 seconds. All four candidates still need owner inventory; no vulnerabilities or twenty year maintenance gaps were established.', 522, pilot)
print('Generated five animated SVG assets')
