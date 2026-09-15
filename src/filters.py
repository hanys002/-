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
    """보유 자격증명이 제목·본문에 직접 적힌 공고만 채택한다.

    판정
      1. exclude        — 채용이 아닌 글(학원 광고)·마감 공고면 탈락
      2. hiring_signals — 게시판 목록에서 메뉴·뉴스를 걸러내기 위한 채용 신호어
      3. qualifications — 자격증명이 직접 적혀 있어야 채택

    이전에는 직무·등급 표현(감리원·선임자·중급·특급·기술자)을 분야 한정어와
    조합해 채택했으나, 그 방식은 자격과 무관한 공고를 대량으로 통과시켰다.
    '정보통신감리원 모집'은 기술사를 요구하지 않는 자리다. 자격증명이
    적히지 않은 공고는 채택하지 않는다.

    normalize()가 공백·특수문자를 제거하므로 '정보통신 기술사'처럼 띄어 쓴
    표기도 '정보통신기술사'로 매칭된다.
    """

    def __init__(self, cfg: dict):
        self.qualifications = cfg.get("qualifications", [])
        self.hiring_signals = cfg.get("hiring_signals", [])
        self.exclude = cfg.get("exclude", [])

    def has_hiring_signal(self, title: str) -> bool:
        """제목에 채용 의사 표현이 있는지. 게시판 목록 전용 판정.

        협회 사이트를 통째로 훑으면 카테고리 메뉴와 뉴스 기사가 함께 걸린다.
        이들은 자격증명이 적혀 있어도 채용 신호어가 없다는 점에서 구별된다.
        """
        if not self.hiring_signals:
            return True
        blob = normalize(title)
        return any(normalize(sig) in blob for sig in self.hiring_signals)

    def is_excluded(self, *texts: str) -> bool:
        """채용이 아닌 글이거나 이미 끝난 공고인지."""
        blob = normalize(" ".join(t for t in texts if t))
        return any(normalize(bad) in blob for bad in self.exclude)

    def match(self, *texts: str) -> list[str]:
        """적힌 자격증명 목록. 하나도 없으면 빈 리스트."""
        blob = normalize(" ".join(t for t in texts if t))
        if not blob or self.is_excluded(*texts):
            return []
        return [q for q in self.qualifications if normalize(q) in blob]


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
