"""표 형식 구인 게시판 수집기 (한국기술사회 등).

일반 게시판과 달리 '제목'이 없고 표의 컬럼에 정보가 나뉘어 있다.

    번호 | 구분 | 모집 자격종목   | 회사          | 지역 | 마감일     | 등록일
    5410 | 경력 | 정보통신기술사  | (주)케이씨에이 | 서울 | 2026-10-30 | 2026-09-15

앵커 텍스트를 제목으로 읽는 generic_board로는 이런 게시판을 통째로 놓친다
(실측: 한국기술사회 HTML에 '정보통신기술사'가 있는데도 0건 수집).
여기서는 행의 셀을 직접 읽어 판정한다.

이 게시판은 전체가 구인글이므로 채용 신호어는 요구하지 않는다.
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

SKIP_LINK_PREFIXES = ("javascript:", "#", "mailto:", "tel:")
# 회사명으로 보이는 셀 판별
COMPANY_HINT = re.compile(r"\(주\)|㈜|주식회사|기술단|엔지니어링|건축사|산업|기술원|연구")
DATE_HINT = re.compile(r"20\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2}|상시|수시")


def _cells(row) -> list[str]:
    return [td.get_text(" ", strip=True) for td in row.find_all(["td", "th"])]


def _pick(cells: list[str], index: int | None, pattern: re.Pattern | None) -> str:
    """지정 열 우선, 없으면 패턴으로 찾는다(열 순서가 바뀌어도 버티도록)."""
    if index is not None and 0 <= index < len(cells) and cells[index]:
        return cells[index]
    if pattern is not None:
        for cell in cells:
            if pattern.search(cell):
                return cell
    return ""


def collect(cfg: dict, settings: dict, matcher: KeywordMatcher) -> tuple[list[Posting], int]:
    session = http.login(cfg.get("login"), cfg["id"])
    soup = BeautifulSoup(fetch.page_html(cfg, settings, session), "lxml")
    cols = cfg.get("columns") or {}
    limit = cfg.get("max_items", settings.get("max_items_per_source", 100))

    out: list[Posting] = []
    scanned = 0

    for row in soup.select(cfg.get("row_selector", "table tbody tr")):
        cells = _cells(row)
        if len(cells) < cfg.get("min_cells", 4):
            continue                      # 헤더·빈 행
        scanned += 1

        row_text = " ".join(cells)
        if matcher.is_excluded(row_text):
            continue
        matched = matcher.match(row_text)
        if not matched:
            continue

        # 제목은 자격종목 셀. 없으면 매칭된 자격증명으로 대신한다.
        title = _pick(cells, cols.get("qualification"), None) or " · ".join(matched)
        company = _pick(cells, cols.get("company"), COMPANY_HINT)
        deadline = _pick(cells, cols.get("deadline"), DATE_HINT)
        posted = parse_date(_pick(cells, cols.get("posted"), DATE_HINT))
        location = _pick(cells, cols.get("location"), None)

        anchor = row.find("a", href=True)
        href = anchor["href"] if anchor else ""
        if href.startswith(SKIP_LINK_PREFIXES):
            href = ""
        url = urljoin(cfg.get("base") or cfg["url"], href) if href else cfg["url"]

        out.append(Posting(
            source_id=cfg["id"], source_name=cfg["name"], org=cfg.get("org", cfg["name"]),
            title=title, url=url, company=company, location=location,
            deadline=deadline if deadline and deadline != str(posted) else "",
            posted_on=posted, matched=matched, link_is_list=not href,
        ))

    return out[:limit], scanned
