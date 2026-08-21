"""
크롤링 대상 협회/단체 게시판 목록.

각 URL은 검색으로 확인한 것이며, 이 실행 환경의 네트워크 정책상 해당
사이트에 직접 접속해 실제 HTML을 확인하지는 못했다. 실행 후 해당 사이트에서
공고가 전혀 잡히지 않거나 이상한 결과가 나오면, 브라우저로 직접 접속해
게시판 URL/구조를 확인한 뒤 이 파일을 수정하면 된다.
"""

BOARD_SITES = [
    {
        "name": "한국기술사회",
        "url": "https://www.kpea.or.kr/kpea/member/OfferList.do",
        "keyword_filter": None,  # 이미 구인 전용 게시판이라 별도 필터 불필요
    },
    {
        "name": "한국정보통신기술사회(ITPE)",
        "url": "http://www.itpe.or.kr/modules/bbs/bbsList.php?code=bbs_sb0401&xid=1",
        "keyword_filter": None,
    },
    {
        "name": "한국정보통신공사협회(KICA)",
        "url": "https://www.kica.or.kr/job/hireIndex",
        "keyword_filter": None,
    },
]
