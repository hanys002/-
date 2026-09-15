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
    "role": ["기술사", "수석감리원", "특급감리원", "감리원"],
    "domain": ["정보통신", "통신설비", "계측제어", "자동제어", "계장", "전자응용"],
    "other_fields": ["건축기술사", "토목기술사", "전기기술사", "소방기술사"],
    "exclude": ["수강생", "개강", "기출문제"],
}

# 사용자 제보: 받은 메일에 보유 자격과 무관한 '기술사' 공고가 섞여 있었다.
# 아래는 그때 통과했던 실제 유형들 — 전부 탈락해야 한다.
OFF_TARGET = [
    ("토목 기술사 설계 PM 모집", "대한토목"),
    ("건축기술사 현장소장 채용", "무관건설"),
    ("전기기술사 우대 - 수배전 설계", "한빛전력"),
    ("소방기술사 감리원 모집", "안전소방"),
    ("기술사 자격 우대 엔지니어링 경력직", "종합엔지니어링"),
]

# 반대로 이건 반드시 채택돼야 한다 (보유 3종 관련)
ON_TARGET = [
    ("정보통신기술사 감리원 모집", "가나기술단"),
    ("정보통신 특급감리원 채용", "디에이치기술단"),
    ("플랜트 계장 기술사 모집", "대한엔지니어링"),
    ("전기·정보통신기술사 동시 모집", "복합기술단"),   # 타 분야 병기여도 채택
    ("자동제어 기술사 우대", "오토메이션"),
]

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
    # 카드 본문(직무·기술 태그)까지 넘기면 제목에 없는 건도 살아난다
    assert not m.match("통신설비 시공관리 경력직 모집")          # 제목만으로는 탈락
    assert m.match("통신설비 시공관리 경력직 모집",
                   "정보통신기술사 우대 · 통신설비 · 감리")       # 본문 포함 시 채택
    # 학원 광고는 본문에 자격증명이 있어도 걸러야 한다
    assert not m.match("정보통신기술사 대비반 수강생 모집", "OO학원")
    print("  ✓ 포털 필터 정책: 카드 본문까지 매칭 + 광고 차단")


def test_off_target_technical_grades_are_rejected():
    """사용자 제보 회귀: 보유 자격과 무관한 분야 기술사 공고가 섞여 나왔다."""
    m = KeywordMatcher(KEYWORDS)
    for title, company in OFF_TARGET:
        assert not m.match(title, company), f"오탐 통과: {title}"
    print("  ✓ 타 분야 기술사 배제:", len(OFF_TARGET), "유형 전부 탈락")


def test_on_target_postings_are_kept():
    """3종 자격 관련 공고는 표현이 달라도 채택돼야 한다."""
    m = KeywordMatcher(KEYWORDS)
    for title, company in ON_TARGET:
        assert m.match(title, company), f"누락: {title}"
    # 타 분야가 병기돼도 본인 자격이 명시되면 살린다
    assert m.match("전기·정보통신기술사 동시 모집") == ["정보통신기술사"]
    print("  ✓ 보유 자격 공고 채택:", len(ON_TARGET), "유형 전부 통과")


def test_portal_padding_results_are_rejected():
    """사용자 제보 회귀: 발송 메일에 무관 공고 18건이 들어갔다.

    사람인은 '정보통신기술사' 검색 일치 건이 적으면 무관한 공고로 결과를 채운다.
    '포털 검색을 필터로 신뢰한다'는 전제가 틀렸음이 실측으로 확인됐다.
    아래는 실제로 메일에 실렸던 제목들 — 전부 탈락해야 한다.
    """
    m = KeywordMatcher(KEYWORDS)
    padded = [
        "무등휴요양병원 영양실장 모집합니다.",
        "상무초밥 본사 상무프랜차이즈에서 경상&충청도 지부장 모집",
        "성균관대학교 교직원(정규직) 경력채용 공고",
        "Flutter 프론트엔드 개발자 채용",
        "백엔드 시니어 개발자 채용",
        "자동차 부품 제조업 생산(공정현장관리)/생산관리 인재 채용",
        "(주)에스제이코비스 물류 영업 지원업무 본사 직원 채용",
        "[사업기획부] 공공제안서/발표자료 작성 및 PPT디자인 업무 담당",
    ]
    for title in padded:
        assert not m.match(title), f"오탐 통과: {title}"
    print("  ✓ 포털 패딩 결과 배제:", len(padded), "건 전부 탈락")


def test_navigation_links_are_not_postings(monkeypatch_get):
    """사용자 제보 회귀: '기술사종합정보시스템'(사이트 메뉴)이 공고로 실렸다."""
    nav_html = """
    <html><body>
      <ul>
        <li><a href="/kpis">기술사종합정보시스템</a></li>
        <li><a href="/intro/greeting">정보통신 기술사회 소개</a></li>
        <li><a href="/board/view.do?id=771">정보통신기술사 감리원 모집</a></li>
      </ul>
    </body></html>"""

    class NavResponse:
        text = nav_html

    import src.collectors.generic_board as gb
    original, gb.http.get = gb.http.get, lambda *a, **k: NavResponse()
    try:
        cfg = dict(CFG, row_selector="table tbody tr")   # 미적중 → 폴백 경로
        posts, _ = board_collect(cfg, SETTINGS, KeywordMatcher(KEYWORDS))
    finally:
        gb.http.get = original

    titles = [p.title for p in posts]
    assert titles == ["정보통신기술사 감리원 모집"], titles
    print("  ✓ 네비게이션 링크 배제: 글 번호 있는 게시글만 채택")


# 실제 운영 설정(config/sources.yaml)으로 검증한다. 픽스처가 아니라 배포되는
# 설정 그 자체를 대상으로 해야 '테스트는 통과하는데 메일은 엉망'을 막을 수 있다.
# 제목은 전부 실제 수집 로그와 발송된 메일에서 가져왔다.
OBSERVED_TITLES = [
    # 감리협회 실제 공고 — 채택돼야 한다
    ("정보통신 설비 유지관리 비상주 선임자 채용", True),
    ("정보통신감리원 모집공고", True),
    ("비상주 정보통신기술자 초급, 중급, 고급, 특급 모집", True),
    ("★급★ 중급 통신 감리원 상주 모십니다.[서울시 강동구, 상주]", True),
    ("[구인]문엔지니어링(주) 감리 경력자 정보통신기술사 모집안내", True),
    # 이미 끝난 공고 — 지원할 수 없으니 제외
    ("서울, 수도권 현장 정보통신기술사 모십니다.  ****** 구인 완료 ******", False),
    ("통신(중급이상) 상주 모십니다.(안산시) *모집완료*", False),
    ("마감되었습니다.", False),
    # 초급 공고 — 기술사 보유자 대상이 아니므로 의도적으로 제외
    ("정보통신초급 채용합니다(비상근 가능)", False),
    # 협회 사이트 카테고리 메뉴
    ("기술사 활동", False),
    ("건축·토목·광업자원", False),
    ("전기·전자·정보기술", False),
    ("경영·회계·사무", False),
    # 협회 사이트 뉴스 기사
    ('2025년 2월 27일 아이티데일리 "정보공학기술사회, 제35차 정기총회 개최"', False),
    # 실제 발송 메일에 실렸던 오탐 (사람인 검색 결과 패딩)
    ("무등휴요양병원 영양실장 모집합니다.", False),
    ("상무초밥 본사 프랜차이즈 지부장 모집", False),
    ("성균관대학교 교직원(정규직) 경력채용 공고", False),
    ("Flutter 프론트엔드 개발자 채용", False),
    ("백엔드 시니어 개발자 채용", False),
    ("자동차 부품 제조업 생산(공정현장관리)/생산관리 인재 채용", False),
    ("부산 소재 공공기관 상주 근무 엔지니어 모집(중급 이상)", False),
    ("(주)유원인포텍 네트워크 스위치 영업 사원 모집", False),
    ("[경기] AV / AI ICT / 화상회의 관련 기술정규직 모집", False),
    ("써키트플렉스 F-PCB 금도금 공정 담당자 채용", False),
    # 타 분야 기술사
    ("토목 기술사 설계 PM 모집", False),
    ("건축기술사 현장소장 채용", False),
]


def test_real_config_against_observed_titles():
    """배포되는 설정으로 실측 제목 26건을 판정한다."""
    import yaml
    cfg = yaml.safe_load(
        (Path(__file__).resolve().parent.parent / "config" / "sources.yaml")
        .read_text(encoding="utf-8")
    )
    m = KeywordMatcher(cfg["keywords"])

    wrong = []
    for title, expected in OBSERVED_TITLES:
        got = bool(m.has_hiring_signal(title) and m.match(title))
        if got != expected:
            wrong.append(f"{'오탐' if got else '누락'}: {title}")
    assert not wrong, "\n      " + "\n      ".join(wrong)
    kept = sum(1 for _, e in OBSERVED_TITLES if e)
    print(f"  ✓ 운영 설정 실측 검증: {len(OBSERVED_TITLES)}건 중 "
          f"{kept}건 채택 / {len(OBSERVED_TITLES) - kept}건 배제 — 전부 일치")


def test_dedupe_key_separates_same_url_postings():
    """회귀: 상세링크가 없는 게시판 글이 전부 한 건으로 뭉개졌다(실측 83→13)."""
    board = "http://www.gamli.or.kr/base/work/work_01.php"
    posts = [
        Posting("gamli", "감리협회", "협회", "정보통신감리원 모집공고", board),
        Posting("gamli", "감리협회", "협회", "중급 통신 감리원 상주 모십니다", board),
        Posting("gamli", "감리협회", "협회", "정보통신감리원 모집공고", board),  # 진짜 중복
    ]
    assert len({p.key for p in posts}) == 2
    assert len(dedupe(posts)) == 2
    print("  ✓ 중복키 회귀: 같은 URL의 다른 글을 제목으로 구분")


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
    test_off_target_technical_grades_are_rejected()
    test_on_target_postings_are_kept()
    test_portal_padding_results_are_rejected()
    test_navigation_links_are_not_postings(None)
    test_real_config_against_observed_titles()
    test_dedupe_key_separates_same_url_postings()
    print("\n전체 통과 ✅")
