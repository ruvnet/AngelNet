#!/usr/bin/env python3
"""Generate standalone animated SVG documentation assets without external dependencies."""
from pathlib import Path
from html import escape

OUT = Path(__file__).resolve().parents[1] / 'docs/assets'
STYLE = '''
text{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.ink{fill:#eef5ff}.muted{fill:#a9b8d0}.cyan{fill:#65e8db}.amber{fill:#ffce83}
.travel{stroke-dasharray:8 18;animation:flow 3s linear infinite}
.pulse{animation:glow 4s ease-in-out infinite}.slow{animation:glow 5s ease-in-out infinite;animation-delay:1s}
@keyframes flow{to{stroke-dashoffset:-104}}
@keyframes glow{0%,100%{opacity:.4}50%{opacity:1}}
@media(prefers-reduced-motion:reduce){*{animation:none!important}.pulse,.slow{opacity:1}}
'''


def frame(title, description, height, body):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="{height}" viewBox="0 0 1280 {height}" role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>
<defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#101e35"/><stop offset="1" stop-color="#080f20"/></linearGradient>
<radialGradient id="halo"><stop stop-color="#1b8f96" stop-opacity=".35"/><stop offset="1" stop-color="#1b8f96" stop-opacity="0"/></radialGradient>
<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#263651" stroke-width=".5"/></pattern>
<style>{STYLE}</style></defs>
<rect width="1280" height="{height}" rx="24" fill="url(#bg)"/>
<rect x="1" y="1" width="1278" height="{height-2}" rx="23" fill="url(#grid)" opacity=".35" stroke="#2b3b55"/>
{body}
</svg>\n'''


def text(x, y, value, size=18, cls='ink', weight=400):
    return f'<text x="{x}" y="{y}" class="{cls}" font-size="{size}" font-weight="{weight}">{escape(value)}</text>'


hero = '''<circle cx="1030" cy="180" r="250" fill="url(#halo)"/>
<path d="M48 63L67 45L86 63M57 58L48 45M77 58L86 45" fill="none" stroke="#65e8db" stroke-width="3" stroke-linecap="round"/>
<rect x="1020" y="38" width="210" height="34" rx="17" fill="#152d3b" stroke="#335459"/>
<circle cx="1042" cy="55" r="4" fill="#65e8db" class="pulse"/>
'''
hero += text(108,61,'GOOD DEEDS DONE',16,'cyan',650)
hero += text(1060,60,'EARLY RELEASE 0.2',13,'cyan',650)
hero += text(48,154,'AngelNet',76,'ink',750)
hero += text(50,207,'Find what needs a closer look.',30,'ink',500)
hero += text(50,247,'Public archives. Traceable evidence. Local retrieval.',19,'muted')
hero += text(50,278,'A starting point for the repair of neglected PHP sites.',19,'muted')
hero += '''<g transform="translate(1010 195)">
<circle r="98" fill="none" stroke="#28465a"/><circle r="69" fill="#102738" stroke="#4b8d93"/>
<path d="M-30 23L0-35L30 23M-18 3H18M-31-6L-65-27L-51 8L-27 20M31-6L65-27L51 8L27 20" fill="none" stroke="#65e8db" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
<circle r="117" fill="none" stroke="#65e8db" stroke-width="2" opacity=".65" class="travel"/>
<circle cx="-98" r="7" fill="#65e8db" class="pulse"/><circle cy="98" r="7" fill="#ffce83" class="slow"/><circle cx="98" r="7" fill="#adc1ff" class="pulse"/>
</g>'''
for x,label,color in [(50,'01  DISCOVER','#65e8db'),(260,'02  PRESERVE','#adc1ff'),(470,'03  REVIEW','#ffce83')]:
    hero += f'<rect x="{x}" y="321" width="190" height="40" rx="8" fill="#12233a" stroke="#2d415d"/>'
    hero += f'<text x="{x+18}" y="347" fill="{color}" font-size="14" font-weight="650">{label}</text>'
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'angelnet-hero.svg').write_text(frame('AngelNet: good deeds done','A discovery and evidence index for reviewing legacy PHP candidates. Animated archive signals surround a winged A. Early release 0.2.',400,hero))

pipe = text(42,49,'FROM ARCHIVE TO REVIEW',24,'ink',700)
pipe += text(42,81,'Two ingestion paths. One evidence model.',18,'muted')
pipe += '''<path d="M294 180H351V250H392M294 332H351V250M662 250H736M1006 250H1050" fill="none" stroke="#304a64" stroke-width="3"/>
<path d="M294 180H351V250H392M294 332H351V250M662 250H736M1006 250H1050" fill="none" stroke="#65e8db" stroke-width="2" class="travel"/>
'''
cards=[(42,124,252,114,'01A','Archive metadata','CDX and Wayback','URL · capture date · source'),
       (42,276,252,114,'01B','WET page text','Byte framed parsing','Text · record ID · hash'),
       (392,170,270,160,'02','Evidence store','SQLite and deduplication','Unknowns stay explicit'),
       (736,170,270,160,'03','Local retrieval','Native RuVector','384 dimensional lexical vectors')]
for x,y,w,h,num,title,subtitle,foot in cards:
    pipe += f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="#111f34" stroke="#38516d"/>'
    pipe += text(x+18,y+27,num,13,'cyan',700)+text(x+18,y+54,title,21,'ink',650)
    pipe += text(x+18,y+80,subtitle,15,'muted')+text(x+18,y+h-12,foot,13,'muted')
pipe += '<rect x="1050" y="186" width="186" height="128" rx="14" fill="#282738" stroke="#92724c"/>'
pipe += text(1070,220,'04',13,'amber',700)+text(1070,249,'Review',24,'ink',650)
pipe += text(1070,276,'CSV · JSONL',16,'muted')+text(1070,299,'Evidence attached',13,'muted')
pipe += '<rect x="42" y="426" width="1194" height="52" rx="10" fill="#102936" stroke="#28515b"/>'
pipe += text(62,459,'Candidate websites receive zero requests from these ingestion scripts.',18,'cyan',500)
(OUT/'archive-pipeline.svg').write_text(frame('AngelNet archive ingestion pipeline','Archive metadata and WET text flow through an evidence store to local vector retrieval and review exports. All stages preserve provenance. Candidate websites are not contacted.',510,pipe))

e = text(42,49,'EVIDENCE IS NOT A VERDICT',24,'ink',700)+text(42,81,'Historical content is a reason to investigate. It is not proof of present neglect.',18,'muted')
e += '<rect x="42" y="119" width="470" height="246" rx="16" fill="#102b35" stroke="#31666d"/>'
e += text(66,157,'OBSERVED',14,'cyan',700)
for i,(label,detail) in enumerate([('PHP shaped URL','A captured path ends in .php'),('Capture timestamp','The archive recorded a page on this date'),('Source identity','File and payload hashes preserve provenance')]):
    y=194+i*67
    e += f'<circle cx="74" cy="{y-6}" r="5" fill="#65e8db" class="pulse"/>'
    e += text(92,y,label,20,'ink',600)+text(92,y+23,detail,15,'muted')
e += '<rect x="594" y="119" width="642" height="246" rx="16" fill="#262337" stroke="#64516a"/>'
e += text(620,157,'STILL UNKNOWN',14,'amber',700)
for i,label in enumerate(['Installed PHP runtime and patch provenance','Whether the current owner or application is the same','Actual maintenance history and exploitability']):
    y=197+i*55
    e += f'<circle cx="628" cy="{y-6}" r="5" fill="#ffce83" class="slow"/>'
    e += text(646,y,label,18,'ink',500)
e += '<path d="M553 137V350" fill="none" stroke="#7784a3" stroke-width="2" class="travel"/>'
e += '<rect x="42" y="397" width="1194" height="58" rx="11" fill="#14233b" stroke="#3b516e"/>'
e += text(66,433,'NEXT STEP',13,'cyan',700)+text(180,434,'Owner or host verification before a repair decision.',21,'ink',550)
(OUT/'evidence-boundary.svg').write_text(frame('Observed facts and unknown security state','Observed URLs, dates and hashes stay separate from unknown runtime, ownership, maintenance and exploitability. Owner or host verification is required before a repair decision.',490,e))
print('Generated three animated SVG assets')
