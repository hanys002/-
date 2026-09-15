"""채용포털 검색 결과 수집기 (사람인·잡코리아·인크루트 공통).

포털마다 검색 파라미터와 상세공고 링크 패턴만 다르고 구조는 같다.
클래스 선택자는 개편에 취약하므로 **상세공고 링크 패턴**으로 직접 수집한다.

주의: 포털 검색을 필터로 신뢰하면 안 된다. 일치 건이 적으면 무관한 공고로
결과를 채우기 때문이다(실측: '정보통신기술사' 검색에 요양병원 영양실장이
섞여 나옴). 채택 여부는 반드시 matcher가 자격증명으로 판정한다.
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .. import http
from ..filters import KeywordMatcher, parse_date
from ..models import Posting

log = logging.getLogger(__name__)

MIN_TITLE_LEN = 6
# 카드 본문에는 직무·자격 태그가 함께 있어 제목만으로는 놓치는 건을 잡아준다.
# 다만 부모 요소가 클 수 있어 상한을 둔다.
ROW_TEXT_LIMIT = 400


def _detail_id(href: str, hints: list[str]) -> str | None:
    """상세공고 링크면 중복 판별용 식별자를, 아니면 None."""
    for hint in hints:
        if hint in href:
            tail = href.split(hint, 1)[1]
            return f"{hint}{tail.split('&')[0]}" if tail else href
    return None


def collect(cfg: dict, settings: dict, matcher: KeywordMatcher) -> tuple[list[Posting], int]:
    hints = cfg.get("detail_hints", [])
    base = cfg.get("base", "")
    limit = cfg.get("max_items", settings.get("max_items_per_source", 60))
    out: list[Posting] = []
    scanned = 0
    seen: set[str] = set()

    for query in cfg.get("queries", []):
        params = dict(cfg.get("extra_params") or {})
        params[cfg["query_param"]] = query
        resp = http.get(
            cfg["search_url"],
            params=params,
            timeout=settings.get("request_timeout", 25),
            delay=settings.get("request_delay", 1.2),
        )
        soup = BeautifulSoup(resp.text, "lxml")

        for anchor in soup.find_all("a", href=True):
            ident = _detail_id(anchor["href"], hints)
            if ident is None or ident in seen:
                continue
            title = (anchor.get("title") or anchor.get_text(" ", strip=True)).strip()
            if len(title) < MIN_TITLE_LEN:
                continue
            seen.add(ident)
            scanned += 1

            row = anchor.find_parent(["tr", "li", "article", "div"]) or anchor
            row_text = row.get_text(" ", strip=True)[:ROW_TEXT_LIMIT]
            matched = matcher.match(title, row_text)
            if not matched:
                continue

            corp = row.select_one(".corp_name a, .company_nm a, .name, .coName, .cpname")
            date_el = row.select_one(".job_date, .date, .support_info, .time")
            out.append(Posting(
                source_id=cfg["id"], source_name=cfg["name"], org=cfg.get("org", cfg["name"]),
                title=title, url=urljoin(base, anchor["href"]),
                company=corp.get_text(" ", strip=True) if corp else "",
                posted_on=parse_date(date_el.get_text(" ", strip=True)) if date_el else None,
                matched=matched,
            ))

    return out[:limit], scanned
