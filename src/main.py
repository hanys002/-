"""
'기술사' 채용정보를 여러 사이트에서 모아 새로운 공고만 카카오톡(나에게 보내기)으로
전송하는 메인 스크립트.

실행: python src/main.py
(cron 등으로 주기적으로 실행하면 새 공고가 뜰 때마다 알림을 받게 된다.)
"""
import sys
import time
import traceback

import config
from kakao_sender import send_text_to_me
from scrapers.base import JobPosting
from scrapers.generic_board import scrape_board
from scrapers import saramin
from seen_store import load_seen_ids, save_seen_ids
from sites import BOARD_SITES


def collect_postings() -> list[JobPosting]:
    postings: list[JobPosting] = []

    for keyword in config.SEARCH_KEYWORDS:
        try:
            postings.extend(saramin.search(keyword, config.SARAMIN_EXTRA_QUERY))
        except Exception:
            print(f"[사람인] '{keyword}' 검색 실패:", file=sys.stderr)
            traceback.print_exc()

    for site in BOARD_SITES:
        try:
            postings.extend(
                scrape_board(site["url"], site["name"], site.get("keyword_filter"))
            )
        except Exception:
            print(f"[{site['name']}] 크롤링 실패:", file=sys.stderr)
            traceback.print_exc()

    return postings


def main() -> None:
    seen_ids = load_seen_ids()
    postings = collect_postings()

    new_postings = [p for p in postings if p.uid not in seen_ids]
    if not new_postings:
        print("새 공고 없음.")
        return

    if "--seed" in sys.argv:
        # 최초 실행 시 기존에 쌓여있던 공고를 전부 카톡으로 보내지 않고
        # '이미 확인함' 상태로만 표시해두고 싶을 때 사용.
        seen_ids.update(p.uid for p in new_postings)
        save_seen_ids(seen_ids)
        print(f"{len(new_postings)}건을 전송 없이 확인 처리했습니다.")
        return

    print(f"새 공고 {len(new_postings)}건 발견, 카카오톡 전송 시작.")
    for posting in new_postings:
        text = f"[{posting.source}] {posting.title}"
        if posting.company:
            text += f"\n{posting.company}"
        try:
            send_text_to_me(text, link_url=posting.link)
            print(f"전송 완료: {text}")
        except Exception:
            print(f"전송 실패: {text}", file=sys.stderr)
            traceback.print_exc()
            continue
        seen_ids.add(posting.uid)
        time.sleep(0.5)  # 카카오 API 과도한 연속호출 방지

    save_seen_ids(seen_ids)


if __name__ == "__main__":
    main()
