"""환경변수(.env) 로딩과 전역 설정."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
DATA_DIR = ROOT_DIR / "data"
SEEN_STORE_PATH = DATA_DIR / "seen.json"

load_dotenv(ENV_PATH)

KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")
KAKAO_REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI", "https://localhost.com")
KAKAO_ACCESS_TOKEN = os.getenv("KAKAO_ACCESS_TOKEN", "")
KAKAO_REFRESH_TOKEN = os.getenv("KAKAO_REFRESH_TOKEN", "")

SEARCH_KEYWORDS = [
    kw.strip() for kw in os.getenv("SEARCH_KEYWORDS", "기술사").split(",") if kw.strip()
]
SARAMIN_EXTRA_QUERY = os.getenv("SARAMIN_EXTRA_QUERY", "")

DATA_DIR.mkdir(exist_ok=True)


def update_env_tokens(access_token: str, refresh_token: str | None = None) -> None:
    """kakao_auth.py / 토큰 자동 갱신 시 .env 파일의 토큰 값을 갱신한다."""
    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    def _set(lines: list[str], key: str, value: str) -> list[str]:
        found = False
        out = []
        for line in lines:
            if line.startswith(f"{key}="):
                out.append(f"{key}={value}")
                found = True
            else:
                out.append(line)
        if not found:
            out.append(f"{key}={value}")
        return out

    lines = _set(lines, "KAKAO_ACCESS_TOKEN", access_token)
    if refresh_token:
        lines = _set(lines, "KAKAO_REFRESH_TOKEN", refresh_token)

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
