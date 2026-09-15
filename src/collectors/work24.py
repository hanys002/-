"""고용24(워크넷) 채용정보 - 공공데이터포털 오픈 API.

WORK24_API_KEY(공공데이터포털 일반 인증키)가 설정된 경우에만 동작하며,
키가 없으면 조용히 건너뛴다(리포트에 '키 미설정'으로 표기).
"""
from __future__ import annotations

import os

from .. import http
from ..filters import KeywordMatcher, parse_iso
from ..models import Posting


class SkipSource(Exception):
    """수집을 건너뛰어야 함을 알리는 신호."""


def collect(cfg: dict, settings: dict, matcher: KeywordMatcher) -> tuple[list[Posting], int]:
    key = os.environ.get("WORK24_API_KEY", "").strip()
    if not key:
        raise SkipSource("WORK24_API_KEY 미설정 (공공데이터포털 인증키 필요)")

    out, scanned = [], 0
    for query in cfg.get("queries", []):
        resp = http.get(
            cfg["api_url"],
            params={
                "serviceKey": key,
                "numOfRows": settings.get("max_items_per_source", 60),
                "pageNo": 1,
                "resultType": "json",
                "acbgCondNmLst": "",
                "recrutPbancTtl": query,
            },
            timeout=settings.get("request_timeout", 25),
            delay=settings.get("request_delay", 1.2),
        )
        items = (resp.json().get("result") or []) if isinstance(resp.json(), dict) else []
        for item in items:
            scanned += 1
            title = item.get("recrutPbancTtl", "")
            company = item.get("instNm", "")
            matched = matcher.match(title, company, item.get("ncsCdNmLst", ""))
            if not matched:
                continue
            out.append(Posting(
                source_id=cfg["id"], source_name=cfg["name"], org=cfg.get("org", "고용24"),
                title=title, company=company,
                url=item.get("srcUrl") or "https://www.work24.go.kr",
                posted_on=parse_iso(item.get("pbancBgngYmd", "")),
                deadline=str(parse_iso(item.get("pbancEndYmd", "")) or ""),
                location=item.get("workRgnNmLst", ""),
                matched=matched,
            ))
    return out, scanned
