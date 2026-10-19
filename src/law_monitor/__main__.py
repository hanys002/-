from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .api import Detail, LawAPIError, LawClient, Version
from .delivery import DeliveryError, send_report
from .pipeline import collect
from .report import render, write_pdf

ROOT = Path(__file__).resolve().parents[2]


class FixtureClient:
    """명시적인 비발송 예시 모드. 실시간 조회로 표시하지 않는다."""
    def __init__(self, path: Path):
        self.data = json.loads(path.read_text(encoding="utf-8"))["laws"]

    def versions(self, name):
        if name not in self.data:
            raise LawAPIError("예시 파일에 없는 법령 — 실제 조회하지 않음")
        return [Version(**{**row["version"],
                           "announced": date.fromisoformat(row["version"]["announced"]),
                           "effective": date.fromisoformat(row["version"]["effective"])})
                for row in self.data[name]]

    def detail(self, version):
        return next(Detail(**row["detail"]) for row in self.data[version.name]
                    if row["version"]["serial"] == version.serial)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="정보통신 법령 모니터링 HTML/PDF 생성 및 Gmail 발송")
    parser.add_argument("--config", type=Path, default=ROOT / "config/laws.yaml")
    parser.add_argument("--date", type=date.fromisoformat, help="보고 기준일 YYYY-MM-DD (기본: 한국시간 오늘)")
    parser.add_argument("--output", type=Path, default=ROOT / "out/laws")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--send", action="store_true", help="설정된 수신자에게 실제 발송")
    mode.add_argument("--dry-run", action="store_true", help="파일만 생성 (기본 동작)")
    parser.add_argument("--fixture", type=Path, help="오프라인 예시 JSON; 실제 발송 불가")
    args = parser.parse_args(argv)
    if args.fixture and args.send:
        parser.error("--fixture 예시 데이터는 --send와 함께 사용할 수 없습니다")
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    laws = cfg.get("laws", [])
    if not laws or len(laws) != len(set(laws)) or not all(isinstance(n, str) and n.strip() for n in laws):
        parser.error("laws에 중복 없는 법령명 목록을 지정하세요")
    if int(cfg.get("lookback_days", 7)) < 1 or int(cfg.get("future_months", 6)) < 1:
        parser.error("조회 기간은 양수여야 합니다")
    today = args.date or datetime.now(ZoneInfo(cfg.get("timezone", "Asia/Seoul"))).date()
    if args.fixture:
        client = FixtureClient(args.fixture)
    else:
        try:
            client = LawClient(os.environ.get("LAW_API_OC", ""))
        except LawAPIError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    report = collect(client, cfg, today)
    report.demo = bool(args.fixture)
    args.output.mkdir(parents=True, exist_ok=True)
    stem = ("EXAMPLE_" if report.demo else "") + f"정보통신_법령개정_모니터링_{today}"
    html_path = args.output / f"{stem}.html"
    pdf_path = args.output / f"{stem}.pdf"
    data_path = args.output / f"{stem}.json"
    html = render(report)
    html_path.write_text(html, encoding="utf-8")
    data_path.write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    try:
        write_pdf(html, pdf_path)
    except Exception as exc:
        print(f"PDF 생성 실패 ({type(exc).__name__}): WeasyPrint·Pango·한글 글꼴 설치를 확인하세요", file=sys.stderr)
        return 2
    print(f"보고서: {pdf_path}\n목록 조회: {len(laws) - report.failures}/{len(laws)}개 법령, "
          f"기간 내 {len(report.weekly)}개 버전 / 시행 예정 {len(report.upcoming)}개 버전")
    if report.failures == len(laws):
        print("전체 법령 조회 실패 — 실패 보고서만 저장, 발송하지 않음", file=sys.stderr)
        return 2
    if args.send:
        label = "[일부 조회 미완료] " if report.incomplete else ""
        subject = f"{label}[정보통신 법령] {today} 주간 모니터링"
        try:
            send_report(cfg["recipient"], subject, html, pdf_path,
                        organization=report.organization)
        except DeliveryError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"발송 완료: {cfg['recipient']}")
    else:
        print("비발송 모드: 메일은 보내지 않았습니다")
    return 1 if report.incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
