"""소스 페이지 진단.

개발 환경에서는 국내 사이트에 접속할 수 없어 선택자를 실물로 검증하지 못한다.
추측으로 고치면 오탐·누락이 반복되므로, 러너가 실제로 받아오는 HTML을 그대로
들여다보는 도구를 둔다. `python -m src.main --diagnose <source_id>`로 실행하고
Actions 로그에서 결과를 읽는다.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from . import http

log = logging.getLogger("diagnose")

# 로그인이 필요한 페이지인지 판별하는 흔적
LOGIN_MARKERS = ["로그인", "login", "아이디", "비밀번호", "회원만", "권한이 없", "member"]
LOGOUT_MARKERS = ["로그아웃", "logout"]


def _summarize_links(soup, limit: int = 25) -> list[tuple[str, str]]:
    out = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if len(text) >= 4:
            out.append((text[:70], a["href"][:90]))
        if len(out) >= limit:
            break
    return out


def run(cfg: dict, settings: dict, qualifications: list[str], session=None) -> None:
    url = cfg.get("url") or cfg.get("search_url") or ""
    log.info("=" * 70)
    log.info("진단: [%s] %s", cfg["id"], cfg.get("name", ""))
    log.info("URL: %s", url)

    try:
        resp = http.get(url, timeout=settings.get("request_timeout", 25),
                        delay=settings.get("request_delay", 1.2), session=session)
    except Exception as exc:  # noqa: BLE001
        log.error("요청 실패: %s: %s", type(exc).__name__, exc)
        return

    body = resp.text
    soup = BeautifulSoup(body, "lxml")
    text = soup.get_text(" ", strip=True)

    log.info("HTTP %s | %s bytes | encoding=%s", resp.status_code, len(body), resp.encoding)
    log.info("<title>: %s", (soup.title.get_text(strip=True) if soup.title else "(없음)")[:80])

    # 로그인 상태
    has_login = [m for m in LOGIN_MARKERS if m in text]
    has_logout = [m for m in LOGOUT_MARKERS if m in text]
    log.info("로그인 흔적: %s / 로그아웃 흔적: %s",
             has_login[:4] or "없음", has_logout[:2] or "없음")
    forms = soup.find_all("form")
    for form in forms[:3]:
        names = [i.get("name") for i in form.find_all("input") if i.get("name")]
        if any(n and re.search(r"id|user|pw|pass", n, re.I) for n in names):
            log.info("로그인 폼 후보: action=%s method=%s inputs=%s",
                     form.get("action"), form.get("method"), names[:8])

    # 구조
    log.info("구조: table=%d, tr=%d, li=%d, a=%d, form=%d",
             len(soup.find_all("table")), len(soup.find_all("tr")),
             len(soup.find_all("li")), len(soup.find_all("a")), len(forms))
    if cfg.get("row_selector"):
        log.info("설정 row_selector '%s' → %d개 적중",
                 cfg["row_selector"], len(soup.select(cfg["row_selector"])))

    # 핵심: 자격증명이 받아온 HTML 안에 실제로 있는가
    for q in qualifications:
        hits = [m.start() for m in re.finditer(re.escape(q), text)]
        if hits:
            around = text[max(0, hits[0] - 60):hits[0] + 80].replace("\n", " ")
            log.info("'%s' %d회 발견 → …%s…", q, len(hits), around)
        else:
            # '정보통신 기술사'처럼 공백을 넣어 쓴 표기도 확인한다.
            loose = r"\s*".join(re.escape(ch) for ch in q)
            found = re.findall(loose, text)
            log.info("'%s' 0회 (공백 허용 매칭 %d회%s)", q, len(found),
                     f" 예: {found[0]!r}" if found else "")

    log.info("링크 상위 %d개:", 25)
    for t, h in _summarize_links(soup):
        log.info("    %-70s %s", t, h)
    log.info("=" * 70)
