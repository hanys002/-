"""수집기·필터·리포트 파이프라인 단위 테스트 (네트워크 불필요).

여기 등장하는 제목은 대부분 실제 수집 로그와 발송된 메일에서 가져왔다.
건수만 보고 판단하다 오탐을 반복해서 놓쳤기 때문에, 실측 제목을 그대로
고정해 두고 배포 설정으로 판정한다.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import http  # noqa: E402
from src.collectors.generic_board import collect as board_collect  # noqa: E402
from src.collectors.portal_search import collect as portal_collect  # noqa: E402
from src.filters import KeywordMatcher, parse_date  # noqa: E402
from src.main import dedupe  # noqa: E402
from src.models import Posting  # noqa: E402
from src.report import build_html, sort_and_split  # noqa: E402

TODAY = date(2026, 9, 15)
ROOT = Path(__file__).resolve().parent.parent

# 배포되는 설정 그 자체로 검증한다. 픽스처가 실제 설정보다 느슨하면
# '테스트는 통과하는데 메일은 엉망'이 된다.
CONFIG = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
KEYWORDS = CONFIG["keywords"]

BOARD_HTML = """
<html><body><table><tbody>
  <tr><td>1</td><td><a href="/view.do?id=101">정보통신기술사 모집 (상주)</a></td>
      <td>주식회사 가나기술단</td><td>2026-09-12</td></tr>
  <tr><td>2</td><td><a href="/view.do?id=102">산업계측제어기술사 채용 - 플랜트 계장설계</a></td>
      <td>대한엔지니어링</td><td>2026.09.01</td></tr>
  <tr><td>3</td><td><a href="/view.do?id=103">정보통신기술사 대비반 수강생 모집</a></td>
      <td>OO학원</td><td>2026-09-14</td></tr>
  <tr><td>4</td><td><a href="/view.do?id=104">정보통신감리원 모집공고</a></td>
      <td>무관기술단</td><td>2026-09-13</td></tr>
  <tr><td>5</td><td><a href="/view.do?id=105">전자응용기술사 우대 - 반도체 계측장비 채용</a></td>
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


def with_html(html: str):
    """http.get을 고정 응답으로 바꾸는 컨텍스트."""
    class Resp:
        text = html

    import src.collectors.generic_board as gb

    class Patch:
        def __enter__(self):
            self.original = gb.http.get
            gb.http.get = lambda *a, **k: Resp()

        def __exit__(self, *exc):
            gb.http.get = self.original

    return Patch()


# ─────────────────────────────────────────────────────────────────────
# 선별 기준 — 자격증명이 직접 적힌 공고만 채택한다
# ─────────────────────────────────────────────────────────────────────

# 실제 발송 메일과 수집 로그에서 가져온 제목. (제목, 채택되어야 하는가)
OBSERVED = [
    # ── 채택: 보유 자격증명이 직접 적혀 있다 ──
    ("정보통신 기술사 모십니다 (인천지역)", True),          # 띄어쓰기 표기
    ("정보통신 기술사 모십니다.(인천현장)", True),
    ("[구인]문엔지니어링(주) 감리 경력자 정보통신기술사 모집안내", True),
    ("전자응용기술사 우대 - 반도체 계측장비 채용", True),
    ("산업계측제어기술사 채용 - 플랜트 계장설계", True),

    # ── 탈락: 직무·등급 표현뿐이고 자격증명이 없다 ──
    # 정보통신감리원은 기술사를 요구하지 않는 자리다. 이 유형을 채택하던 것이
    # 이전 메일이 자격과 무관한 공고로 채워진 직접 원인이었다.
    ("정보통신감리원 모집공고", False),
    ("정보통신감리원 모집(인천광역시)", False),
    ("정보통신감리원 모십니다.(고급이상, 상주)", False),
    ("정보통신감리원(고급이상_ 비상주감리원 구인합니다.", False),
    ("[정보통신] 특급 감리원 모집 (최고대우/ 2026년 7월 투입 예정)", False),
    ("★급★ 중급 통신 감리원 상주 모십니다.[서울시 강동구, 상주]", False),
    ("통신 책임 상주감리원 모집합니다(세종시)", False),
    ("정보통신 설비 유지관리 비상주 선임자 채용", False),
    ("비상주 정보통신기술자 초급, 중급, 고급, 특급 모집", False),   # 기술'자'
    ("정보통신 중급 비상주 모십니다.", False),
    ("글로벌 건설사업관리(CM) 전문기업 [데이타센터 통신기술자]", False),

    # ── 탈락: 이미 끝난 공고 ──
    ("서울, 수도권 현장 정보통신기술사 모십니다.  ****** 구인 완료 ******", False),
    ("정보통신기술사 모십니다(안산시) *모집완료*", False),
    ("비상주 정보통신기술사 모십니다(대전) - 모집하였습니다", False),
    ("마감되었습니다.", False),

    # ── 탈락: 협회 사이트 카테고리 메뉴 ──
    ("기술사 활동", False),
    ("건축·토목·광업자원", False),
    ("전기·전자·정보기술", False),
    ("경영·회계·사무", False),
    ("기술사종합정보시스템", False),

    # ── 탈락: 협회 뉴스 기사 ──
    ('2025년 2월 27일 아이티데일리 "정보공학기술사회, 제35차 정기총회 개최"', False),

    # ── 탈락: 포털 검색 결과 패딩 (실제 발송 메일에 실렸던 오탐) ──
    ("무등휴요양병원 영양실장 모집합니다.", False),
    ("상무초밥 본사 프랜차이즈 지부장 모집", False),
    ("성균관대학교 교직원(정규직) 경력채용 공고", False),
    ("Flutter 프론트엔드 개발자 채용", False),
    ("백엔드 시니어 개발자 채용", False),
    ("자동차 부품 제조업 생산(공정현장관리)/생산관리 인재 채용", False),
    ("부산 소재 공공기관 상주 근무 엔지니어 모집(중급 이상)", False),
    ("(주)유원인포텍 네트워크 스위치 영업 사원 모집", False),
    ("써키트플렉스 F-PCB 금도금 공정 담당자 채용", False),

    # ── 탈락: 타 분야 기술사 ──
    ("토목 기술사 설계 PM 모집", False),
    ("건축기술사 현장소장 채용", False),
    ("전기기술사 우대 - 수배전 설계", False),
    ("소방기술사 감리원 모집", False),

    # ── 탈락: 학원 광고 ──
    ("정보통신기술사 대비반 수강생 모집", False),
]


def test_only_qualifications_are_matched():
    """배포 설정으로 실측 제목을 판정한다. 자격증명이 있는 건만 채택."""
    m = KeywordMatcher(KEYWORDS)
    wrong = [
        f"{'오탐' if bool(m.has_hiring_signal(t) and m.match(t)) else '누락'}: {t}"
        for t, expected in OBSERVED
        if bool(m.has_hiring_signal(t) and m.match(t)) != expected
    ]
    assert not wrong, "\n      " + "\n      ".join(wrong)
    kept = sum(1 for _, e in OBSERVED if e)
    print(f"  ✓ 자격증명 단독 판정: {len(OBSERVED)}건 중 "
          f"{kept}건 채택 / {len(OBSERVED) - kept}건 배제 — 전부 일치")


def test_spacing_variants_match():
    """'정보통신 기술사'처럼 띄어 쓴 표기도 같은 자격으로 본다."""
    m = KeywordMatcher(KEYWORDS)
    for variant in ["정보통신기술사 모집", "정보통신 기술사 모십니다",
                    "[정보통신기술사] 채용", "전자응용 기술사 구합니다",
                    "산업계측제어 기술사 채용"]:
        assert m.match(variant), variant
    print("  ✓ 표기 변형: 공백·괄호 무관하게 매칭")


def test_all_three_qualifications_configured():
    """설정에 세 자격이 모두 있어야 한다. 하나라도 빠지면 조용히 누락된다."""
    assert set(KEYWORDS["qualifications"]) == {
        "정보통신기술사", "전자응용기술사", "산업계측제어기술사",
    }, KEYWORDS["qualifications"]
    print("  ✓ 대상 자격 3종 설정 확인")


# ─────────────────────────────────────────────────────────────────────
# 수집기
# ─────────────────────────────────────────────────────────────────────

def test_board_collection():
    with with_html(BOARD_HTML):
        posts, scanned = board_collect(CFG, SETTINGS, KeywordMatcher(KEYWORDS))
    titles = [p.title for p in posts]
    assert scanned == 5
    assert titles == [
        "정보통신기술사 모집 (상주)",
        "산업계측제어기술사 채용 - 플랜트 계장설계",
        "전자응용기술사 우대 - 반도체 계측장비 채용",
    ], titles
    assert posts[0].url == "https://example.or.kr/view.do?id=101"
    assert posts[0].posted_on == date(2026, 9, 12)
    print("  ✓ 게시판 수집:", len(posts), "건 채택 (학원광고·감리원 공고 제외)")


def test_navigation_and_news_are_not_postings():
    """회귀: 사이트 메뉴('기술사종합정보시스템')가 공고로 실렸다."""
    html = """
    <html><body><ul>
      <li><a href="/kpis">기술사종합정보시스템</a></li>
      <li><a href="/intro">정보통신기술사회 소개</a></li>
      <li><a href="/board/view.do?id=771">정보통신기술사 모집</a></li>
    </ul></body></html>"""
    with with_html(html):
        posts, _ = board_collect(dict(CFG, row_selector="table tbody tr"),
                                 SETTINGS, KeywordMatcher(KEYWORDS))
    assert [p.title for p in posts] == ["정보통신기술사 모집"], [p.title for p in posts]
    print("  ✓ 메뉴·소개 링크 배제: 게시글만 채택")


def test_unusable_links_fall_back_to_board_url():
    """회귀: 클릭해도 열리지 않는 javascript: 링크가 메일에 실렸다.

    감리협회는 비회원 상세 열람을 막아
    href가 javascript:alert("게시판 읽기 권한이 없습니다.")로 나온다.
    """
    html = """
    <html><body><table><tbody>
      <tr><td><a href='javascript:alert("게시판 읽기 권한이 없습니다.")'>정보통신기술사 모십니다</a></td><td>2026-06-16</td></tr>
      <tr><td><a href="/board/view.do?id=88">산업계측제어기술사 모집합니다</a></td><td>2026-06-18</td></tr>
    </tbody></table></body></html>"""
    with with_html(html):
        posts, _ = board_collect(CFG, SETTINGS, KeywordMatcher(KEYWORDS))

    assert len(posts) == 2, [p.title for p in posts]
    assert not any(p.url.startswith("javascript:") for p in posts)
    fallback = [p for p in posts if p.link_is_list]
    assert len(fallback) == 1 and fallback[0].url == CFG["url"]
    normal = [p for p in posts if not p.link_is_list][0]
    assert normal.url == "https://example.or.kr/board/view.do?id=88"
    print("  ✓ 사용불가 링크: 목록 URL로 대체 + 안내 플래그")


# ─────────────────────────────────────────────────────────────────────
# 날짜·정렬·중복
# ─────────────────────────────────────────────────────────────────────

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
        assert parse_date(text, today=TODAY) == expected, text
    print("  ✓ 날짜 파싱:", len(cases), "케이스 통과")


def test_six_month_split_and_order():
    posts = [
        Posting("s", "n", "o", "오래된", "u1", date(2025, 1, 5)),
        Posting("s", "n", "o", "최신", "u2", date(2026, 9, 14)),
        Posting("s", "n", "o", "중간", "u3", date(2026, 6, 1)),
        Posting("s", "n", "o", "날짜미상", "u4", None),
        Posting("s", "n", "o", "경계 직전", "u5", TODAY - timedelta(days=182)),
        Posting("s", "n", "o", "경계 직후", "u6", TODAY - timedelta(days=184)),
    ]
    recent, old = sort_and_split(posts, 183, today=TODAY)
    assert [p.url for p in recent] == ["u2", "u3", "u5", "u4"]
    assert [p.url for p in old] == ["u6", "u1"]
    print("  ✓ 최신순 정렬 + 6개월 분할: 최근", len(recent), "/ 참고", len(old))


def test_dedupe_key_separates_same_url_postings():
    """회귀: 상세링크 없는 게시판 글이 전부 한 건으로 뭉개졌다(실측 83→13)."""
    board = "http://www.gamli.or.kr/base/work/work_01.php"
    posts = [
        Posting("g", "감리협회", "협회", "정보통신기술사 모집", board),
        Posting("g", "감리협회", "협회", "산업계측제어기술사 모집", board),
        Posting("g", "감리협회", "협회", "정보통신기술사 모집", board),   # 진짜 중복
    ]
    assert len({p.key for p in posts}) == 2
    assert len(dedupe(posts)) == 2
    print("  ✓ 중복키: 같은 URL의 다른 글을 제목으로 구분")


def test_dedupe_prefers_dated():
    posts = [
        Posting("a", "A", "O", "같은 공고", "https://x/1", None),
        Posting("b", "B", "O", "같은 공고", "https://x/1", date(2026, 9, 10)),
    ]
    merged = dedupe(posts)
    assert len(merged) == 1 and merged[0].posted_on == date(2026, 9, 10)
    print("  ✓ 중복 제거: 날짜 있는 레코드 우선")


def test_html_report_renders_links_and_escapes():
    posts = [Posting("s", "테스트", "협회", 'XSS <script> & "따옴표" 정보통신기술사',
                     "https://example.or.kr/a?b=1&c=2", date(2026, 9, 14), is_new=True)]
    recent, old = sort_and_split(posts, 183, today=TODAY)
    html = build_html(recent, old, [], 1, 183, TODAY)
    assert 'href="https://example.or.kr/a?b=1&amp;c=2"' in html
    assert "<script>" not in html
    assert "NEW" in html and "2026-09-14" in html
    print("  ✓ HTML 리포트: 링크/이스케이프/NEW 배지 정상")


PORTAL_CFG = {
    "id": "testportal", "name": "테스트포털", "org": "포털",
    "search_url": "https://portal.example/search", "base": "https://portal.example",
    "query_param": "kw", "detail_hints": ["rec_idx="], "max_items": 20,
    "queries": ["정보통신기술사"],
}

PORTAL_HTML = """
<html><body>
  <div class="item_recruit">
    <a href="/jobs/view?rec_idx=111">정보통신기술사 감리 경력자 채용</a>
    <span class="corp_name"><a>가나기술단</a></span><span class="date">2026-09-10</span>
  </div>
  <div class="item_recruit">
    <a href="/jobs/view?rec_idx=222">무등휴요양병원 영양실장 모집합니다.</a>
    <span class="corp_name"><a>무등휴요양병원</a></span>
  </div>
  <div class="item_recruit">
    <a href="/jobs/view?rec_idx=111">정보통신기술사 감리 경력자 채용</a>
  </div>
  <a href="/company/intro">회사소개</a>
</body></html>"""


def test_portal_search_filters_padding():
    """포털은 일치 건이 적으면 무관 공고로 결과를 채운다 — 자격증명으로만 채택."""
    class Resp:
        text = PORTAL_HTML

    import src.collectors.portal_search as ps
    original, ps.http.get = ps.http.get, lambda *a, **k: Resp()
    try:
        posts, scanned = portal_collect(PORTAL_CFG, SETTINGS, KeywordMatcher(KEYWORDS))
    finally:
        ps.http.get = original

    assert scanned == 2, scanned                       # rec_idx 중복·회사소개 제외
    assert [p.title for p in posts] == ["정보통신기술사 감리 경력자 채용"]
    assert posts[0].url == "https://portal.example/jobs/view?rec_idx=111"
    assert posts[0].company == "가나기술단"
    assert posts[0].posted_on == date(2026, 9, 10)
    print("  ✓ 포털 검색: 패딩 공고 배제 + rec_idx 중복 제거")


def test_every_source_has_a_registered_collector():
    """설정에 타입 오타가 나면 조용히 소스가 빠진다 — 발송 전에 잡는다."""
    from src.collectors import REGISTRY
    unknown = [
        f"{src['id']}({src.get('type')})"
        for src in CONFIG["sources"]
        if src.get("type") not in REGISTRY
    ]
    assert not unknown, unknown
    print(f"  ✓ 소스 {len(CONFIG['sources'])}곳 전부 등록된 수집기 사용")


def test_portal_queries_cover_all_qualifications():
    """포털에 세 자격을 모두 던져야 한다. 하나라도 빠지면 그 자격은 안 걸린다."""
    quals = set(KEYWORDS["qualifications"])
    for src in CONFIG["sources"]:
        if src.get("type") in ("portal_search", "work24"):
            assert set(src["queries"]) == quals, f"{src['id']}: {src['queries']}"
    print("  ✓ 포털·API 검색어가 자격 3종을 모두 포함")


def test_detail_verification_catches_body_only_mentions():
    """자격증명이 제목엔 없고 상세 우대사항에만 있는 공고를 잡아낸다.

    실측 근거: 사람인 계측제어 직종 337건 중 제목에 '산업계측제어기술사'를
    쓴 공고는 0건이었다. 목록만 봐서는 이 자격들을 잡을 수 없다.
    동시에 검색 패딩(본문에도 자격증명이 없는 무관 공고)은 걸러져야 한다.
    """
    search_html = """
    <html><body>
      <div class="item_recruit"><a href="/jobs/view?rec_idx=301">플랜트 계장설계 경력직 채용</a></div>
      <div class="item_recruit"><a href="/jobs/view?rec_idx=302">무등휴요양병원 영양실장 모집합니다.</a></div>
    </body></html>"""
    details = {
        # 제목엔 없지만 우대사항에 자격증명이 있다 → 채택돼야 한다
        "https://portal.example/jobs/view?rec_idx=301":
            "<html><body><h1>플랜트 계장설계</h1>"
            "<p>우대사항: 산업계측제어기술사 또는 전자응용기술사 보유자</p></body></html>",
        # 검색 패딩 — 본문에도 자격증명이 없다 → 탈락해야 한다
        "https://portal.example/jobs/view?rec_idx=302":
            "<html><body><p>급식 영양관리 업무. 영양사 면허 필수.</p></body></html>",
    }

    calls = []

    class Resp:
        def __init__(self, text):
            self.text = text

    def fake_get(url, **kwargs):
        calls.append(url)
        return Resp(details.get(url, search_html))

    cfg = dict(PORTAL_CFG, verify_detail=True, max_detail_fetch=10)
    import src.collectors.portal_search as ps
    original, ps.http.get = ps.http.get, fake_get
    try:
        posts, scanned = portal_collect(cfg, SETTINGS, KeywordMatcher(KEYWORDS))
    finally:
        ps.http.get = original

    assert scanned == 2, scanned
    assert [p.title for p in posts] == ["플랜트 계장설계 경력직 채용"], [p.title for p in posts]
    assert set(posts[0].matched) == {"산업계측제어기술사", "전자응용기술사"}, posts[0].matched
    assert len(calls) == 3, calls        # 검색 1회 + 상세 2회
    print("  ✓ 상세 확인: 우대사항에만 있는 자격증명 채택 / 패딩 공고 배제")


def test_detail_fetch_budget_is_respected():
    """상세 조회는 상한이 있어야 한다. 없으면 실행시간과 차단 위험이 커진다."""
    links = "".join(
        f'<div class="item_recruit"><a href="/jobs/view?rec_idx={i}">무관한 공고 제목 {i}</a></div>'
        for i in range(30)
    )
    calls = []

    class Resp:
        text = f"<html><body>{links}</body></html>"

    def fake_get(url, **kwargs):
        calls.append(url)
        return Resp()

    cfg = dict(PORTAL_CFG, verify_detail=True, max_detail_fetch=5)
    import src.collectors.portal_search as ps
    original, ps.http.get = ps.http.get, fake_get
    try:
        posts, _ = portal_collect(cfg, SETTINGS, KeywordMatcher(KEYWORDS))
    finally:
        ps.http.get = original

    assert posts == []
    assert len(calls) == 6, len(calls)   # 검색 1회 + 상세 5회(상한)
    print("  ✓ 상세 조회 상한: 30건 후보 중 5건만 조회")


def test_recency_window_is_one_year():
    assert CONFIG["recency_days"] == 365, CONFIG["recency_days"]
    print("  ✓ 수집 범위: 최근 1년")


def test_login_credentials_are_never_in_config():
    """자격정보는 설정 파일이 아니라 환경변수(=시크릿)에서만 읽어야 한다."""
    raw = (ROOT / "config" / "sources.yaml").read_text(encoding="utf-8")
    for src in CONFIG["sources"]:
        login = src.get("login")
        if not login:
            continue
        assert "id_env" in login and "pw_env" in login, src["id"]
        # 값을 직접 적는 키가 있으면 안 된다
        assert "id" not in login and "pw" not in login, src["id"]
        assert "password" not in login, src["id"]
    # 흔한 실수: 평문 비밀번호가 설정에 섞여 들어가는 것
    assert "password:" not in raw.lower(), "설정에 평문 비밀번호로 보이는 키가 있습니다"
    print("  ✓ 로그인 자격정보: 설정 파일에 평문 없음 (시크릿 참조만)")


if __name__ == "__main__":
    print("기술사 채용 다이제스트 — 파이프라인 테스트\n")
    test_all_three_qualifications_configured()
    test_only_qualifications_are_matched()
    test_spacing_variants_match()
    test_board_collection()
    test_portal_search_filters_padding()
    test_detail_verification_catches_body_only_mentions()
    test_detail_fetch_budget_is_respected()
    test_every_source_has_a_registered_collector()
    test_recency_window_is_one_year()
    test_login_credentials_are_never_in_config()
    test_portal_queries_cover_all_qualifications()
    test_navigation_and_news_are_not_postings()
    test_unusable_links_fall_back_to_board_url()
    test_date_parsing()
    test_six_month_split_and_order()
    test_dedupe_key_separates_same_url_postings()
    test_dedupe_prefers_dated()
    test_html_report_renders_links_and_escapes()
    print("\n전체 통과 ✅")
