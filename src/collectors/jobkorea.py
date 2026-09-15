"""잡코리아 공개 검색 결과 수집기(공식 오픈 API 미제공)."""
from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .. import http
from ..filters import KeywordMatcher, parse_date
from ..models import Posting

BASE = "https://www.jobkorea.co.kr"
# 공고 상세로 가는 링크 패턴 — 선택자가 깨졌을 때 폴백 판별 기준
DETAIL_HINTS = ("/Recruit/GI_Read", "/Recruit/Co_Read", "recruit/view")
MIN_TITLE_LEN = 6


def collect(cfg: dict, settings: dict, matcher: KeywordMatcher) -> tuple[list[Posting], int]:
    """검색 결과 파싱.

    잡코리아 검색은 자격요건 본문까지 훑으므로, 제목만 다시 키워드 검사하면
    정당한 공고를 대부분 버리게 된다(실측: 119건 스캔 / 0건 채택).
    검색 자체를 필터로 신뢰하고 여기서는 제외 대상만 걸러낸다.
    """
    out, scanned = [], 0
    for query in cfg.get("queries", []):
        resp = http.get(
            cfg["search_url"],
            params={"stext": query, "tabType": "recruit", "Page_No": 1},
            timeout=settings.get("request_timeout", 25),
            delay=settings.get("request_delay", 1.2),
        )
        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select("tr.devloopArea, .list-post, article.list-item, div[class*=list-item]")
        for card in cards:
            anchor = card.select_one("a.title, .post-list-info a, a[href*='/Recruit/GI_Read']")
            if not anchor:
                continue
            scanned += 1
            title = anchor.get("title") or anchor.get_text(" ", strip=True)
            corp = card.select_one(".name, .post-list-corp a, a.coName")
            company = corp.get_text(" ", strip=True) if corp else ""
            if matcher.is_excluded(title, company):
                continue
            date_el = card.select_one(".date, .post-list-info .date, .time")
            out.append(Posting(
                source_id=cfg["id"], source_name=cfg["name"], org=cfg.get("org", "잡코리아"),
                title=title, url=urljoin(BASE, anchor.get("href", "")), company=company,
                posted_on=parse_date(date_el.get_text(" ", strip=True)) if date_el else None,
                matched=[query],
            ))
        if not out:
            # 폴백: 카드 선택자가 빗나감 → 상세 링크 패턴으로 직접 수집
            found, extra = _fallback(soup, matcher, query)
            out.extend(found)
            scanned += extra

    limit = cfg.get("max_items", settings.get("max_items_per_source", 60))
    return out[:limit], scanned


def _fallback(soup, matcher: KeywordMatcher, query: str) -> tuple[list[Posting], int]:
    out, scanned, seen = [], 0, set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not any(hint in href for hint in DETAIL_HINTS):
            continue
        title = anchor.get("title") or anchor.get_text(" ", strip=True)
        if len(title) < MIN_TITLE_LEN or (href, title) in seen:
            continue
        seen.add((href, title))
        scanned += 1
        row = anchor.find_parent(["tr", "li", "article", "div"]) or anchor
        if matcher.is_excluded(title, row.get_text(" ", strip=True)):
            continue
        out.append(Posting(
            source_id="jobkorea", source_name="잡코리아", org="잡코리아",
            title=title, url=urljoin(BASE, href),
            posted_on=parse_date(row.get_text(" ", strip=True)),
            matched=[query],
        ))
    return out, scanned
