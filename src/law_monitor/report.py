"""10페이지 이내 요약 보고서. 상세 원문은 공식 링크로 제공한다."""
from __future__ import annotations

import re
import base64
from html import escape
from pathlib import Path

from .pipeline import Report
from .design import COVER_CSS, cover, highlight

MAX_PAGES = 10


class ReportValidationError(RuntimeError):
    pass


def h(value) -> str:
    return escape(str(value) if value is not None else "미확인", quote=True)


def excerpt(value: str, limit: int = 180) -> str:
    """공식 설명의 주요내용 부분을 우선 발췌한다. 법률 해석을 생성하지 않는다."""
    if not value.strip():
        return "개정 내용은 공식 원문 확인 필요"
    # 개정이유 전체의 긴 연혁보다 공식 '주요내용'을 우선한다.
    match = re.search(r'(?:[◇◆]\s*|\n\s*(?:[0-9]+[.)]\s*)?)(?:개정이유\s*및\s*)?주요\s*내용\s*[:：]?', value)
    if match:
        value = value[match.end():]
    value = re.sub(r'\s+', ' ', value).strip()
    if len(value) <= limit:
        return value
    cut = value[:limit]
    # 가능하면 마지막 완결 문장까지만 보여 준다. 축약임을 항상 명시한다.
    end = max(cut.rfind('다.'), cut.rfind('함.'), cut.rfind('됨.'))
    if end >= limit // 2:
        cut = cut[:end + 2]
    else:
        space = cut.rfind(' ')
        if space >= limit // 2:
            cut = cut[:space]
    return cut.rstrip() + ' … [일부 발췌]'


def summary(item, limit=180):
    if item is None or item.detail is None:
        return '상세 미확인 — 원문 확인 필요'
    return excerpt(item.detail.reason or item.detail.amendment_text, limit)


def render(report: Report) -> str:
    imminent = sum(0 <= (v.effective - report.today).days <= 30 for v in report.upcoming)
    badge = '[예시 데이터 · 실제 조회 아님] ' if report.demo else ''
    warning = '일부 조회 미완료 — 변경 없음으로 판단하지 마세요.' if report.incomplete else '설정된 대상의 목록 조회 완료'
    analyses = {item.version.serial: item for item in report.analyses}
    parts = [f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>{h(badge + report.title)} · 요약본</title><style>
@page {{ size: A4; margin: 15mm 13mm; @bottom-center {{ content: "- " counter(page) " -"; font-size: 9pt; }} }}
body {{ font-family: "Noto Sans CJK KR", "NanumGothic", sans-serif; color: #193047; font-size: 10pt; line-height: 1.5; }}
header {{ border-bottom: 3px solid #137d91; padding: 10px 0; }}
h1 {{ font-size: 21pt; }} h2 {{ color: #126b80; border-bottom: 1px solid #aac4ce; margin-top: 18px; break-after: avoid; }}
h3 {{ break-after: avoid; }} table {{ border-collapse: collapse; width: 100%; table-layout: fixed; margin: 10px 0; }}
th,td {{ border: 1px solid #c6d6dc; padding: 6px; text-align: left; vertical-align: top; overflow-wrap: anywhere; }}
th {{ background: #e7f1f5; }} thead {{ display: table-header-group; }}
a {{ color: #00677c; }} .notice {{ background: #fff1d6; padding: 9px; }}
.metrics {{ background: #e8f4f5; padding: 12px; }}
.urgent {{ color: #b52525; font-weight: bold; }} .source {{ color: #516574; font-size: 9pt; }}
.card {{ border-left: 3px solid #137d91; padding-left: 10px; margin: 12px 0; }}
{COVER_CSS}</style></head><body>{cover(report)}<header><p><strong>{h(report.organization)}</strong></p>
<h1>{h(badge + report.title)} · 요약본</h1><p>보고일 {report.today} (한국시간) · 점검 기간 {report.start} ~ {report.end}</p></header>
<h2 id="monitor-status">1. 모니터링 현황 및 참고</h2>
<p class="metrics">대상 {len(report.statuses)}개 법령 · 목록 확인 {len(report.statuses) - report.failures}개 · 기간 내 공포·시행 {len(report.weekly)}개 버전 · 30일 내 시행 {imminent}개 버전 · 6개월 내 시행 {len(report.upcoming)}개 버전</p>
<p class="notice">{h(warning)} 통계는 조회 성공한 대상 기준이며 단계별 시행 버전은 각각 집계합니다.</p>
<p class="source">아래 요약은 공식 개정이유·주요내용의 짧은 발췌입니다. 개정문·부칙·신구조문 전문은 첨부하지 않으며 법령명 링크에서 확인할 수 있습니다. 일정은 API 대표 시행일 기준이고, 조문별 적용례·경과조치는 원문 확인이 필요합니다. <strong class="important">적색: 30일 이내 시행 일정과 의무·금지·교육·보증 등 핵심 표현</strong></p>''']

    def version_table(versions, future=False):
        if not versions:
            return '<p>확인된 항목이 없습니다. 조회 실패가 있으면 변경 여부는 미확인입니다.</p>'
        rows = []
        for v in versions:
            day = (v.effective - report.today).days if v.effective else None
            timing = ('D-day' if day == 0 else f'D-{day}') if future else v.amendment
            urgency = ' class="urgent"' if future and day is not None and day <= 30 else ''
            item = analyses.get(v.serial)
            issue = f'<br><strong>미확인: {h(item.error)}</strong>' if item and item.error else ''
            rows.append(f'<tr><td><a href="{h(v.url)}">{h(v.name)}</a><br>{h(v.kind)} 제{h(v.number)}호</td>'
                        f'<td>공포 {h(v.announced)}<br><span{urgency}>시행 {h(v.effective)}</span><br><span{urgency}>{h(timing)}</span></td>'
                        f'<td>{highlight(summary(item))}{issue}</td></tr>')
        return '<table><thead><tr><th style="width:27%">법령 / 원문 링크</th><th style="width:24%">일정</th><th>개정 요약 · 공식 설명 발췌</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'

    parts.extend(['<h2 id="weekly-laws">2. 금주 공포·시행 법령</h2>', version_table(report.weekly),
                  f'<h2 id="upcoming-laws">3. 시행 예정 법령</h2><p>{report.today} ~ {report.horizon} (당일 시행 포함)</p>',
                  version_table(report.upcoming, True), '<h2 id="core-laws">4. 핵심 법령 모니터링</h2>'])
    core = [item for item in report.analyses if item.version.name in report.core_laws]
    for idx, name in enumerate(report.core_laws):
        parts.append(f'<h3 id="core-law-{idx}">4-{idx + 1}) {h(name)}</h3>')
        for item in (i for i in core if i.version.name == name):
            v = item.version
            urgent = v.effective and 0 <= (v.effective - report.today).days <= 30
            style = ' class="urgent"' if urgent else ''
            parts.append(f'<div class="card"><h4{style}>시행 {h(v.effective)}</h4>')
            if item.comparison_note:
                parts.append(f'<p>{h(item.comparison_note)}</p>')
            else:
                parts.append(f'<p>{highlight(summary(item, 420))}</p>')
            if item.error:
                parts.append(f'<p class="notice">{h(item.error)}</p>')
            if item.previous:
                labels = ', '.join(c['article'] for c in item.changes[:8])
                remainder = f' 외 {len(item.changes) - 8}개' if len(item.changes) > 8 else ''
                parts.append(f'<p>기계 비교에서 변경 조문 {len(item.changes)}개 확인: {h(labels + remainder)}. '
                             f'<a href="{h(item.previous.url)}">이전 버전 원문</a></p>')
            parts.append(f'<p><a href="{h(v.url)}">법령·개정이유·부칙 원문 확인</a> · 적용 대상과 경과조치는 원문에서 확인하세요.</p></div>')
    if not core:
        parts.append('<p>별도 핵심 법령 변경 요약이 없습니다. 전체 일정은 위 표를 확인하세요.</p>')
    parts.append('<h2 id="source-status">5. 대상별 조회 상태 및 추가 확인</h2>')
    good = [name for name, status in report.statuses.items() if status == '확인 완료']
    parts.append(f'<p>목록 확인 완료 {len(good)}개: {h(" · ".join(good))}</p>')
    problems = [f'{name}: {status}' for name, status in report.statuses.items() if status != '확인 완료']
    problems.extend(f'{i.version.name} (시행 {i.version.effective}): {i.error}' for i in report.analyses if i.error)
    if problems:
        parts.append('<ul class="notice">' + ''.join('<li>' + h(s) + '</li>' for s in problems) + '</ul>')
    parts.append('<ul>' + ''.join('<li>' + h(s) + '</li>' for s in report.manual_checks) + '</ul>')
    parts.append('<p class="source">자료: 국가법령정보센터 공동활용 API. 설정된 대상만 조회하며 전체 84건 등록부는 아닙니다. 원문 데이터와 전체 기계 비교 결과는 실행 아티팩트 JSON에 보관합니다. 이 보고서는 정보 제공용입니다.</p></body></html>')
    return ''.join(parts)


def write_pdf(html: str, destination: Path, *, organization='한영기술사사무소') -> int:
    from weasyprint import HTML
    from pypdf import PdfReader
    from bs4 import BeautifulSoup

    def deny_fetch(url, *args, **kwargs):
        if url.startswith('data:image/png;base64,'):
            return {'string': base64.b64decode(url.split(',', 1)[1], validate=True), 'mime_type': 'image/png'}
        raise ValueError('보고서 PDF 외부 리소스 요청 금지')

    document = HTML(string=html, url_fetcher=deny_fetch).render()
    if not 1 <= len(document.pages) <= MAX_PAGES:
        raise ReportValidationError(f'PDF {len(document.pages)}페이지: 최대 {MAX_PAGES}페이지 초과, 발송 중단')
    document.write_pdf(destination)
    reader = PdfReader(destination)
    if not 1 <= len(reader.pages) <= MAX_PAGES:
        raise ReportValidationError('저장된 PDF 페이지 수 검증 실패, 발송 중단')
    body = '\n'.join(page.extract_text() or '' for page in reader.pages)
    if organization not in body or '대상별 조회 상태' not in body:
        raise ReportValidationError('PDF 한글 기관명·조회 상태 확인 실패, 발송 중단')
    toc = BeautifulSoup(html, 'html.parser').select('.cover-toc a')
    cover_text = re.sub(r'[\s.\u2026]', '', reader.pages[0].extract_text() or '')
    if not toc or '목차' not in cover_text:
        raise ReportValidationError('PDF 표지·목차 확인 실패, 발송 중단')
    for link in toc:
        target = reader.named_destinations.get(link['href'].lstrip('#'))
        if target is None:
            raise ReportValidationError('PDF 목차 연결 대상 누락, 발송 중단')
        page = reader.get_destination_page_number(target)
        label = re.sub(r'[\s.\u2026]', '', link.get_text())
        if page < 1 or label + str(page) not in cover_text:
            raise ReportValidationError('PDF 목차 페이지 번호 검증 실패, 발송 중단')
    return len(reader.pages)
