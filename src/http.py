"""공용 HTTP 클라이언트: 재시도, 인코딩 자동판별, 예의상 rate limit."""
from __future__ import annotations

import logging
import os
import ssl
import time

import requests
from requests.adapters import HTTPAdapter

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

_last_call: dict[str, float] = {}


class _LegacyTLSAdapter(HTTPAdapter):
    """구형 서명 알고리즘(SHA1-RSA 등)을 쓰는 서버용 어댑터.

    OpenSSL 3.x는 기본 보안수준(SECLEVEL=2)에서 이런 인증서를 거부해
    WRONG_SIGNATURE_TYPE으로 핸드셰이크가 깨진다. 국내 협회·공공 사이트에
    아직 흔해 SECLEVEL만 낮춰 연결한다. **인증서 검증은 그대로 유지**한다.
    """

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0)
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


_legacy_session: requests.Session | None = None


def _legacy() -> requests.Session:
    global _legacy_session
    if _legacy_session is None:
        _legacy_session = requests.Session()
        _legacy_session.mount("https://", _LegacyTLSAdapter())
    return _legacy_session


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
    session: requests.Session | None = None,
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
            getter = session.get if session is not None else requests.get
            try:
                resp = getter(url, params=params, headers=headers, timeout=timeout)
            except requests.exceptions.SSLError:
                # 구형 TLS 서버 — 보안수준을 낮춘 세션으로 1회 재시도
                log.warning("%s TLS 핸드셰이크 실패 — 레거시 TLS로 재시도", host)
                if session is not None:
                    session.mount("https://", _LegacyTLSAdapter())
                    resp = session.get(url, params=params, headers=headers, timeout=timeout)
                else:
                    resp = _legacy().get(url, params=params, headers=headers, timeout=timeout)
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


def login(cfg: dict, source_id: str) -> requests.Session | None:
    """협회 게시판 로그인. 자격정보는 환경변수(=GitHub 시크릿)에서만 읽는다.

    설정 예:
        login:
          url: https://www.kpea.or.kr/kpea/member/LoginProc.do
          id_field: userId
          pw_field: userPw
          id_env: KPEA_ID
          pw_env: KPEA_PW
          extra: {returnUrl: "/"}
          success_marker: 로그아웃

    자격정보가 없으면 None을 돌려주고 비로그인으로 진행한다.
    """
    if not cfg:
        return None
    user = os.environ.get(cfg.get("id_env", ""), "").strip()
    password = os.environ.get(cfg.get("pw_env", ""), "").strip()
    if not user or not password:
        log.info("[%s] 로그인 자격정보 없음 — 비로그인으로 진행", source_id)
        return None

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    payload = dict(cfg.get("extra") or {})
    payload[cfg.get("id_field", "userId")] = user
    payload[cfg.get("pw_field", "userPw")] = password

    try:
        resp = session.post(cfg["url"], data=payload, timeout=25, allow_redirects=True)
        resp.raise_for_status()
        if resp.encoding in (None, "ISO-8859-1"):
            resp.encoding = resp.apparent_encoding or "utf-8"
    except Exception as exc:  # noqa: BLE001 - 로그인 실패해도 비로그인으로 계속한다
        log.warning("[%s] 로그인 요청 실패(%s) — 비로그인으로 진행", source_id, exc)
        return None

    marker = cfg.get("success_marker", "로그아웃")
    if marker and marker not in resp.text:
        log.warning("[%s] 로그인 실패로 보임 — '%s'를 찾지 못함. 비로그인으로 진행",
                    source_id, marker)
        return None

    log.info("[%s] 로그인 성공", source_id)
    return session
