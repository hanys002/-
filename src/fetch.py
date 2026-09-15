"""소스 HTML 취득. 설정의 render 여부에 따라 정적/브라우저를 고른다."""
from __future__ import annotations

import logging
import os

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
        login=_browser_login(cfg),
        timeout_ms=settings.get("render_timeout_ms", browser.DEFAULT_TIMEOUT_MS),
    )


def _browser_login(cfg: dict) -> dict | None:
    """브라우저 로그인에 쓸 자격정보. 환경변수(=시크릿)에서만 읽는다."""
    login = cfg.get("login")
    if not login or not login.get("form_url"):
        return None
    user = os.environ.get(login.get("id_env", ""), "").strip()
    password = os.environ.get(login.get("pw_env", ""), "").strip()
    if not user or not password:
        log.info("[%s] 브라우저 로그인 자격정보 없음", cfg.get("id", "?"))
        return None
    return {
        "url": login["form_url"],
        "id_field": login.get("id_field", "userID"),
        "pw_field": login.get("pw_field", "password"),
        "user": user,
        "password": password,
    }
