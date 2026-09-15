"""소스 HTML 취득. 설정의 render 여부에 따라 정적/브라우저를 고른다."""
from __future__ import annotations

import logging

from . import browser, http

log = logging.getLogger(__name__)


def page_html(cfg: dict, settings: dict, session=None) -> str:
    """수집기들이 공통으로 쓰는 HTML 취득 경로."""
    url = cfg["url"]
    if not cfg.get("render"):
        resp = http.get(
            url,
            timeout=settings.get("request_timeout", 25),
            delay=settings.get("request_delay", 1.2),
            session=session,
        )
        return resp.text

    log.info("[%s] 브라우저 렌더링", cfg.get("id", "?"))
    return browser.render(
        url,
        wait_for=cfg.get("wait_for"),
        eval_js=cfg.get("eval_js"),
        timeout_ms=settings.get("render_timeout_ms", browser.DEFAULT_TIMEOUT_MS),
    )
