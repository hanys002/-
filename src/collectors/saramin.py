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
from ..filters import KeywordMatcher, parse_date, parse_iso
from ..models import Posting

log = logging.getLogger(__name__)
BASE = "https://www.saramin.co.kr"
MIN_TITLE_LEN = 6


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
            matched = matcher.match(
                title, company,
                ((job.get("position") or {}).get("job-code") or {}).get("name", ""),
            )
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
    """공개 검색 결과 파싱.

    클래스 선택자는 개편에 취약해 상세공고 링크 패턴(rec_idx)으로 직접 수집한다.
    검색 자체가 키워드 필터이므로 여기서는 제외 대상만 걸러낸다.
    """
    out, scanned, seen = [], 0, set()
    limit = cfg.get("max_items", settings.get("max_items_per_source", 60))
    for query in cfg.get("queries", []):
        resp = http.get(
            cfg["search_url"],
            params={"searchword": query, "recruitSort": "reg_dt", "recruitPageCount": 40},
            timeout=settings.get("request_timeout", 25),
            delay=settings.get("request_delay", 1.2),
        )
        soup = BeautifulSoup(resp.text, "lxml")
        for anchor in soup.find_all("a", href=True):
            if "rec_idx=" not in anchor["href"]:
                continue
            title = (anchor.get("title") or anchor.get_text(" ", strip=True)).strip()
            if len(title) < MIN_TITLE_LEN:
                continue
            rec_id = anchor["href"].split("rec_idx=")[1].split("&")[0]
            if rec_id in seen:
                continue
            seen.add(rec_id)
            scanned += 1
            row = anchor.find_parent(["tr", "li", "article", "div"]) or anchor
            row_text = row.get_text(" ", strip=True)
            if matcher.is_excluded(title, row_text):
                continue
            corp = row.select_one(".corp_name a, .company_nm a, .str_tit")
            date_el = row.select_one(".job_date, .date, .support_info")
            out.append(Posting(
                source_id=cfg["id"], source_name=cfg["name"], org=cfg.get("org", "사람인"),
                title=title, url=urljoin(BASE, anchor["href"]),
                company=corp.get_text(" ", strip=True) if corp else "",
                posted_on=parse_date(date_el.get_text(" ", strip=True)) if date_el else None,
                matched=[query],
            ))
    return out[:limit], scanned


def collect(cfg: dict, settings: dict, matcher: KeywordMatcher) -> tuple[list[Posting], int]:
    key = os.environ.get("SARAMIN_API_KEY", "").strip()
    if key:
        return _from_api(cfg, settings, matcher, key)
    log.info("SARAMIN_API_KEY 없음 — 공개 검색 HTML 폴백 사용")
    return _from_html(cfg, settings, matcher)
