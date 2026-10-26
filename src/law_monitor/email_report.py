"""Gmail 등 웹메일에서 안정적으로 표시되는 별도 요약 본문."""
from __future__ import annotations

from .design import highlight
from .pipeline import Report
from .report import h, summary


FONT = "Arial, 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif"
BLUE = "#143765"
TEAL = "#177d8d"
RED = "#b52525"
TEXT = "#243342"
MUTED = "#5c6d7c"
BORDER = "#b8c9d5"
PALE = "#edf4f8"
MAX_EMAIL_BYTES = 80_000


class EmailRenderError(RuntimeError):
    pass


def metric(label: str, value: str) -> str:
    return (f'<td width="50%" valign="top" style="padding:6px;">'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            f'style="border-collapse:collapse;border:1px solid {BORDER};background:{PALE};">'
            f'<tr><td style="padding:12px;font-family:{FONT};text-align:center;">'
            f'<div style="font-size:20px;font-weight:bold;color:{BLUE};">{h(value)}</div>'
            f'<div style="font-size:12px;color:{MUTED};margin-top:3px;">{h(label)}</div>'
            f'</td></tr></table></td>')


def heading(number: str, title: str) -> str:
    return (f'<tr><td style="padding:22px 20px 8px 20px;font-family:{FONT};">'
            f'<div style="border-left:5px solid {TEAL};padding-left:10px;'
            f'font-size:20px;line-height:1.4;font-weight:bold;color:{BLUE};">'
            f'{h(number)}. {h(title)}</div></td></tr>')


def version_cards(report: Report, versions, analyses, *, future: bool) -> str:
    if not versions:
        return (f'<tr><td style="padding:8px 20px;font-family:{FONT};font-size:14px;color:{MUTED};">'
                '확인된 항목이 없습니다.</td></tr>')
    rows = []
    for version in versions:
        item = analyses.get(version.serial)
        days = (version.effective - report.today).days if version.effective else None
        timing = ('D-day' if days == 0 else f'D-{days}') if future else version.amendment
        urgent = future and days is not None and 0 <= days <= 30
        schedule_color = RED if urgent else TEXT
        issue = (f'<div style="margin-top:8px;color:{RED};font-weight:bold;">'
                 f'미확인: {h(item.error)}</div>') if item and item.error else ''
        core = version.name in report.core_laws
        rows.append(
            f'<tr><td style="padding:7px 20px;font-family:{FONT};">'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            f'style="border-collapse:separate;border-spacing:0;border:1px solid {BORDER};'
            f'border-left:5px solid {TEAL if core else BORDER};background:#ffffff;">'
            f'<tr><td style="padding:12px 14px 6px 14px;font-size:16px;font-weight:bold;">'
            f'<a href="{h(version.url)}" style="color:#15528a;text-decoration:underline;">{h(version.name)}</a>'
            f'</td></tr><tr><td style="padding:0 14px 8px 14px;font-size:12px;color:{MUTED};">'
            f'{h(version.kind)} 제{h(version.number)}호 · 공포 {h(version.announced)} · '
            f'<strong style="color:{schedule_color};">시행 {h(version.effective)} · {h(timing)}</strong>'
            f'</td></tr><tr><td style="padding:10px 14px 14px 14px;border-top:1px solid #dce5eb;'
            f'font-size:14px;line-height:1.65;color:{TEXT};">{highlight(summary(item))}{issue}</td></tr>'
            f'</table></td></tr>')
    return ''.join(rows)


def render_email(report: Report) -> str:
    """인쇄 CSS·내장 이미지 없이 인라인 스타일만 사용한다."""
    imminent = sum(0 <= (v.effective - report.today).days <= 30 for v in report.upcoming)
    analyses = {item.version.serial: item for item in report.analyses}
    badge = '[예시 데이터 · 실제 조회 아님] ' if report.demo else ''
    warning = ('일부 조회가 완료되지 않았습니다. 첨부 PDF의 조회 상태를 확인하세요.'
               if report.incomplete else f'설정된 {len(report.statuses)}개 법령의 목록 조회를 완료했습니다.')

    parts = [f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>{h(badge + report.title)}</title></head>
<body style="margin:0;padding:0;background:#f3f6f8;color:{TEXT};font-family:{FONT};">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;background:#f3f6f8;">
<tr><td align="center" style="padding:18px 8px;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;max-width:720px;background:#ffffff;border:1px solid #d7e0e6;">
<tr><td style="height:8px;background:{TEAL};font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td style="padding:22px 20px 18px 20px;background:{BLUE};font-family:{FONT};color:#ffffff;">
<div style="font-size:13px;line-height:1.4;opacity:0.9;">{h(report.organization)}</div>
<div style="font-size:24px;line-height:1.35;font-weight:bold;margin-top:5px;">{h(badge + report.title)}</div>
<div style="font-size:13px;line-height:1.5;margin-top:8px;">보고일 {h(report.today)} · 점검 기간 {h(report.start)} ~ {h(report.end)} · Vol. {h(report.volume)}</div>
</td></tr>
<tr><td style="padding:16px 14px 4px 14px;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
<tr>{metric('모니터링 대상', str(len(report.statuses)) + '개')}{metric('기간 내 공포·시행', str(len(report.weekly)) + '개')}</tr>
<tr>{metric('30일 내 시행', str(imminent) + '개')}{metric('6개월 내 시행', str(len(report.upcoming)) + '개')}</tr>
</table></td></tr>
<tr><td style="padding:12px 20px 4px 20px;font-family:{FONT};">
<div style="padding:12px 14px;border:1px solid #d5e1e8;background:#f7fafc;font-size:14px;line-height:1.6;color:{TEXT};">{h(warning)}</div>
<div style="padding:10px 2px 0 2px;font-size:12px;line-height:1.6;color:{MUTED};">메일 본문은 화면용 요약입니다. 표지·목차·상세 조회 상태가 포함된 정식 보고서는 첨부 PDF를 확인하세요. 법령명을 누르면 국가법령정보센터 원문으로 이동합니다.</div>
</td></tr>''']

    parts.append(heading('1', '금주 공포·시행 법령'))
    parts.append(version_cards(report, report.weekly, analyses, future=False))
    parts.append(heading('2', '시행 예정 법령'))
    parts.append(f'<tr><td style="padding:0 20px 5px 20px;font-family:{FONT};font-size:13px;color:{MUTED};">{h(report.today)} ~ {h(report.horizon)}</td></tr>')
    parts.append(version_cards(report, report.upcoming, analyses, future=True))
    parts.append(heading('3', '핵심 법령 확인 사항'))

    core_items = [item for item in report.analyses if item.version.name in report.core_laws]
    if not core_items:
        parts.append(f'<tr><td style="padding:8px 20px;font-family:{FONT};font-size:14px;color:{MUTED};">별도 핵심 법령 변경 요약이 없습니다.</td></tr>')
    for item in core_items:
        version = item.version
        note = item.comparison_note or summary(item, 360)
        parts.append(
            f'<tr><td style="padding:7px 20px;font-family:{FONT};">'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            f'style="border-collapse:collapse;border:1px solid {BORDER};background:{PALE};">'
            f'<tr><td style="padding:12px 14px;font-size:15px;line-height:1.6;color:{TEXT};">'
            f'<strong style="color:{BLUE};">{h(version.name)} · 시행 {h(version.effective)}</strong>'
            f'<div style="margin-top:7px;">{highlight(note)}</div>'
            f'<div style="margin-top:9px;"><a href="{h(version.url)}" style="color:#15528a;text-decoration:underline;">법령·개정이유·부칙 원문 확인</a></div>'
            f'</td></tr></table></td></tr>')

    parts.append(
        f'<tr><td style="padding:22px 20px 24px 20px;font-family:{FONT};">'
        f'<div style="border-top:1px solid #d6e0e6;padding-top:14px;font-size:12px;line-height:1.7;color:{MUTED};">'
        f'자료: 국가법령정보센터 공동활용 API · 정보 제공용 보고서<br>'
        f'적용 대상·경과조치·세부 내용은 첨부 PDF와 공식 원문을 확인하세요.</div></td></tr>'
        f'</table></td></tr></table></body></html>')
    return ''.join(parts)


def validate_email(html: str, report: Report) -> int:
    """Gmail이 제거하거나 잘라낼 가능성이 큰 요소를 발송 전에 거부한다."""
    from bs4 import BeautifulSoup

    size = len(html.encode('utf-8'))
    if size > MAX_EMAIL_BYTES:
        raise EmailRenderError(f'메일 HTML {size}바이트: Gmail 안전 한도 {MAX_EMAIL_BYTES}바이트 초과')
    soup = BeautifulSoup(html, 'html.parser')
    if soup.select('style, svg, img, script'):
        raise EmailRenderError('메일 본문에 Gmail 비호환 인쇄·이미지 요소가 포함되었습니다')
    lowered = html.lower()
    if '@page' in lowered or 'position:' in lowered or 'data:image' in lowered:
        raise EmailRenderError('메일 본문에 PDF 전용 위치·페이지 요소가 포함되었습니다')
    body = soup.get_text(' ', strip=True)
    required = (report.organization, report.title, '첨부 PDF')
    if any(value not in body for value in required):
        raise EmailRenderError('메일 본문의 기관명·제목·PDF 안내 검증에 실패했습니다')
    versions = [*report.weekly, *report.upcoming]
    if versions and not any(soup.find('a', href=v.url) for v in versions):
        raise EmailRenderError('메일 본문에 법령 원문 링크가 없습니다')
    return size
