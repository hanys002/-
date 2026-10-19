"""첨부 참고 문서의 표지 구성 및 의미를 바꾸지 않는 적색 강조."""
from __future__ import annotations

import base64
import re
from html import escape
from pathlib import Path

KEY_TERMS = re.compile('|'.join(map(re.escape, sorted([
    '감리관리시스템', '공사대금', '지급보증', '손해배상책임', '무선국자기적합확인서',
    '자기적합확인', '준공검사', '전파차단장치', '교육', '보증', '보험', '공제',
    '의무화', '의무', '금지', '신설', '과태료', '경과조치', '적용례',
], key=len, reverse=True))))


def highlight(value: str) -> str:
    """원문의 지정된 핵심어만 강조하고 나머지 문자와 의미는 그대로 둔다."""
    parts, start = [], 0
    for match in KEY_TERMS.finditer(value):
        parts.append(escape(value[start:match.start()]))
        parts.append('<strong class="important" style="color:#b52525">' + escape(match.group()) + '</strong>')
        start = match.end()
    parts.append(escape(value[start:]))
    return ''.join(parts)


COVER_CSS = '''
@page cover { margin: 0; counter-reset: page 0;
 @bottom-center { content: none; } @bottom-left { content: none; }
 @bottom-right { content: none; } @top-right { content: none; } }
body { margin: 0; }
.cover { page: cover; width: 210mm; height: 297mm; position: relative; break-after: page; color: #17232e; }
.cover-top { position: absolute; top: 0; left: 0; width: 100%; height: 62mm;
 background: linear-gradient(110deg, #0e3c59, #20818e 53%, #d8e9ed); }
.cover-logo { position: absolute; left: 12mm; top: 12mm; padding: 4mm; background: white; border-radius: 2mm; width: 62mm; }
.cover-org { position: absolute; right: 16mm; top: 15mm; text-align: right; color: #10315c; }
.cover-org strong { font-size: 17pt; } .cover-org small { font-size: 9pt; }
.cover-binary { position: absolute; left: 14mm; top: 28mm; color: #7db9c8; font-family: monospace; font-size: 10pt; line-height: 2; }
.cover-wave { position: absolute; top: 0; left: 0; width: 210mm; height: 62mm; }
.cover-band { position: absolute; left: 0; top: 62mm; width: 100%; height: 32mm; background: #102e5d; color: white; text-align: center; }
.cover-band h1 { font-size: 22pt; margin: 10mm 0 0; line-height: 1.3; }
.cover-volume { position: absolute; top: 98mm; right: 16mm; color: #777; font-size: 25pt; font-weight: bold; }
.cover-toc { position: absolute; left: 25mm; right: 16mm; top: 116mm; }
.cover-toc h2 { color: #202830; border: 0; font-size: 16pt; margin: 0 0 6mm; padding: 0; }
.cover-toc a { display: block; color: #17232e; text-decoration: none; font-size: 11pt; line-height: 1.5; padding: 2.5mm 0; }
.cover-toc a::after { content: leader('.') target-counter(attr(href), page); }
.cover-toc .sub { padding-left: 7mm; font-size: 10pt; }
.cover-meta { position: absolute; right: 16mm; top: 230mm; width: 80mm; border-collapse: collapse; font-size: 10pt; }
.cover-meta th, .cover-meta td { border: 0; border-top: 0.3mm solid #a9bccc; border-bottom: 0.3mm solid #a9bccc; padding: 3mm; text-align: center; }
.cover-meta th { width: 23mm; background: #e7edf2; } .cover-meta td { background: #f5f7f9; }
.cover-art { position: absolute; left: 24mm; bottom: 20mm; width: 58mm; height: 42mm; }
.cover-demo { position: absolute; left: 25mm; bottom: 10mm; color: #b52525; font-weight: bold; }
.important { color: #b52525; font-weight: bold; }
tr { break-inside: avoid; }
@media screen { .cover { max-width: 100%; } .cover-toc a::after { content: ''; } }
'''


def cover(report) -> str:
    logo = base64.b64encode((Path(__file__).parent / 'assets/reference-association-logo.png').read_bytes()).decode('ascii')
    toc = [('#monitor-status', '1. 모니터링 현황 및 참고', ''),
           ('#weekly-laws', '2. 금주 공포·시행 법령', ''),
           ('#upcoming-laws', '3. 시행 예정 법령', ''),
           ('#core-laws', '4. 핵심 법령 모니터링', '')]
    for i, name in enumerate(report.core_laws):
        toc.append((f'#core-law-{i}', f'4-{i+1}) {name}', 'sub'))
    toc.append(('#source-status', '5. 대상별 조회 상태 및 추가 확인', ''))
    links = ''.join(f'<a class="{cls}" href="{href}">{escape(label)}</a>' for href, label, cls in toc)
    return f'''<section class="cover">
<div class="cover-top"></div>
<svg class="cover-wave" viewBox="0 0 840 248" xmlns="http://www.w3.org/2000/svg">
<g fill="none" stroke="#8dc6ce" stroke-width="1.4" opacity="0.65">
<path d="M0 195 C210 115 335 220 555 95 S755 30 840 10"/>
<path d="M0 213 C210 133 335 238 555 113 S755 48 840 28"/>
<path d="M0 231 C210 151 335 256 555 131 S755 66 840 46"/></g></svg>
<div class="cover-binary">0101 1100 0110<br>　1011 0010 1101<br>0110 1001 0011</div>
<img class="cover-logo" src="data:image/png;base64,{logo}" alt="한국정보통신기술사회 — 참고 문서의 로고">
<div class="cover-org"><strong>{escape(report.organization)}</strong><br><small>ICT Technical Consultancy</small></div>
<div class="cover-band"><h1>{escape(report.title)}</h1></div>
<div class="cover-volume">Vol. {report.volume}</div>
<nav class="cover-toc"><h2>목 차</h2>{links}</nav>
<svg class="cover-art" viewBox="0 0 230 168" xmlns="http://www.w3.org/2000/svg">
<ellipse cx="115" cy="156" rx="112" ry="10" fill="#e1e6eb"/>
<g fill="#8f3829"><rect x="16" y="87" width="124" height="25" rx="3"/><rect x="23" y="62" width="117" height="25" rx="3"/><rect x="32" y="37" width="110" height="25" rx="3"/></g>
<g fill="#ece1cf"><rect x="20" y="112" width="112" height="5"/><rect x="27" y="87" width="105" height="4"/><rect x="36" y="62" width="98" height="4"/></g>
<g stroke="#c79e3c" fill="none"><path d="M176 24 V140 M143 31 H210" stroke-width="3"/><path d="M143 31 L135 67 H151 Z M210 31 L202 67 H218 Z"/></g>
<path d="M134 67 Q143 83 152 67 M201 67 Q210 83 219 67" fill="#c79e3c"/>
<rect x="154" y="135" width="43" height="9" rx="4" fill="#c79e3c"/></svg>
<table class="cover-meta"><tr><th>보고 기관</th><td>{escape(report.organization)}</td></tr>
<tr><th>점검 기간</th><td>{report.start:%Y.%m.%d} ~<br>{report.end:%Y.%m.%d}</td></tr>
<tr><th>보고일</th><td>{report.today:%Y.%m.%d}</td></tr></table>
{'<p class="cover-demo">예시 데이터 · 실제 조회 아님</p>' if report.demo else ''}
</section>'''
