"""이미 알림을 보낸 공고를 기록해서 중복 전송을 막는다."""
import json

from config import SEEN_STORE_PATH


def load_seen_ids() -> set[str]:
    if not SEEN_STORE_PATH.exists():
        return set()
    try:
        return set(json.loads(SEEN_STORE_PATH.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen_ids(seen_ids: set[str]) -> None:
    # 파일이 무한히 커지지 않도록 최근 2000개만 유지
    trimmed = list(seen_ids)[-2000:]
    SEEN_STORE_PATH.write_text(
        json.dumps(trimmed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
