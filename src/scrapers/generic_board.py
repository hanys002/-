"""
일반적인 협회/단체 게시판(구인구직 게시판)용 범용 크롤러.

사이트마다 HTML 구조(클래스명 등)가 다르고 이 환경에서는 실제 페이지를
가져와 구조를 확인할 수 없었기 때문에(네트워크 정책상 접근 차단), 특정
클래스명에 의존하지 않는 방식으로 작성했다:

  1) 흔히 쓰이는 게시판 셀렉터 후보들을 순서대로 시도한다.
  2) 전부 실패하면 페이지 전체에서 "그럴듯한 게시글 제목처럼 보이는
     링크"(글자 수, 네비게이션성 문구 제외 등)를 휴리스틱으로 추출한다.

실제 사용 시 결과가 이상하면(공고가 하나도 안 잡히거나 엉뚱한 링크가 잡히면)
브라우저 개발자 도구(F12)로 게시글 목록의 실제 태그/클래스를 확인한 뒤
LIST_SELECTOR_CANDIDATES 맨 앞에 해당 사이트 전용 셀렉터를 추가하면 된다.
"""
import re

from bs4 import BeautifulSoup

from .base import JobPosting, absolute_url, fetch_html

LIST_SELECTOR_CANDIDATES = [
    "table.board_list tbody tr td.subject a, table.board_list tbody tr td.title a",
    "table.bbs_list tbody tr td.subject a, table.bbs_list tbody tr td.title a",
    "ul.board_list li a, ul.bbs-list li a",
    "div.board_list li a, div.bbs-list li a",
    ".list_wrap a, .boardList a",
]

_NAV_WORDS = {"로그인", "회원가입", "다음", "이전", "처음", "마지막", "검색", "홈", "menu", "top"}
_MIN_TITLE_LEN = 6


def _looks_like_title(text: str) -> bool:
    text = text.strip()
    if len(text) < _MIN_TITLE_LEN:
        return False
    if text in _NAV_WORDS:
        return False
    return True


def _extract_with_selectors(soup: BeautifulSoup, base_url: str, source_name: str) -> list[JobPosting]:
    for selector in LIST_SELECTOR_CANDIDATES:
        anchors = soup.select(selector)
        results = [a for a in anchors if a.get("href") and _looks_like_title(a.get_text())]
        if results:
            return [
                JobPosting(
                    source=source_name,
                    title=a.get_text(strip=True),
                    link=absolute_url(base_url, a["href"]),
                )
                for a in results
            ]
    return []


def _extract_heuristic(soup: BeautifulSoup, base_url: str, source_name: str) -> list[JobPosting]:
    postings = []
    seen_links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("javascript:") or href.strip() == "#":
            continue
        text = a.get_text(strip=True)
        if not _looks_like_title(text):
            continue
        link = absolute_url(base_url, href)
        if link in seen_links:
            continue
        seen_links.add(link)
        postings.append(JobPosting(source=source_name, title=text, link=link))
    return postings


def scrape_board(
    url: str,
    source_name: str,
    keyword_filter: list[str] | None = None,
) -> list[JobPosting]:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    postings = _extract_with_selectors(soup, url, source_name)
    if not postings:
        postings = _extract_heuristic(soup, url, source_name)

    if keyword_filter:
        pattern = "|".join(re.escape(kw) for kw in keyword_filter)
        postings = [p for p in postings if re.search(pattern, p.title, re.IGNORECASE)]

    return postings
