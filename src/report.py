"""HTML/텍스트 리포트 생성. Gmail 호환을 위해 전부 인라인 스타일 + 테이블 레이아웃."""
from __future__ import annotations

import html
from datetime import date, timedelta

from .models import Posting, SourceResult

FONT = "'Malgun Gothic','Apple SD Gothic Neo',AppleGothic,sans-serif"
INK = "#1a1a1a"
MUTED = "#6b7280"
LINE = "#e5e7eb"
ACCENT = "#1d4ed8"


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def sort_and_split(
    postings: list[Posting], recency_days: int, today: date | None = None
) -> tuple[list[Posting], list[Posting]]:
    """최신순 정렬 후 (최근분, 오래된분)으로 분할.

    날짜 미상은 최근분 뒤쪽에 둔다 — 협회 게시판은 날짜 파싱이 실패해도
    대개 목록 상단이 최신이라 버리는 것보다 노출하는 편이 낫다.
    """
    today = today or date.today()
    cutoff = today - timedelta(days=recency_days)

    def key(post: Posting):
        return (post.posted_on is not None, post.posted_on or date.min)

    ordered = sorted(postings, key=key, reverse=True)
    recent = [p for p in ordered if p.posted_on is None or p.posted_on >= cutoff]
    old = [p for p in ordered if p.posted_on is not None and p.posted_on < cutoff]
    return recent, old


def _row(post: Posting, dim: bool) -> str:
    color = MUTED if dim else INK
    link_color = MUTED if dim else ACCENT
    badge = (
        f'<span style="background:#dc2626;color:#fff;font-size:10px;font-weight:700;'
        f'padding:1px 5px;border-radius:3px;margin-right:6px;vertical-align:middle;">NEW</span>'
        if post.is_new and not dim
        else ""
    )
    meta = " · ".join(
        _esc(x) for x in [post.org, post.company, post.location] if x
    )
    tags = " ".join(
        f'<span style="background:#eef2ff;color:#3730a3;font-size:11px;'
        f'padding:1px 6px;border-radius:9px;margin-right:4px;">{_esc(t)}</span>'
        for t in post.matched[:3]
    )
    deadline = (
        f'<span style="color:#b45309;font-size:12px;">마감 {_esc(post.deadline)}</span>'
        if post.deadline
        else ""
    )
    return f"""
<tr>
  <td style="padding:11px 0;border-bottom:1px solid {LINE};font-family:{FONT};">
    <div style="font-size:12px;color:{MUTED};margin-bottom:3px;">{_esc(post.date_text)}</div>
    <div style="font-size:15px;line-height:1.45;margin-bottom:4px;">
      {badge}<a href="{_esc(post.url)}" style="color:{link_color};text-decoration:none;font-weight:600;">{_esc(post.title)}</a>
    </div>
    <div style="font-size:12px;color:{color};">{meta}</div>
    <div style="margin-top:5px;">{tags}{deadline}</div>
  </td>
</tr>"""


def _section(title: str, note: str, postings: list[Posting], dim: bool) -> str:
    if not postings:
        return ""
    rows = "".join(_row(p, dim) for p in postings)
    note_html = (
        f'<div style="font-size:12px;color:{MUTED};margin:2px 0 10px;">{_esc(note)}</div>'
        if note
        else ""
    )
    return f"""
<h2 style="font-family:{FONT};font-size:16px;color:{INK};margin:28px 0 2px;
           padding-bottom:6px;border-bottom:2px solid {INK};">{_esc(title)} <span style="color:{MUTED};font-weight:400;">({len(postings)}건)</span></h2>
{note_html}
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;">{rows}</table>"""



def _source_links(sources: list[dict]) -> str:
    """소스 바로가기 — 자동수집과 별개로 직접 확인할 수 있게 링크를 노출한다."""
    items = [
        (s, s.get("url") or s.get("search_url") or s.get("api_url", ""))
        for s in sources
        if s.get("enabled", True) and (s.get("url") or s.get("search_url"))
    ]
    if not items:
        return ""
    cells = "".join(
        f'<a href="{_esc(link)}" style="display:inline-block;font-family:{FONT};'
        f'font-size:12px;color:{ACCENT};text-decoration:none;border:1px solid {LINE};'
        f'border-radius:14px;padding:5px 11px;margin:0 5px 6px 0;">'
        f'{_esc(s.get("org") or s.get("name", ""))} &rsaquo;</a>'
        for s, link in items
    )
    return f"""
<h2 style="font-family:{FONT};font-size:14px;color:{MUTED};margin:30px 0 9px;
           padding-top:14px;border-top:1px solid {LINE};">소스 바로가기 — 직접 확인</h2>
<div>{cells}</div>"""


def _diagnostics(results: list[SourceResult]) -> str:
    rows = "".join(
        f'<tr><td style="padding:4px 10px 4px 0;font-family:{FONT};font-size:12px;'
        f'color:{INK};white-space:nowrap;">{_esc(r.source_name)}</td>'
        f'<td style="padding:4px 0;font-family:{FONT};font-size:12px;'
        f'color:{"#15803d" if r.ok else "#b91c1c"};">{_esc(r.status_text)}</td></tr>'
        for r in results
    )
    return f"""
<h2 style="font-family:{FONT};font-size:14px;color:{MUTED};margin:32px 0 8px;
           padding-top:14px;border-top:1px solid {LINE};">수집 소스 상태</h2>
<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">{rows}</table>"""


def build_html(
    recent: list[Posting],
    old: list[Posting],
    results: list[SourceResult],
    new_count: int,
    recency_days: int,
    today: date,
    sources: list[dict] | None = None,
) -> str:
    months = round(recency_days / 30.4)
    summary = (
        f"최근 {months}개월 이내 {len(recent)}건"
        + (f" (신규 {new_count}건)" if new_count else "")
        + (f" · 참고 {len(old)}건" if old else "")
    )
    empty = (
        f'<p style="font-family:{FONT};font-size:14px;color:{MUTED};padding:24px 0;">'
        f"오늘 조건에 맞는 신규 공고가 확인되지 않았습니다. 아래 소스 상태를 확인하세요.</p>"
        if not recent and not old
        else ""
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f6f7f9;">
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#f6f7f9;">
<tr><td align="center" style="padding:20px 12px;">
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:660px;background:#ffffff;border:1px solid {LINE};border-radius:8px;">
<tr><td style="padding:26px 26px 30px;">

  <div style="font-family:{FONT};font-size:12px;color:{MUTED};letter-spacing:.5px;">
    기술사 채용공고 데일리 브리핑
  </div>
  <h1 style="font-family:{FONT};font-size:21px;color:{INK};margin:6px 0 4px;">
    {today.strftime("%Y년 %m월 %d일")}
  </h1>
  <div style="font-family:{FONT};font-size:13px;color:{MUTED};">
    정보통신기술사 · 산업계측제어기술사 · 전자응용기술사
  </div>
  <div style="font-family:{FONT};font-size:13px;color:{ACCENT};margin-top:8px;font-weight:600;">
    {_esc(summary)}
  </div>

  {empty}
  {_section(f"최근 공고 (최근 {months}개월 이내)", "게시일 최신순입니다. 제목을 클릭하면 원문으로 이동합니다.", recent, dim=False)}
  {_section("참고 — 오래된 공고", f"게시일이 {months}개월을 넘은 건입니다. 마감되었을 수 있으니 참고용으로만 보세요.", old, dim=True)}
  {_source_links(sources or [])}
  {_diagnostics(results)}

  <p style="font-family:{FONT};font-size:11px;color:{MUTED};margin-top:26px;
            padding-top:12px;border-top:1px solid {LINE};line-height:1.6;">
    매일 09:00(KST) 자동 발송 · 수집 시각 {today.strftime("%Y-%m-%d")}<br>
    공고 내용·마감일은 반드시 원문 링크에서 최종 확인하시기 바랍니다.
  </p>

</td></tr></table></td></tr></table></body></html>"""


def build_text(recent: list[Posting], old: list[Posting], today: date) -> str:
    """HTML 미지원 클라이언트용 대체 본문."""
    lines = [f"기술사 채용공고 데일리 브리핑 — {today:%Y-%m-%d}", ""]
    for label, group in (("[최근 공고]", recent), ("[참고 — 오래된 공고]", old)):
        if not group:
            continue
        lines.append(label)
        for post in group:
            mark = "NEW " if post.is_new else ""
            lines.append(f"  {post.date_text} {mark}{post.title} ({post.org})")
            lines.append(f"    {post.url}")
        lines.append("")
    return "\n".join(lines)
