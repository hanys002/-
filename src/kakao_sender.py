"""카카오톡 '나에게 보내기' 메시지 전송."""
import json

import requests

import config

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


class KakaoAuthError(RuntimeError):
    pass


def _refresh_access_token() -> str:
    if not config.KAKAO_REFRESH_TOKEN:
        raise KakaoAuthError(
            "액세스 토큰이 만료되었고 refresh token도 없습니다. "
            "kakao_auth.py 를 다시 실행해 재인증하세요."
        )
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": config.KAKAO_REST_API_KEY,
            "refresh_token": config.KAKAO_REFRESH_TOKEN,
        },
        timeout=10,
    )
    resp.raise_for_status()
    payload = resp.json()
    new_access_token = payload["access_token"]
    new_refresh_token = payload.get("refresh_token")  # 응답에 없을 수도 있음
    config.update_env_tokens(new_access_token, new_refresh_token)
    config.KAKAO_ACCESS_TOKEN = new_access_token
    if new_refresh_token:
        config.KAKAO_REFRESH_TOKEN = new_refresh_token
    return new_access_token


def send_text_to_me(text: str, link_url: str | None = None, button_title: str = "채용공고 보기") -> None:
    """카카오톡 '나에게 보내기'로 텍스트 메시지 1건을 전송한다."""
    if not config.KAKAO_ACCESS_TOKEN:
        _refresh_access_token()

    template_object = {
        "object_type": "text",
        "text": text[:200],
        "link": {
            "web_url": link_url or "https://www.saramin.co.kr",
            "mobile_web_url": link_url or "https://www.saramin.co.kr",
        },
    }
    if link_url:
        template_object["button_title"] = button_title

    def _post(token: str) -> requests.Response:
        return requests.post(
            SEND_URL,
            headers={"Authorization": f"Bearer {token}"},
            data={"template_object": json.dumps(template_object, ensure_ascii=False)},
            timeout=10,
        )

    resp = _post(config.KAKAO_ACCESS_TOKEN)
    if resp.status_code == 401:
        token = _refresh_access_token()
        resp = _post(token)

    if resp.status_code != 200:
        raise RuntimeError(f"카카오톡 전송 실패 ({resp.status_code}): {resp.text}")
