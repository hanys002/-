"""
카카오 '나에게 보내기' 사용을 위한 최초 1회 인증 도구.

사용법:
  1) python src/kakao_auth.py url          -> 인가 코드 발급용 URL 출력
  2) 브라우저에서 그 URL 접속 -> 카카오 로그인 -> 동의 -> 리다이렉트된 주소창에서 "code=" 뒤의 값 복사
  3) python src/kakao_auth.py exchange <복사한 코드>
     -> access_token / refresh_token 을 발급받아 .env 에 자동 저장
"""
import sys

import requests

from config import KAKAO_REDIRECT_URI, KAKAO_REST_API_KEY, update_env_tokens

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"


def print_authorize_url() -> None:
    if not KAKAO_REST_API_KEY:
        print("먼저 .env 에 KAKAO_REST_API_KEY 를 설정하세요.")
        return
    params = (
        f"?client_id={KAKAO_REST_API_KEY}"
        f"&redirect_uri={KAKAO_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=talk_message"
    )
    print("아래 URL을 브라우저에 붙여넣고 카카오 로그인 후 동의하세요.")
    print(AUTHORIZE_URL + params)


def exchange_code_for_token(code: str) -> None:
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": KAKAO_REST_API_KEY,
            "redirect_uri": KAKAO_REDIRECT_URI,
            "code": code,
        },
        timeout=10,
    )
    resp.raise_for_status()
    payload = resp.json()
    access_token = payload["access_token"]
    refresh_token = payload.get("refresh_token")
    update_env_tokens(access_token, refresh_token)
    print("발급 완료. .env 에 KAKAO_ACCESS_TOKEN / KAKAO_REFRESH_TOKEN 을 저장했습니다.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    if command == "url":
        print_authorize_url()
    elif command == "exchange":
        if len(sys.argv) < 3:
            print("사용법: python src/kakao_auth.py exchange <인가코드>")
            sys.exit(1)
        exchange_code_for_token(sys.argv[2])
    else:
        print(__doc__)
