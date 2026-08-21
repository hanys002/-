"""공통 데이터 구조 및 유틸."""
from dataclasses import dataclass
from urllib.parse import urljoin

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass
class JobPosting:
    source: str          # 출처 사이트 이름
    title: str
    link: str
    company: str = ""
    posted_at: str = ""

    @property
    def uid(self) -> str:
        """중복 판별용 고유 키 (출처 + 링크)."""
        return f"{self.source}:{self.link}"


def fetch_html(url: str, timeout: int = 10) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    return resp.text


def absolute_url(base_url: str, href: str) -> str:
    return urljoin(base_url, href)


def matches_keywords(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(kw.lower() in lowered for kw in keywords)
