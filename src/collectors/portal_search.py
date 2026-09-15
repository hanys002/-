"""채용포털 검색 결과 수집기 (사람인·잡코리아·인크루트 공통).

포털마다 검색 파라미터와 상세공고 링크 패턴만 다르고 구조는 같다.
클래스 선택자는 개편에 취약하므로 **상세공고 링크 패턴**으로 직접 수집한다.

채택은 2단계로 판정한다.

  1) 제목·카드 본문에 자격증명이 있으면 즉시 채택 (요청 1회)
  2) 없으면 상세 페이지를 열어 본문을 확인 (verify_detail)

2단계가 필요한 이유: 자격증명은 제목이 아니라 상세의 '우대사항'에 적힌다.
실측으로 사람인 계측제어 직종 337건을 훑었으나 제목에 '산업계측제어기술사'를
쓴 공고는 0건이었다. 목록만 봐서는 이 자격들을 영원히 잡을 수 없다.

포털 검색은 본문까지 색인하므로 검색 결과가 좋은 후보 집합이 된다. 다만
검색 자체를 신뢰하면 안 된다 — 일치 건이 적으면 무관한 공고로 결과를 채운다
(실측: '정보통신기술사' 검색에 요양병원 영양실장이 섞여 나옴). 상세 본문을
직접 확인하면 패딩 공고는 본문에도 자격증명이 없어 함께 걸러진다.
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
# 상세 본문에서 자격증명을 찾을 때 읽을 최대 길이. 공고 전문은 길지만
# 우대사항·자격요건은 대개 앞부분에 있고, 너무 길면 무관한 문구까지 걸린다.
DETAIL_TEXT_LIMIT = 6000


def _detail_id(href: str, hints: list[str]) -> str | None:
    """상세공고 링크면 중복 판별용 식별자를, 아니면 None."""
    for hint in hints:
        if hint in href:
            tail = href.split(hint, 1)[1]
            return f"{hint}{tail.split('&')[0]}" if tail else href
    return None


def _verify_detail(url: str, cfg: dict, settings: dict, matcher: KeywordMatcher):
    """상세 페이지 본문에 자격증명이 있는지 확인. 실패하면 조용히 None."""
    try:
        resp = http.get(
            url,
            timeout=settings.get("request_timeout", 25),
            delay=settings.get("request_delay", 1.2),
            retries=1,          # 후보가 많아 재시도까지 하면 실행시간이 길어진다
        )
    except Exception as exc:  # noqa: BLE001 - 한 건 실패로 소스 전체를 버리지 않는다
        log.debug("상세 확인 실패 %s (%s)", url, exc)
        return None
    text = BeautifulSoup(resp.text, "lxml").get_text(" ", strip=True)[:DETAIL_TEXT_LIMIT]
    return matcher.match(text) or None


def collect(cfg: dict, settings: dict, matcher: KeywordMatcher) -> tuple[list[Posting], int]:
    hints = cfg.get("detail_hints", [])
    base = cfg.get("base", "")
    limit = cfg.get("max_items", settings.get("max_items_per_source", 60))
    verify = cfg.get("verify_detail", False)
    budget = cfg.get("max_detail_fetch", 25)   # 상세 조회 요청 수 상한
    out: list[Posting] = []
    scanned = 0
    checked = 0
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
            url = urljoin(base, anchor["href"])

            matched = matcher.match(title, row_text)
            if not matched:
                # 제목·카드에 없으면 상세의 우대사항에 있는지 확인한다.
                if not verify or checked >= budget or matcher.is_excluded(title, row_text):
                    continue
                checked += 1
                matched = _verify_detail(url, cfg, settings, matcher)
                if not matched:
                    continue
                log.info("[%s] 상세 확인으로 채택: %s", cfg["id"], title[:60])

            corp = row.select_one(".corp_name a, .company_nm a, .name, .coName, .cpname")
            date_el = row.select_one(".job_date, .date, .support_info, .time")
            out.append(Posting(
                source_id=cfg["id"], source_name=cfg["name"], org=cfg.get("org", cfg["name"]),
                title=title, url=url,
                company=corp.get_text(" ", strip=True) if corp else "",
                posted_on=parse_date(date_el.get_text(" ", strip=True)) if date_el else None,
                matched=matched,
            ))

    if verify:
        log.info("[%s] 상세 확인 %d건 (상한 %d)", cfg["id"], checked, budget)
    return out[:limit], scanned
