"""YAML 선택자 기반 범용 게시판 수집기.

협회 게시판은 개편이 잦아 선택자가 깨지기 쉽다. 설정 선택자가 0건을 반환하면
문서 전체의 <a>를 훑는 폴백으로 전환해, 사이트가 바뀌어도 수집이 멈추지 않게 한다.
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .. import http
from ..filters import KeywordMatcher, parse_date
from ..models import Posting

log = logging.getLogger(__name__)

# 링크 텍스트가 이보다 짧으면 제목이 아니라 페이징/아이콘으로 본다.
MIN_TITLE_LEN = 6
SKIP_LINK_PREFIXES = ("javascript:void", "#")


def _row_date(row, date_selector: str):
    """행 안에서 날짜를 찾는다. 지정 셀 → 행 전체 텍스트 순."""
    if date_selector:
        for cell in row.select(date_selector):
            found = parse_date(cell.get_text(" ", strip=True))
            if found:
                return found
    return parse_date(row.get_text(" ", strip=True))


def _make_posting(cfg, anchor, row, matcher: KeywordMatcher) -> Posting | None:
    title = anchor.get_text(" ", strip=True)
    if len(title) < MIN_TITLE_LEN:
        return None

    row_text = row.get_text(" ", strip=True) if row is not None else title
    matched = matcher.match(title, row_text)
    if not matched:
        return None

    href = anchor.get(cfg.get("link_attr", "href"), "") or ""
    if href.startswith(SKIP_LINK_PREFIXES):
        # onclick 기반 게시판: 상세 링크를 못 만들면 목록 URL로 보낸다.
        href = ""
    url = urljoin(cfg.get("base") or cfg["url"], href) if href else cfg["url"]

    return Posting(
        source_id=cfg["id"],
        source_name=cfg["name"],
        org=cfg.get("org", cfg["name"]),
        title=title,
        url=url,
        posted_on=_row_date(row, cfg.get("date_selector", "")) if row is not None else None,
        matched=matched,
    )


def collect(cfg: dict, settings: dict, matcher: KeywordMatcher) -> tuple[list[Posting], int]:
    resp = http.get(
        cfg["url"],
        timeout=settings.get("request_timeout", 25),
        delay=settings.get("request_delay", 1.2),
    )
    soup = BeautifulSoup(resp.text, "lxml")

    rows = soup.select(cfg.get("row_selector", "")) if cfg.get("row_selector") else []
    postings: list[Posting] = []
    scanned = 0

    for row in rows:
        for anchor in row.select(cfg.get("title_selector", "a")):
            scanned += 1
            item = _make_posting(cfg, anchor, row, matcher)
            if item:
                postings.append(item)

    if not postings:
        # 폴백: 선택자가 빗나갔거나 행을 거의 못 잡음 → 문서 전체 링크 스캔.
        # 행을 몇 개 잡고도 0건이면 선택자가 부분적으로만 맞은 것이므로 함께 폴백한다.
        log.warning("[%s] 채택 0건(행 %d개) — 전체 링크 폴백", cfg["id"], len(rows))
        seen_anchors = set()
        for anchor in soup.find_all("a"):
            ident = (anchor.get("href", ""), anchor.get_text(" ", strip=True))
            if ident in seen_anchors:
                continue
            seen_anchors.add(ident)
            scanned += 1
            row = anchor.find_parent(["tr", "li", "article", "div"]) or anchor
            item = _make_posting(cfg, anchor, row, matcher)
            if item:
                postings.append(item)

    limit = settings.get("max_items_per_source", 60)
    return postings[:limit], scanned
