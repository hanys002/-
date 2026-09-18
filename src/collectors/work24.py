"""워크넷(고용24) 채용정보 오픈 API.

전 산업·전 지역을 포괄하므로 플랜트·계장·전자 분야까지 들어온다. 협회
게시판이 분야별로 쪼개져 있는 것과 달리 한 곳에서 세 자격을 모두 볼 수 있어,
WORK24_API_KEY를 등록하면 수집 범위가 가장 크게 넓어진다.

인증키 발급: https://www.data.go.kr/data/3038225/openapi.do (무료)
키가 없으면 조용히 건너뛰고 메일의 소스 상태에 그 사실을 남긴다.
"""
from __future__ import annotations

import logging
import os
from xml.etree import ElementTree

from .. import http
from ..filters import KeywordMatcher, parse_iso
from ..models import Posting

log = logging.getLogger(__name__)

# 응답이 XML이 아닐 때 원인을 가르는 표식. 인증키가 틀렸는지, 승인 대기인지,
# 그냥 결과가 없는지를 첫 실행에서 바로 구분하기 위한 것이다.
AUTH_ERROR_MARKERS = [
    "인증키", "authKey", "auth key", "유효하지", "등록되지", "승인",
    "권한", "SERVICE_KEY", "SERVICE ERROR", "인증", "미승인", "정지",
]


class SkipSource(Exception):
    """수집을 건너뛰어야 함을 알리는 신호."""


def _redact(text: str, key: str) -> str:
    """로그에 인증키가 새지 않게 가린다.

    GitHub Actions가 등록된 시크릿을 자동으로 가리지만, 오류 응답이 키를
    변형해 되돌려주는 경우까지는 보장되지 않는다. 직접 한 번 더 지운다.
    """
    if key and len(key) >= 8:
        text = text.replace(key, "***")
    return text


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
    first_call = True          # 첫 응답만 상세히 남긴다(로그 과다 방지)
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
        body = resp.content or b""
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError as exc:
            # 무엇이 잘못됐는지 첫 실행에서 판정할 수 있게 응답 자체를 남긴다.
            snippet = _redact(
                body.decode("utf-8", "replace")[:300].replace("\n", " ").strip(), key
            )
            hint = ("인증키가 유효하지 않거나 아직 승인되지 않았습니다"
                    if any(m in snippet for m in AUTH_ERROR_MARKERS)
                    else "응답이 XML이 아닙니다")
            raise RuntimeError(
                f"{hint} (HTTP {resp.status_code}, {len(body)}B) "
                f"응답: {snippet or '(빈 응답)'} | 파싱오류: {exc}"
            ) from exc

        # XML이긴 한데 에러 문서일 수 있다. 목록 태그가 하나도 없으면 남겨 둔다.
        if first_call:
            first_call = False
            wanted_count = len(list(root.iter("wanted")))
            log.info("[work24] 응답 OK (HTTP %s, %dB, 루트=<%s>, wanted=%d개)",
                     resp.status_code, len(body), root.tag, wanted_count)
            if wanted_count == 0:
                detail = _redact(" ".join(root.itertext())[:200].strip(), key)
                log.warning("[work24] 목록이 비어 있습니다 — 응답 본문: %s",
                            detail or "(텍스트 없음)")

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
