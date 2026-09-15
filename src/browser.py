"""브라우저 렌더링 수집.

일부 협회 사이트는 정적 HTML에 게시글이 없다.
  - 정보통신기술사회: 메뉴가 전부 javascript:menu('sub7_1') — 링크에 주소가 없다
  - 대한기술사회: jquery.tmpl로 목록을 클라이언트에서 그린다

주소를 추정해 맞히려는 시도는 전부 404였다(후보 9개). 브라우저로 실제 렌더링하면
주소 규칙을 몰라도 되고, JS가 그린 결과를 그대로 읽을 수 있다.

느리고(수 초) 무거우므로 `render: true`가 지정된 소스에만 쓴다.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 30000
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")


class BrowserUnavailable(RuntimeError):
    """Playwright 미설치 등으로 렌더링할 수 없음."""


# 로그인 폼이 레이어 팝업 안에 숨어 있으면 page.fill이 '보이는 요소'를 기다리다
# 타임아웃 난다(실측: ITPE에서 30초 초과). 폼은 DOM에 있으므로 JS로 직접 채운다.
_LOGIN_JS = """([idField, pwField, user, password]) => {
  const input = document.querySelector(`input[name="${idField}"]`);
  if (!input) return 'no-field';
  const form = input.form;
  if (!form) return 'no-form';
  form.querySelector(`[name="${idField}"]`).value = user;
  const pw = form.querySelector(`[name="${pwField}"]`);
  if (!pw) return 'no-password-field';
  pw.value = password;
  form.submit();
  return 'submitted';
}"""


def _do_login(page, login: dict, timeout_ms: int) -> None:
    """브라우저에서 로그인 폼을 채우고 제출한다.

    requests 세션 로그인과 달리, 로그인 후 JS 메뉴를 그대로 클릭할 수 있다.
    회원 전용 게시판의 실제 주소를 모를 때 이 경로가 유일한 방법이다.
    """
    page.goto(login["url"], wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        result = page.evaluate(
            _LOGIN_JS,
            [login["id_field"], login["pw_field"], login["user"], login["password"]],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("로그인 폼 조작 실패(%s) — 비로그인으로 진행", exc)
        return

    if result != "submitted":
        log.warning("로그인 폼을 찾지 못함(%s) — 비로그인으로 진행", result)
        return

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:  # noqa: BLE001
        pass
    log.info("로그인 제출 후 위치: %s", page.url)


def render(url: str, *, wait_for: str | None = None, eval_js: str | None = None,
           login: dict | None = None,
           timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """페이지를 렌더링해 최종 HTML을 돌려준다.

    eval_js: 페이지 로드 후 실행할 JS. 메뉴 함수 호출로 게시판에 진입할 때 쓴다.
             예) "menu('sub7_1')"
    wait_for: 이 선택자가 나타날 때까지 기다린다. AJAX 목록이 그려지길 기다릴 때.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # noqa: BLE001
        raise BrowserUnavailable(f"playwright 미설치: {exc}") from exc

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(user_agent=UA, locale="ko-KR",
                                    viewport={"width": 1280, "height": 900})
            page.set_default_timeout(timeout_ms)

            if login:
                _do_login(page, login, timeout_ms)

            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

            if eval_js:
                log.info("JS 실행: %s", eval_js)
                page.evaluate(eval_js)

            # networkidle은 광고·트래커가 있으면 영원히 안 오므로 실패를 삼킨다.
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:  # noqa: BLE001
                pass

            if wait_for:
                try:
                    page.wait_for_selector(wait_for, timeout=10000)
                except Exception:  # noqa: BLE001
                    log.warning("대기 선택자 '%s' 미출현 — 현재 상태로 진행", wait_for)

            # JS로 이동하는 사이트는 이 최종 주소가 게시판의 실제 URL이다.
            log.info("최종 위치: %s", page.url)
            return page.content()
        finally:
            browser.close()
