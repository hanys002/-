"""워크넷(고용24) 채용정보 오픈 API.

전 산업·전 지역을 포괄하므로 플랜트·계장·전자 분야까지 들어온다. 협회
게시판이 분야별로 쪼개져 있는 것과 달리 한 곳에서 세 자격을 모두 볼 수 있어,
WORK24_API_KEY를 등록하면 수집 범위가 가장 크게 넓어진다.

인증키 발급: https://www.data.go.kr/data/3038225/openapi.do (무료)
키가 없으면 조용히 건너뛰고 메일의 소스 상태에 그 사실을 남긴다.
"""
from __future__ import annotations

import os
from xml.etree import ElementTree

from .. import http
from ..filters import KeywordMatcher, parse_iso
from ..models import Posting


class SkipSource(Exception):
    """수집을 건너뛰어야 함을 알리는 신호."""


def _text(node, *names: str) -> str:
    """여러 후보 태그명 중 먼저 값이 있는 것을 돌려준다(스펙 변동 대비)."""
    for name in names:
        found = node.find(name)
        if found is not None and (found.text or "").strip():
            return found.text.strip()
    return ""


def collect(cfg: dict, settings: dict, matcher: KeywordMatcher) -> tuple[list[Posting], int]:
    key = os.environ.get("WORK24_API_KEY", "").strip()
    if not key:
        raise SkipSource(
            "WORK24_API_KEY 미설정 — 등록하면 플랜트·계장·전자 분야까지 수집됩니다"
        )

    out: list[Posting] = []
    scanned = 0
    seen: set[str] = set()
    limit = cfg.get("max_items", settings.get("max_items_per_source", 60))

    for query in cfg.get("queries", []):
        resp = http.get(
            cfg["api_url"],
            params={
                "authKey": key,
                "callTp": "L",          # 목록 조회
                "returnType": "XML",
                "startPage": 1,
                "display": limit,
                "keyword": query,
                "sortOrderBy": "DESC",
                "sortField": "DEADLINE",
            },
            timeout=settings.get("request_timeout", 25),
            delay=settings.get("request_delay", 1.2),
        )
        try:
            root = ElementTree.fromstring(resp.content)
        except ElementTree.ParseError as exc:
            raise RuntimeError(f"XML 파싱 실패 (인증키 확인 필요): {exc}") from exc

        for item in root.iter("wanted"):
            wanted_id = _text(item, "wantedAuthNo")
            if wanted_id and wanted_id in seen:
                continue
            seen.add(wanted_id)
            scanned += 1

            title = _text(item, "wantedTitle", "title")
            company = _text(item, "company", "coNm")
            matched = matcher.match(title, company, _text(item, "jobsCd", "jobsNm"))
            if not matched:
                continue

            out.append(Posting(
                source_id=cfg["id"], source_name=cfg["name"], org=cfg.get("org", "워크넷"),
                title=title, company=company,
                url=_text(item, "wantedInfoUrl", "wantedMobileInfoUrl") or "https://www.work24.go.kr",
                posted_on=parse_iso(_text(item, "regDt", "registDt")),
                deadline=_text(item, "closeDt"),
                location=_text(item, "basicAddr", "region"),
                matched=matched,
            ))

    return out[:limit], scanned
