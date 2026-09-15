"""사람인 수집기.

SARAMIN_API_KEY(사람인 오픈 API 인증키)가 있으면 공식 API를 쓰고,
없으면 공개 검색 결과 HTML을 파싱하는 폴백으로 동작한다.
"""
from __future__ import annotations

import logging
import os
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .. import http
from ..filters import KeywordMatcher, parse_iso
from ..models import Posting

log = logging.getLogger(__name__)
BASE = "https://www.saramin.co.kr"


def _from_api(cfg, settings, matcher, key) -> tuple[list[Posting], int]:
    out, scanned = [], 0
    for query in cfg.get("queries", []):
        resp = http.get(
            cfg["api_url"],
            params={
                "access-key": key,
                "keywords": query,
                "count": settings.get("max_items_per_source", 60),
                "sort": "pd",  # 게시일 최신순
                "fields": "posting-date,expiration-date,count",
            },
            timeout=settings.get("request_timeout", 25),
            delay=settings.get("request_delay", 1.2),
        )
        jobs = (resp.json().get("jobs") or {}).get("job") or []
        for job in jobs:
            scanned += 1
            title = (job.get("position") or {}).get("title", "")
            company = ((job.get("company") or {}).get("detail") or {}).get("name", "")
            matched = matcher.match(title, company,
                                    ((job.get("position") or {}).get("job-code") or {}).get("name", ""))
            if not matched:
                continue
            out.append(Posting(
                source_id=cfg["id"], source_name=cfg["name"], org=cfg.get("org", "사람인"),
                title=title, url=job.get("url", BASE), company=company,
                location=((job.get("position") or {}).get("location") or {}).get("name", ""),
                posted_on=parse_iso(job.get("posting-timestamp") or job.get("posting-date", "")),
                deadline=parse_iso(job.get("expiration-date", "")) and
                         str(parse_iso(job.get("expiration-date", ""))) or "",
                matched=matched,
            ))
    return out, scanned


def _from_html(cfg, settings, matcher) -> tuple[list[Posting], int]:
    out, scanned = [], 0
    for query in cfg.get("queries", []):
        resp = http.get(
            cfg["search_url"],
            params={"searchword": query, "recruitSort": "reg_dt", "recruitPageCount": 40},
            timeout=settings.get("request_timeout", 25),
            delay=settings.get("request_delay", 1.2),
        )
        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select(".item_recruit, .list_item, div[class*=item]")
        for card in cards:
            anchor = card.select_one("h2 a, .job_tit a, a[title]")
            if not anchor:
                continue
            scanned += 1
            title = anchor.get("title") or anchor.get_text(" ", strip=True)
            corp = card.select_one(".corp_name a, .company_nm a")
            company = corp.get_text(" ", strip=True) if corp else ""
            matched = matcher.match(title, company, query)
            if not matched:
                continue
            date_el = card.select_one(".job_date, .date, .support_info")
            out.append(Posting(
                source_id=cfg["id"], source_name=cfg["name"], org=cfg.get("org", "사람인"),
                title=title, url=urljoin(BASE, anchor.get("href", "")), company=company,
                posted_on=parse_iso(date_el.get_text(" ", strip=True)) if date_el else None,
                matched=matched,
            ))
    return out, scanned


def collect(cfg: dict, settings: dict, matcher: KeywordMatcher) -> tuple[list[Posting], int]:
    key = os.environ.get("SARAMIN_API_KEY", "").strip()
    if key:
        return _from_api(cfg, settings, matcher, key)
    log.info("SARAMIN_API_KEY 없음 — 공개 검색 HTML 폴백 사용")
    return _from_html(cfg, settings, matcher)
