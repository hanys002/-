"""
사람인(saramin.co.kr) 키워드 검색 크롤러.

주의: 사람인은 페이지 구조를 종종 바꾼다. 아래는 흔히 쓰이는 클래스명을 우선
시도하고, 실패하면 '상세페이지 링크에는 항상 rec_idx= 파라미터가 붙는다'는
안정적인 규칙을 이용해 링크를 찾아내는 방식으로 이중 안전장치를 뒀다.
검색 결과가 계속 비어 있으면 브라우저 개발자 도구로 실제 클래스명을 확인해
SELECTORS 를 수정하면 된다.
"""
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from .base import JobPosting, absolute_url, fetch_html

SEARCH_URL = "https://www.saramin.co.kr/zf_user/search/recruit"
SOURCE_NAME = "사람인"
REC_IDX_RE = re.compile(r"rec_idx=(\d+)")


def _parse_with_known_selectors(soup: BeautifulSoup, base_url: str) -> list[JobPosting]:
    postings = []
    for item in soup.select("div.item_recruit"):
        title_tag = item.select_one("h2.job_tit a") or item.select_one("a.job_link")
        if not title_tag or not title_tag.get("href"):
            continue
        company_tag = item.select_one(".corp_name a") or item.select_one(".area_corp a")
        postings.append(
            JobPosting(
                source=SOURCE_NAME,
                title=title_tag.get_text(strip=True),
                link=absolute_url(base_url, title_tag["href"]),
                company=company_tag.get_text(strip=True) if company_tag else "",
            )
        )
    return postings


def _parse_with_link_pattern(soup: BeautifulSoup, base_url: str) -> list[JobPosting]:
    postings = []
    seen_idx = set()
    for a in soup.find_all("a", href=True):
        match = REC_IDX_RE.search(a["href"])
        title = a.get_text(strip=True)
        if not match or not title:
            continue
        idx = match.group(1)
        if idx in seen_idx:
            continue
        seen_idx.add(idx)
        postings.append(
            JobPosting(
                source=SOURCE_NAME,
                title=title,
                link=absolute_url(base_url, a["href"]),
            )
        )
    return postings


def search(keyword: str, extra_query: str = "") -> list[JobPosting]:
    url = f"{SEARCH_URL}?searchword={quote(keyword)}&recruitPageCount=40"
    if extra_query:
        url += f"&{extra_query}"

    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    postings = _parse_with_known_selectors(soup, url)
    if not postings:
        postings = _parse_with_link_pattern(soup, url)
    return postings
