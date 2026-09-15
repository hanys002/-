"""이전 실행에서 본 공고를 기억해 'NEW' 배지를 붙인다."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

RETENTION_DAYS = 400


def load(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save(path: Path, seen: dict[str, str]) -> None:
    cutoff = (date.today() - timedelta(days=RETENTION_DAYS)).isoformat()
    pruned = {k: v for k, v in seen.items() if v >= cutoff}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(pruned, ensure_ascii=False, indent=0, sort_keys=True),
        encoding="utf-8",
    )


def mark_new(postings, seen: dict[str, str]) -> int:
    """처음 보는 공고에 is_new를 세우고, 신규 건수를 돌려준다."""
    today = date.today().isoformat()
    count = 0
    for post in postings:
        if post.key not in seen:
            post.is_new = True
            count += 1
        seen[post.key] = today
    return count
