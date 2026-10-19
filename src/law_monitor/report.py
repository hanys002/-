"""메일 HTML과 인쇄용 PDF에 같은 내용을 사용한다. 외부 자료는 모두 escape."""
from __future__ import annotations

from html import escape
from pathlib import Path

from .pipeline import Report


def h(value) -> str:
    return escape(str(value) if value is not None else "미확인", quote=True)


def render(report: Report) -> str:
    imminent = sum(0 <= (v.effective - report.today).days <= 30 for v in report.upcoming)
    badge = "[예시 데이터 · 실제 조회 아님] " if report.demo else ""
    warning = "일부 조회 미완료 — 변경 없음으로 판단하지 마세요." if report.incomplete else "설정된 대상의 목록 조회 완료"
    parts = [f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>{h(badge + report.title)}</title><style>
@page {{ size: A4; margin: 17mm 13mm; @bottom-center {{ content: counter(page) " / " counter(pages); font-size: 9pt; }} }}
body {{ font-family: "Noto Sans CJK KR", "NanumGothic", sans-serif; color: #193047; font-size: 10pt; line-height: 1.6; }}
header {{ border-bottom: 4px solid #137d91; padding: 14px 0; }}
h1 {{ font-size: 23pt; }} h2 {{ color: #126b80; border-bottom: 1px solid #aac4ce; padding-top: 15px; }}
h3 {{ break-after: avoid; }} table {{ border-collapse: collapse; width: 100%; table-layout: fixed; margin: 12px 0; }}
th,td {{ border: 1px solid #c6d6dc; padding: 7px; text-align: left; vertical-align: top; overflow-wrap: anywhere; }}
th {{ background: #e7f1f5; }} thead {{ display: table-header-group; }}
a {{ color: #00677c; }} .notice {{ background: #fff1d6; padding: 12px; }}
.metrics {{ background: #e8f4f5; padding: 14px; font-size: 12pt; }}
.urgent {{ color: #b52525; font-weight: bold; }} .source {{ color: #516574; font-size: 9pt; }}
.excerpt {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
</style></head><body><header><p><strong>{h(report.organization)}</strong> · 정보통신 · 설계 · 감리 · 공사업</p>
<h1>{h(badge + report.title)}</h1><p>보고일 {report.today} (한국시간) · 점검 기간 {report.start} ~ {report.end}</p></header>
<h2>1. 모니터링 현황 및 참고</h2>
<p class="metrics">대상 {len(report.statuses)}개 법령 · 목록 확인 {len(report.statuses) - report.failures}개 · 기간 내 공포·시행 {len(report.weekly)}개 버전 · 30일 내 시행 {imminent}개 버전 · 6개월 내 시행 {len(report.upcoming)}개 버전</p>
<p class="notice">{h(warning)} 통계는 조회 성공한 대상 기준입니다. 한 법령의 단계별 시행 버전은 각각 집계합니다.</p>
<p>자료: 국가법령정보센터 공동활용 API의 현행·시행예정·연혁 목록, 개정이유·개정문·조문·부칙 원문.
PDF에 명시된 법령과 핵심 법령의 시행령·시행규칙부터 추적하며, 첨부 문서의 전체 84건 등록부를 재현한 것은 아닙니다.</p>
<p>일정 통계는 API 목록의 대표 시행일 기준입니다. 부칙의 조문별 단계 시행일은 자동 추출하지 않으며 원문을 확인해야 합니다.</p>
<ul>{''.join('<li>' + h(item) + '</li>' for item in report.manual_checks)}</ul>''']

    def version_table(versions, future=False):
        if not versions:
            return ("<p>확인된 항목이 없습니다. 조회 실패가 있으면 변경 여부는 미확인입니다.</p>")
        rows = []
        for v in versions:
            day = (v.effective - report.today).days if v.effective else None
            timing = ("D-day" if day == 0 else f"D-{day}") if future else v.amendment
            urgency = ' class="urgent"' if future and day is not None and day <= 30 else ""
            rows.append(f'<tr><td><a href="{h(v.url)}">{h(v.name)}</a><br>{h(v.kind)} 제{h(v.number)}호</td>'
                        f'<td>{h(v.announced)}</td><td>{h(v.effective)}</td><td{urgency}>{h(timing)}</td></tr>')
        return '<table><thead><tr><th style="width:40%">법령 / 공식 원문</th><th>공포일</th><th>시행일</th><th>구분</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'

    parts.extend(["<h2>2. 기간 내 공포·시행 법령</h2>", version_table(report.weekly),
                  f"<h2>3. 시행 예정 법령</h2><p>{report.today} ~ {report.horizon} (보고일 당일 시행 포함)</p>",
                  version_table(report.upcoming, True),
                  "<h2>4. 개정 원문 및 핵심 법령 모니터링</h2>",
                  "<p>자동 법률 요약 대신 개정이유·개정문을 원문으로 제공합니다. 핵심 법령의 조문 대비는 이전 시행 버전과의 기계 비교이며, 법제처 공식 신·구조문 대비표가 아닙니다. 부칙의 조문별 시행일·적용례는 별도로 확인해야 합니다. 원문은 임의로 잘라내지 않습니다.</p>"])
    if not report.analyses:
        parts.append("<p>확인된 상세 분석 대상이 없습니다.</p>")
    for item in report.analyses:
        v = item.version
        parts.append(f'<h3><a href="{h(v.url)}">{h(v.name)}</a> · 시행 {h(v.effective)}</h3>'
                     f'<p>공포 {h(v.announced)} · {h(v.kind)} 제{h(v.number)}호 · {h(v.amendment)}</p>')
        if item.error:
            parts.append(f'<p class="notice">{h(item.error)}</p>')
        if item.detail:
            for label, value in [("개정이유·주요내용 (공식 원문)", item.detail.reason),
                                 ("개정문 (공식 원문)", item.detail.amendment_text),
                                 ("부칙·적용례·경과조치 (해당 버전에 포함된 원문)", item.detail.supplements)]:
                parts.append(f'<h4>{label}</h4><div class="excerpt">{h(value or "API 응답 미제공 — 공식 원문 직접 확인 필요")}</div>')
        if item.previous:
            parts.append(f'<p>비교 기준: <a href="{h(item.previous.url)}">시행 {h(item.previous.effective)} 버전</a> → 시행 {h(v.effective)} 버전. 변경 조문 {len(item.changes)}개.</p>')
        if item.changes:
            for change in item.changes:
                # 긴 조문을 표의 한 행에 넣으면 인쇄 시 페이지 밖으로 넘칠 수 있다.
                # 일반 블록으로 나눠 조문 전체가 페이지를 가로질러 이어지도록 한다.
                parts.append(f'<h4>{h(change["article"])} · 신·구조문 비교</h4>'
                             f'<p><strong>이전 시행 버전</strong></p><div class="excerpt">{h(change["before"])}</div>'
                             f'<p><strong>대상 버전</strong></p><div class="excerpt">{h(change["after"])}</div>')
    parts.append('<h2>5. 대상별 조회 상태</h2><table><thead><tr><th>법령</th><th>조회 결과</th></tr></thead><tbody>')
    parts.extend(f'<tr><td>{h(name)}</td><td>{h(status)}</td></tr>' for name, status in report.statuses.items())
    parts.append('</tbody></table><p class="source">정보 제공용 보고서입니다. 적용 판단은 공식 원문과 관계기관 안내를 확인하세요.</p></body></html>')
    return ''.join(parts)


def write_pdf(html: str, destination: Path) -> None:
    from weasyprint import HTML

    # All report content is inline; never fetch remote resources during PDF rendering.
    def deny_fetch(url, *args, **kwargs):
        raise ValueError("보고서 PDF 외부 리소스 요청 금지")

    HTML(string=html, url_fetcher=deny_fetch).write_pdf(destination)
