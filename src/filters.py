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
    """보유 자격 3종(정보통신·산업계측제어·전자응용 기술사)에 한정해 선별한다.

    판정 순서
      1. exclude   — 채용이 아닌 글(학원 광고 등)이면 즉시 탈락
      2. primary   — 자격증명이 직접 적혔으면 채택.
                     타 분야 기술사가 함께 적혀 있어도 버리지 않는다.
      3. other_fields — primary가 없는데 타 분야 기술사가 보이면 탈락
      4. role AND domain — 기술사급 직무 + 해당 분야가 둘 다 있어야 채택

    role만으로 채택하면 맨 '기술사'에 토목·건축·전기 공고가 전부 걸린다.
    domain에 '엔지니어링/설계' 같은 범용어를 넣어도 같은 결과가 되므로,
    domain은 반드시 3개 자격의 분야로만 유지할 것.
    """

    def __init__(self, cfg: dict):
        self.primary = cfg.get("primary", [])
        self.role = cfg.get("role", [])
        self.domain = cfg.get("domain", [])
        self.other_fields = cfg.get("other_fields", [])
        self.exclude = cfg.get("exclude", [])
        self.hiring_signals = cfg.get("hiring_signals", [])

    def has_hiring_signal(self, title: str) -> bool:
        """제목에 채용 의사 표현이 있는지. 게시판 목록 전용 판정.

        협회 사이트를 통째로 훑으면 카테고리 메뉴('전기·전자·정보기술')와
        뉴스 기사('정보공학기술사회 정기총회 개최')가 함께 걸린다. 이들은
        키워드는 맞지만 채용 신호어가 없다는 점에서 공고와 구별된다.
        """
        if not self.hiring_signals:
            return True
        blob = normalize(title)
        return any(normalize(sig) in blob for sig in self.hiring_signals)

    def is_excluded(self, *texts: str) -> bool:
        """채용이 아닌 글인지만 판정한다.

        포털 검색 결과처럼 이미 키워드로 걸러진 목록에 쓴다. 포털은 자격요건
        본문까지 검색하므로 제목만 다시 검사하면 정당한 공고를 대부분 버린다.
        """
        blob = normalize(" ".join(t for t in texts if t))
        return any(normalize(bad) in blob for bad in self.exclude)

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

        if any(normalize(other) in blob for other in self.other_fields):
            return []

        roles = [kw for kw in self.role if normalize(kw) in blob]
        if roles and any(normalize(d) in blob for d in self.domain):
            return roles
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
