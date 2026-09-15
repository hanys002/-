"""YAML 선택자 기반 범용 게시판 수집기.

협회 게시판은 개편이 잦아 선택자가 깨지기 쉽다. 설정 선택자가 0건을 반환하면
문서 전체의 <a>를 훑는 폴백으로 전환해, 사이트가 바뀌어도 수집이 멈추지 않게 한다.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .. import fetch, http
from ..filters import KeywordMatcher, parse_date
from ..models import Posting

log = logging.getLogger(__name__)

# 링크 텍스트가 이보다 짧으면 제목이 아니라 페이징/아이콘으로 본다.
MIN_TITLE_LEN = 6
# javascript: 스킴은 전부 사용 불가. 감리협회는 비회원 상세 열람을 막아
# href가 javascript:alert("게시판 읽기 권한이 없습니다.")로 나온다.
SKIP_LINK_PREFIXES = ("javascript:", "#", "mailto:", "tel:")

# 게시글 링크는 글 번호를 갖는다(?id=123, /view/456 등). 반면 사이트 메뉴는
# '/kpis' 처럼 번호가 없다. 폴백으로 문서 전체를 훑을 때 메뉴가 공고로 잡히는
# 것을 막는다(실측: 한국기술사회 '기술사종합정보시스템' 메뉴가 채택됨).
POST_ID_HINT = re.compile(r"\d")
# 워드프레스식 게시글은 번호 대신 긴 슬러그를 쓴다(한글은 URL 인코딩돼 더 길어진다).
# 메뉴 링크('/kpis', '/intro/greeting')는 짧아 이 길이를 넘지 않는다.
SLUG_MIN_LEN = 25
ROW_TEXT_LIMIT = 300


def _looks_like_post(href: str) -> bool:
    """게시글 링크로 보이면 True. 사이트 메뉴를 걸러내기 위한 판별."""
    return bool(POST_ID_HINT.search(href)) or len(href) > SLUG_MIN_LEN


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

    # 게시판 목록은 카테고리 메뉴·뉴스도 함께 걸리므로 채용 신호어를 요구한다.
    if not matcher.has_hiring_signal(title):
        return None

    # 폴백 경로에서는 부모가 메뉴 블록 전체일 수 있어 길이를 제한한다.
    # (제한하지 않으면 메뉴 전체 텍스트가 분야 키워드를 만족시켜 버린다)
    row_text = row.get_text(" ", strip=True)[:ROW_TEXT_LIMIT] if row is not None else title
    matched = matcher.match(title, row_text)
    if not matched:
        return None

    href = anchor.get(cfg.get("link_attr", "href"), "") or ""
    if href.startswith(SKIP_LINK_PREFIXES):
        # onclick 기반이거나 비회원 열람이 막힌 게시판. 상세 링크를 만들 수 없다.
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
        link_is_list=not href,     # 목록 URL로 대체됐음을 메일에 표시
    )


def collect(cfg: dict, settings: dict, matcher: KeywordMatcher) -> tuple[list[Posting], int]:
    session = http.login(cfg.get("login"), cfg["id"])
    soup = BeautifulSoup(fetch.page_html(cfg, settings, session), "lxml")

    rows = soup.select(cfg.get("row_selector", "")) if cfg.get("row_selector") else []
    postings: list[Posting] = []
    scanned = 0

    for row in rows:
        anchors = row.select(cfg.get("title_selector", "a"))
        # 목록이 표가 아니라 링크 묶음인 게시판이 있다(정보통신기술사회 실측:
        # table=1이 검색 폼이고 글은 bbsView.php 링크로만 늘어서 있다).
        # 그 경우 row_selector가 <a>를 직접 가리키는데, select()는 자손만 보므로
        # 행 자신을 놓친다.
        if not anchors and row.name == "a":
            anchors = [row]

        for anchor in anchors:
            scanned += 1
            # 날짜·부가정보는 링크 바깥 형제 칸에 있다. 행이 곧 링크면
            # 한 단계 올려 잡아야 날짜가 보인다.
            ctx = row
            if ctx is anchor:
                ctx = anchor.find_parent(["tr", "li", "article", "div"]) or anchor
            item = _make_posting(cfg, anchor, ctx, matcher)
            if item:
                postings.append(item)

    if not postings:
        # 폴백: 선택자가 빗나갔거나 행을 거의 못 잡음 → 문서 전체 링크 스캔.
        # 행을 몇 개 잡고도 0건이면 선택자가 부분적으로만 맞은 것이므로 함께 폴백한다.
        log.warning("[%s] 채택 0건(행 %d개) — 전체 링크 폴백", cfg["id"], len(rows))
        seen_anchors = set()
        for anchor in soup.find_all("a"):
            href = anchor.get("href", "")
            if not _looks_like_post(href):
                continue          # 글 번호도 슬러그도 없으면 메뉴/네비게이션
            ident = (href, anchor.get_text(" ", strip=True))
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
