"""환경변수(.env) 로딩과 전역 설정."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
DATA_DIR = ROOT_DIR / "data"
SEEN_STORE_PATH = DATA_DIR / "seen.json"

load_dotenv(ENV_PATH)

NAVER_EMAIL = os.getenv("NAVER_EMAIL", "")
NAVER_APP_PASSWORD = os.getenv("NAVER_APP_PASSWORD", "")
MAIL_TO = os.getenv("MAIL_TO", "hanys002@naver.com")

SEARCH_KEYWORDS = [
    kw.strip() for kw in os.getenv("SEARCH_KEYWORDS", "기술사").split(",") if kw.strip()
]
SARAMIN_EXTRA_QUERY = os.getenv("SARAMIN_EXTRA_QUERY", "")

DATA_DIR.mkdir(exist_ok=True)
