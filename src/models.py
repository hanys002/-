"""수집 결과 데이터 모델."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Posting:
    """채용공고 1건."""

    source_id: str
    source_name: str
    org: str
    title: str
    url: str
    posted_on: Optional[date] = None
    company: str = ""
    location: str = ""
    deadline: str = ""
    matched: list[str] = field(default_factory=list)
    is_new: bool = False

    @property
    def key(self) -> str:
        """중복 제거 키. URL 우선, 없으면 제목 해시."""
        basis = self.url.strip() or f"{self.source_id}:{normalize(self.title)}"
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]

    @property
    def date_text(self) -> str:
        return self.posted_on.strftime("%Y-%m-%d") if self.posted_on else "날짜미상"


@dataclass
class SourceResult:
    """소스 1곳의 수집 결과 및 진단 정보."""

    source_id: str
    source_name: str
    ok: bool
    postings: list[Posting] = field(default_factory=list)
    error: str = ""
    scanned: int = 0

    @property
    def status_text(self) -> str:
        if not self.ok:
            return f"실패 — {self.error[:160]}"
        return f"정상 — {self.scanned}건 스캔 / {len(self.postings)}건 적합"


def normalize(text: str) -> str:
    """공백·특수문자를 제거한 비교용 문자열."""
    return re.sub(r"[\s\W_]+", "", (text or "")).lower()
