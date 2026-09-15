"""진입점: 수집 → 중복제거 → 정렬/분할 → 리포트 → 메일 발송."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import yaml

from . import diagnose, http, report, state
from .collectors import REGISTRY
from .collectors.work24 import SkipSource
from .filters import KeywordMatcher
from .mailer import MailConfigError, send
from .models import Posting, SourceResult

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "sources.yaml"
STATE = ROOT / "state" / "seen.json"
OUT = ROOT / "out"

log = logging.getLogger("digest")
SAMPLE_TITLES = 8   # 소스별로 로그에 남길 채택 제목 수


def collect_all(cfg: dict, matcher: KeywordMatcher) -> tuple[list[Posting], list[SourceResult]]:
    """소스별로 오류를 격리 수집한다. 한 곳이 깨져도 나머지는 발송된다."""
    postings: list[Posting] = []
    results: list[SourceResult] = []

    for source in cfg.get("sources", []):
        if not source.get("enabled", True):
            continue
        name = source.get("name", source["id"])
        collector = REGISTRY.get(source.get("type", ""))
        if collector is None:
            results.append(SourceResult(source["id"], name, False,
                                        error=f"알 수 없는 소스 타입: {source.get('type')}"))
            continue
        try:
            found, scanned = collector(source, cfg, matcher)
            postings.extend(found)
            results.append(SourceResult(source["id"], name, True,
                                        postings=found, scanned=scanned))
            log.info("[%s] %d건 수집 (%d건 스캔)", source["id"], len(found), scanned)
            # 건수만으로는 오탐을 못 잡는다. 채택된 제목을 남겨 눈으로 검증한다.
            for item in found[:SAMPLE_TITLES]:
                log.info("      · %s", item.title[:80])
            if len(found) > SAMPLE_TITLES:
                log.info("      · … 외 %d건", len(found) - SAMPLE_TITLES)
        except SkipSource as skip:
            results.append(SourceResult(source["id"], name, False, error=f"건너뜀 — {skip}"))
        except Exception as exc:  # noqa: BLE001 - 소스 장애를 리포트에 남기고 계속 진행
            log.exception("[%s] 수집 실패", source["id"])
            results.append(SourceResult(source["id"], name, False,
                                        error=f"{type(exc).__name__}: {exc}"))
    return postings, results


def dedupe(postings: list[Posting]) -> list[Posting]:
    """URL/제목 기준 중복 제거. 날짜가 있는 쪽을 살린다."""
    best: dict[str, Posting] = {}
    for post in postings:
        current = best.get(post.key)
        if current is None or (current.posted_on is None and post.posted_on is not None):
            best[post.key] = post
    return list(best.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="기술사 채용공고 일일 다이제스트")
    parser.add_argument("--dry-run", action="store_true",
                        help="메일을 보내지 않고 out/digest.html 로만 저장")
    parser.add_argument("--no-state", action="store_true",
                        help="NEW 배지 상태파일을 읽거나 쓰지 않음")
    parser.add_argument("--diagnose", metavar="SOURCE_ID",
                        help="해당 소스가 실제로 받아오는 HTML을 진단 출력하고 종료 "
                             "(all 이면 전체). 선택자·로그인 문제 파악용")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    matcher = KeywordMatcher(cfg.get("keywords", {}))
    today = date.today()

    if args.diagnose:
        targets = [s for s in cfg["sources"]
                   if args.diagnose == "all" or s["id"] == args.diagnose]
        if not targets:
            log.error("소스 '%s'를 찾을 수 없습니다. 가능한 값: %s",
                      args.diagnose, ", ".join(s["id"] for s in cfg["sources"]))
            return 1
        failed = 0
        for source in targets:
            try:
                diagnose.run(source, cfg, cfg["keywords"]["qualifications"],
                             session=http.login(source.get("login"), source["id"]))
            except Exception:  # noqa: BLE001 - 진단 도구 버그로 나머지를 못 보면 곤란하다
                log.exception("[%s] 진단 중 오류", source["id"])
                failed += 1
        return 1 if failed == len(targets) else 0

    postings, results = collect_all(cfg, matcher)
    postings = dedupe(postings)

    seen = {} if args.no_state else state.load(STATE)
    new_count = state.mark_new(postings, seen)

    recent, old = report.sort_and_split(postings, cfg.get("recency_days", 183), today)
    html_body = report.build_html(recent, old, results, new_count,
                                  cfg.get("recency_days", 183), today,
                                  sources=cfg.get("sources", []))
    text_body = report.build_text(recent, old, today, results)

    OUT.mkdir(exist_ok=True)
    (OUT / "digest.html").write_text(html_body, encoding="utf-8")
    log.info("총 %d건 (최근 %d / 참고 %d / 신규 %d)",
             len(postings), len(recent), len(old), new_count)

    log.info("요약 | %s", " / ".join(
        f"{r.source_id}:{len(r.postings) if r.ok else 'X'}" for r in results))

    ok_sources = sum(1 for r in results if r.ok)
    if ok_sources == 0:
        log.error("모든 소스 수집에 실패했습니다.")

    if args.dry_run:
        log.info("dry-run — 발송 생략. out/digest.html 확인")
        return 0

    subject = (f"[기술사 채용] {today:%m/%d} 최근 {len(recent)}건"
               + (f" · 신규 {new_count}건" if new_count else ""))
    try:
        send(subject, html_body, text_body)
    except MailConfigError as exc:
        log.error("%s", exc)
        return 2

    if not args.no_state:
        state.save(STATE, seen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
