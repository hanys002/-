"""수집기·필터·리포트 파이프라인 단위 테스트 (네트워크 불필요)."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.collectors.generic_board import collect as board_collect  # noqa: E402
from src.filters import KeywordMatcher, parse_date  # noqa: E402
from src.main import dedupe  # noqa: E402
from src.models import Posting  # noqa: E402
from src.report import build_html, sort_and_split  # noqa: E402
from src import http  # noqa: E402

TODAY = date(2026, 9, 15)

KEYWORDS = {
    "primary": ["정보통신기술사", "산업계측제어기술사", "전자응용기술사"],
    "secondary": ["기술사", "수석감리원", "감리원"],
    "context": ["정보통신", "계측", "제어", "전자"],
    "exclude": ["수강생", "개강", "기출문제"],
}

BOARD_HTML = """
<html><body><table><tbody>
  <tr><td>1</td><td><a href="/view.do?id=101">정보통신기술사 감리원 모집 (상주)</a></td>
      <td>주식회사 가나기술단</td><td>2026-09-12</td></tr>
  <tr><td>2</td><td><a href="/view.do?id=102">산업계측제어기술사 채용 - 플랜트 계장설계</a></td>
      <td>대한엔지니어링</td><td>2026.09.01</td></tr>
  <tr><td>3</td><td><a href="/view.do?id=103">정보통신기술사 자격증 대비반 수강생 모집</a></td>
      <td>OO학원</td><td>2026-09-14</td></tr>
  <tr><td>4</td><td><a href="/view.do?id=104">건축 시공 현장소장 구함</a></td>
      <td>무관건설</td><td>2026-09-13</td></tr>
  <tr><td>5</td><td><a href="/view.do?id=105">전자응용기술사 우대 - 반도체 계측장비 개발</a></td>
      <td>한빛세미콘</td><td>2025-12-20</td></tr>
</tbody></table></body></html>
"""

CFG = {
    "id": "test", "name": "테스트 게시판", "org": "테스트협회",
    "url": "https://example.or.kr/board", "base": "https://example.or.kr",
    "row_selector": "table tbody tr", "title_selector": "a",
    "date_selector": "td:nth-last-child(1)", "link_attr": "href",
}
SETTINGS = {"max_items_per_source": 60, "request_timeout": 5, "request_delay": 0}


class FakeResponse:
    text = BOARD_HTML


def test_board_collection_filters_correctly(monkeypatch_get):
    posts, scanned = board_collect(CFG, SETTINGS, KeywordMatcher(KEYWORDS))
    titles = [p.title for p in posts]
    assert scanned == 5
    assert len(posts) == 3, titles                      # 학원 광고/무관 공고 제외
    assert not any("수강생" in t for t in titles)        # exclude 동작
    assert not any("현장소장" in t for t in titles)      # 키워드 미매칭
    assert posts[0].url == "https://example.or.kr/view.do?id=101"
    assert posts[0].posted_on == date(2026, 9, 12)
    assert posts[0].matched == ["정보통신기술사"]
    print("  ✓ 게시판 수집/필터:", len(posts), "건 채택 ->", titles)


def test_date_parsing():
    cases = {
        "2026-09-12": date(2026, 9, 12),
        "2026.09.01": date(2026, 9, 1),
        "26.09.03": date(2026, 9, 3),
        "등록일 2026년 8월 7일": date(2026, 8, 7),
        "3일 전": TODAY - timedelta(days=3),
        "오늘": TODAY,
        "2개월 전": TODAY - timedelta(days=60),
        "": None,
        "마감임박": None,
    }
    for text, expected in cases.items():
        got = parse_date(text, today=TODAY)
        assert got == expected, f"{text!r} -> {got} (기대 {expected})"
    print("  ✓ 날짜 파싱:", len(cases), "케이스 통과")


def test_six_month_split_and_order():
    posts = [
        Posting("s", "n", "o", "오래된 정보통신기술사", "u1", date(2025, 1, 5)),
        Posting("s", "n", "o", "최신 정보통신기술사", "u2", date(2026, 9, 14)),
        Posting("s", "n", "o", "중간 전자응용기술사", "u3", date(2026, 6, 1)),
        Posting("s", "n", "o", "날짜미상 산업계측제어기술사", "u4", None),
        Posting("s", "n", "o", "경계 직전", "u5", TODAY - timedelta(days=182)),
        Posting("s", "n", "o", "경계 직후", "u6", TODAY - timedelta(days=184)),
    ]
    recent, old = sort_and_split(posts, 183, today=TODAY)
    assert [p.url for p in recent] == ["u2", "u3", "u5", "u4"], [p.url for p in recent]
    assert [p.url for p in old] == ["u6", "u1"], [p.url for p in old]
    print("  ✓ 최신순 정렬 + 6개월 분할: 최근", len(recent), "/ 참고", len(old))


def test_dedupe_prefers_dated():
    posts = [
        Posting("a", "A", "O", "같은 공고", "https://x/1", None),
        Posting("b", "B", "O", "같은 공고", "https://x/1", date(2026, 9, 10)),
    ]
    merged = dedupe(posts)
    assert len(merged) == 1 and merged[0].posted_on == date(2026, 9, 10)
    print("  ✓ 중복 제거: 날짜 있는 레코드 우선")


def test_html_report_renders_links_and_escapes():
    posts = [Posting("s", "테스트", "협회", 'XSS <script> & "따옴표" 기술사 정보통신',
                     "https://example.or.kr/a?b=1&c=2", date(2026, 9, 14), is_new=True)]
    recent, old = sort_and_split(posts, 183, today=TODAY)
    html = build_html(recent, old, [], 1, 183, TODAY)
    assert 'href="https://example.or.kr/a?b=1&amp;c=2"' in html
    assert "<script>" not in html                      # 이스케이프 확인
    assert "NEW" in html and "2026-09-14" in html
    assert "최근 6개월 이내" in html
    print("  ✓ HTML 리포트: 링크/이스케이프/NEW 배지 정상")


def test_search_query_does_not_bypass_filter():
    """회귀: 검색어를 매처에 넘기면 모든 결과가 통과하던 버그 (run #1에서 61건 중 57건 오탐)."""
    m = KeywordMatcher(KEYWORDS)
    # 포털 검색 결과에 섞여 나오는 무관한 공고
    assert not m.match("일반 사무보조 채용", "무관상사")
    # 검색어를 함께 넘기면 무관한 공고까지 통과해 버린다 — 넘기지 않아야 한다
    assert m.match("일반 사무보조 채용", "무관상사", "정보통신기술사")
    print("  ✓ 검색어 우회 회귀: 검색어 미전달 시 오탐 차단 확인")


def test_fallback_runs_when_rows_matched_but_nothing_adopted(monkeypatch_get):
    """회귀: 선택자가 행을 일부만 잡아도(kpea 1건) 폴백이 돌아야 한다."""
    bad_cfg = dict(CFG, row_selector="table thead tr")   # 존재하지 않는 행
    posts, scanned = board_collect(bad_cfg, SETTINGS, KeywordMatcher(KEYWORDS))
    assert len(posts) == 3, [p.title for p in posts]
    assert scanned > 0
    print("  ✓ 폴백 트리거 회귀: 선택자 부분 적중 시에도", len(posts), "건 복구")


def test_gamriwon_titles_are_matched():
    """정보통신기술사는 특급감리원 자격요건 — 감리원 공고가 누락되면 안 된다."""
    m = KeywordMatcher(KEYWORDS)
    assert m.match("본사 비상주 정보통신감리원 모집", "디에이치기술단")
    assert not m.match("건축 감리원 모집", "무관건설")   # 정보통신 맥락 없음 -> 제외
    print("  ✓ 감리원 키워드: 정보통신 맥락만 선별 채택")


def test_portal_policy_is_exclude_only():
    """회귀: 포털 검색 결과에 제목 매칭을 다시 걸면 정당한 공고가 전부 날아간다.

    run #2 실측 — 잡코리아 119건 스캔 / 0건 채택, 사람인 61건 / 0건.
    포털은 자격요건 본문까지 검색하므로 '검색 자체를 필터로 신뢰'하고
    학원 광고 등 제외 대상만 걸러야 한다.
    """
    m = KeywordMatcher(KEYWORDS)
    # 포털이 '정보통신기술사'로 찾아준 공고지만 제목엔 그 단어가 없다
    real = "통신설비 시공관리 경력직 모집"
    assert not m.match(real)            # 제목 매칭으로는 탈락 — 과거 버그의 원인
    assert not m.is_excluded(real)      # 제외 정책으로는 통과해야 정상
    # 학원 광고는 포털 결과여도 걸러야 한다
    assert m.is_excluded("정보통신기술사 대비반 수강생 모집", "OO학원")
    print("  ✓ 포털 필터 정책: 검색 신뢰 + 제외 대상만 차단")


if __name__ == "__main__":
    http.get = lambda *a, **k: FakeResponse()          # 네트워크 차단 환경용 스텁
    import src.collectors.generic_board as gb
    gb.http = http

    print("기술사 채용 다이제스트 — 파이프라인 테스트")
    test_board_collection_filters_correctly(None)
    test_date_parsing()
    test_six_month_split_and_order()
    test_dedupe_prefers_dated()
    test_html_report_renders_links_and_escapes()
    test_search_query_does_not_bypass_filter()
    test_fallback_runs_when_rows_matched_but_nothing_adopted(None)
    test_gamriwon_titles_are_matched()
    test_portal_policy_is_exclude_only()
    print("\n전체 통과 ✅")
