"""키워드 적합성 판정 및 한국어 날짜 파싱."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .models import normalize

# "2026-09-14", "2026.09.14", "2026/09/14", "26.09.14", "09-14"
_DATE_PATTERNS = [
    (re.compile(r"(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})"), "ymd"),
    (re.compile(r"\b(\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})\b"), "yymd"),
    (re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})\b"), "md"),
]

_RELATIVE = re.compile(r"(\d+)\s*(분|시간|일|주|개월)\s*전")


def parse_date(text: str, today: date | None = None) -> date | None:
    """게시판 셀 텍스트에서 날짜를 뽑아낸다. 실패하면 None."""
    if not text:
        return None
    today = today or date.today()
    text = text.strip()

    if "오늘" in text or "방금" in text:
        return today
    if "어제" in text:
        return today - timedelta(days=1)

    rel = _RELATIVE.search(text)
    if rel:
        n, unit = int(rel.group(1)), rel.group(2)
        days = {"분": 0, "시간": 0, "일": n, "주": n * 7, "개월": n * 30}[unit]
        return today - timedelta(days=days)

    for pattern, kind in _DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        try:
            if kind == "ymd":
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if kind == "yymd":
                return date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
            # 연도 없는 MM-DD: 미래면 작년으로 간주
            cand = date(today.year, int(m.group(1)), int(m.group(2)))
            return cand if cand <= today else cand.replace(year=today.year - 1)
        except ValueError:
            continue
    return None


class KeywordMatcher:
    """primary는 단독 채택, secondary는 context 동반 시 채택, exclude는 즉시 탈락."""

    def __init__(self, cfg: dict):
        self.primary = cfg.get("primary", [])
        self.secondary = cfg.get("secondary", [])
        self.context = cfg.get("context", [])
        self.exclude = cfg.get("exclude", [])

    def match(self, *texts: str) -> list[str]:
        """적합하면 매칭된 키워드 목록, 아니면 빈 리스트."""
        blob = normalize(" ".join(t for t in texts if t))
        if not blob:
            return []

        if any(normalize(bad) in blob for bad in self.exclude):
            return []

        hits = [kw for kw in self.primary if normalize(kw) in blob]
        if hits:
            return hits

        soft = [kw for kw in self.secondary if normalize(kw) in blob]
        if soft and any(normalize(c) in blob for c in self.context):
            return soft
        return []


def parse_iso(value: str) -> date | None:
    """API가 돌려주는 ISO/숫자 날짜 문자열 파싱."""
    if not value:
        return None
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%dT%H:%M:%S", "%Y.%m.%d"):
        try:
            return datetime.strptime(value[: len(fmt) + 2].strip(), fmt).date()
        except ValueError:
            continue
    if value.isdigit() and len(value) >= 10:  # epoch seconds / millis
        ts = int(value[:10])
        return datetime.fromtimestamp(ts).date()
    return parse_date(value)
