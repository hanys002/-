"""잡코리아 공개 검색 결과 수집기(공식 오픈 API 미제공)."""
from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .. import http
from ..filters import KeywordMatcher, parse_date
from ..models import Posting

BASE = "https://www.jobkorea.co.kr"


def collect(cfg: dict, settings: dict, matcher: KeywordMatcher) -> tuple[list[Posting], int]:
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
            matched = matcher.match(title, company, query)
            if not matched:
                continue
            date_el = card.select_one(".date, .post-list-info .date, .time")
            out.append(Posting(
                source_id=cfg["id"], source_name=cfg["name"], org=cfg.get("org", "잡코리아"),
                title=title, url=urljoin(BASE, anchor.get("href", "")), company=company,
                posted_on=parse_date(date_el.get_text(" ", strip=True)) if date_el else None,
                matched=matched,
            ))
    limit = settings.get("max_items_per_source", 60)
    return out[:limit], scanned
