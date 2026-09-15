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

from . import fetch

log = logging.getLogger("diagnose")

# 로그인이 필요한 페이지인지 판별하는 흔적
LOGIN_MARKERS = ["로그인", "login", "아이디", "비밀번호", "회원만", "권한이 없", "member"]
LOGOUT_MARKERS = ["로그아웃", "logout"]


def _summarize_links(soup, limit: int = 10) -> list[tuple[str, str]]:
    out = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if len(text) >= 4:
            out.append((text[:70], a["href"][:90]))
        if len(out) >= limit:
            break
    return out


# 목록이 표가 아니라 ul/li·div로 그려진 사이트가 많다. 행 선택자를 추측하지 않고,
# '같은 태그의 형제가 여러 개 붙어 있는 부모'를 찾아 실제 후보를 뽑는다.
def _list_candidates(soup, limit: int = 6) -> list[tuple[str, int, list[str]]]:
    seen: dict[int, tuple[str, int, list[str]]] = {}
    for parent in soup.find_all(["ul", "ol", "tbody", "table", "div", "section"]):
        kids = [c for c in parent.find_all(recursive=False) if c.name in ("li", "tr", "div", "a", "dl")]
        if len(kids) < 4:
            continue
        tag = max({k.name for k in kids}, key=lambda n: sum(1 for k in kids if k.name == n))
        same = [k for k in kids if k.name == tag]
        if len(same) < 4:
            continue
        # 링크를 품은 행만 게시판 목록으로 본다(내비게이션 메뉴 배제는 아래 텍스트로 판단).
        linked = sum(1 for k in same if k.find("a", href=True))
        if linked < 3:
            continue
        samples = []
        for k in same[:4]:
            txt = k.get_text(" ", strip=True)
            a = k.find("a", href=True)
            href = a["href"][:70] if a else "-"
            samples.append(f"{txt[:80]}  ←  {href}")
        seen[id(parent)] = (_selector_of(parent, tag), len(same), samples)
    out = sorted(seen.values(), key=lambda x: -x[1])
    return out[:limit]


def _selector_of(el, child_tag: str) -> str:
    """부모를 그대로 설정에 붙여넣을 수 있는 CSS 선택자로 적는다."""
    bits = []
    node = el
    for _ in range(3):
        if node is None or node.name in (None, "[document]", "html", "body"):
            break
        part = node.name
        if node.get("id"):
            part = f"{node.name}#{node['id']}"
            bits.append(part)
            break
        classes = [c for c in (node.get("class") or []) if c]
        if classes:
            part = f"{node.name}.{'.'.join(classes[:2])}"
        bits.append(part)
        node = node.parent
    return " ".join(reversed(bits)) + f" > {child_tag}"


# javascript:menu(...) 내비게이션을 걷어내고 '실제 주소가 있는 링크'만 남긴다.
def _content_links(soup, limit: int = 25) -> list[tuple[str, str]]:
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith(("javascript:", "#", "mailto:", "tel:")):
            continue
        text = a.get_text(" ", strip=True)
        if len(text) < 4:
            continue
        out.append((text[:70], href[:100]))
        if len(out) >= limit:
            break
    return out


def run(cfg: dict, settings: dict, qualifications: list[str], session=None) -> None:
    url = cfg.get("url") or cfg.get("search_url") or ""
    log.info("=" * 70)
    log.info("진단: [%s] %s", cfg["id"], cfg.get("name", ""))
    log.info("URL: %s", url)

    if cfg.get("render"):
        log.info("모드: 브라우저 렌더링 (eval_js=%s, wait_for=%s)",
                 cfg.get("eval_js"), cfg.get("wait_for"))
    try:
        body = fetch.page_html(cfg, settings, session)
    except Exception as exc:  # noqa: BLE001
        log.error("요청 실패: %s: %s", type(exc).__name__, exc)
        return
    soup = BeautifulSoup(body, "lxml")
    text = soup.get_text(" ", strip=True)

    log.info("본문 %s bytes | %s", len(body),
             "브라우저 렌더링" if cfg.get("render") else "정적 요청")
    if len(body) < 2000:
        # 응답이 작으면 JS 리다이렉트·프레임·차단 안내인 경우가 많다.
        # 구조 분석이 무의미하므로 원문을 그대로 보여준다.
        log.info("본문이 작아 원문을 그대로 출력합니다:")
        for line in body.strip().splitlines()[:20]:
            log.info("    | %s", line[:200])
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
    found_summary: list[str] = []
    for q in qualifications:
        hits = [m.start() for m in re.finditer(re.escape(q), text)]
        if hits:
            around = text[max(0, hits[0] - 60):hits[0] + 80].replace("\n", " ")
            log.info("'%s' %d회 발견 → …%s…", q, len(hits), around)
            found_summary.append(f"{q}×{len(hits)}")
        else:
            # '정보통신 기술사'처럼 공백을 넣어 쓴 표기도 확인한다.
            loose = r"\s*".join(re.escape(ch) for ch in q)
            found = re.findall(loose, text)
            log.info("'%s' 0회 (공백 허용 매칭 %d회%s)", q, len(found),
                     f" 예: {found[0]!r}" if found else "")

    # 여러 후보를 한 번에 던질 때 이 한 줄만 훑으면 된다.
    log.info("판정 ▶ [%s] %s | %sB | rows=%s | 자격: %s | %s",
             cfg["id"], "렌더" if cfg.get("render") else "정적", len(body),
             len(soup.select(cfg["row_selector"])) if cfg.get("row_selector") else "-",
             ", ".join(found_summary) or "없음", url)

    # JS로 이동하는 사이트는 링크에 주소가 없다(javascript:menu(...)).
    # 다음 단서는 스크립트·iframe·폼에 있다.
    scripts = [t.get("src") for t in soup.find_all("script") if t.get("src")]
    frames = [t.get("src") for t in soup.find_all(["iframe", "frame"]) if t.get("src")]
    actions = [t.get("action") for t in soup.find_all("form") if t.get("action")]
    if scripts:
        log.info("스크립트 %d개: %s", len(scripts), ", ".join(scripts[:8]))
    if frames:
        log.info("프레임: %s", ", ".join(frames[:5]))
    if actions:
        log.info("폼 action: %s", ", ".join(actions[:5]))

    log.info("링크 상위 %d개:", 10)
    for t, h in _summarize_links(soup):
        log.info("    %-70s %s", t, h)

    # 행 선택자를 실물에서 고르기 위한 후보 목록
    cands = _list_candidates(soup)
    if cands:
        log.info("목록 후보 %d개 (행 많은 순):", len(cands))
        for sel, n, samples in cands:
            log.info("  · row_selector: %s   (%d행)", sel, n)
            for smp in samples:
                log.info("        %s", smp)
    else:
        log.info("목록 후보 없음 — 반복 구조를 찾지 못했다")

    links = _content_links(soup)
    log.info("주소 있는 링크 %d개(내비 제외):", len(links))
    for t, h in links:
        log.info("    %-70s %s", t, h)
    log.info("=" * 70)
