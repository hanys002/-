"""공용 HTTP 클라이언트: 재시도, 인코딩 자동판별, 예의상 rate limit."""
from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

_last_call: dict[str, float] = {}


def _throttle(host: str, delay: float) -> None:
    prev = _last_call.get(host, 0.0)
    wait = delay - (time.time() - prev)
    if wait > 0:
        time.sleep(wait)
    _last_call[host] = time.time()


def get(
    url: str,
    *,
    params: dict | None = None,
    timeout: int = 25,
    delay: float = 1.2,
    retries: int = 3,
) -> requests.Response:
    """GET + 지수 백오프 재시도. 마지막 실패는 예외로 전파한다."""
    host = requests.utils.urlparse(url).netloc
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }
    last: Exception | None = None
    for attempt in range(retries):
        try:
            _throttle(host, delay)
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            # 국내 사이트는 EUC-KR/CP949가 흔하다. requests 추정이 빗나가면 apparent로 교정.
            if resp.encoding in (None, "ISO-8859-1"):
                resp.encoding = resp.apparent_encoding or "utf-8"
            return resp
        except Exception as exc:  # noqa: BLE001 - 소스별로 격리해 리포트에 남긴다
            last = exc
            if attempt < retries - 1:
                back = 2 ** attempt
                log.warning("GET %s 실패(%s) — %ss 후 재시도", url, exc, back)
                time.sleep(back)
    raise last  # type: ignore[misc]
