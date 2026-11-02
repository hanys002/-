"""사용법

  python -m src.samsung_notes ingest [입력폴더 ...] [--no-ocr] [--force] [--prune]
  python -m src.samsung_notes search "검색어" [-n 20] [--json]
  python -m src.samsung_notes site [--out out/notes-site]
  python -m src.samsung_notes stats

입력폴더 기본값: samsung-notes/inbox (저장소에 직접 올린 파일)
                + $NOTES_CLOUD_DIR (Actions 가 rclone 으로 내려받은 클라우드 폴더)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .ingest import ROOT, build_index, ingest, load_index
from .search import search
from .site import build_site


def _default_inputs() -> list[Path]:
    dirs = [ROOT / "inbox"]
    if os.environ.get("NOTES_CLOUD_DIR"):
        dirs.append(Path(os.environ["NOTES_CLOUD_DIR"]))
    return dirs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="samsung_notes", description="삼성노트 검색 저장소")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ingest", help="내보내기 파일 → Markdown·색인")
    a.add_argument("inputs", nargs="*", type=Path)
    a.add_argument("--no-ocr", action="store_true")
    a.add_argument("--force", action="store_true", help="해시가 같아도 재추출")
    a.add_argument("--prune", action="store_true", help="원본이 사라진 노트 삭제")
    s = sub.add_parser("search", help="노트 검색")
    s.add_argument("query")
    s.add_argument("-n", type=int, default=20)
    s.add_argument("--json", action="store_true")
    s.add_argument("--full", action="store_true", help="전문 출력")
    w = sub.add_parser("site", help="정적 검색 페이지 생성")
    w.add_argument("--out", type=Path, default=Path("out/notes-site"))
    sub.add_parser("stats")
    sub.add_parser("reindex")
    args = ap.parse_args(argv)

    if args.cmd == "ingest":
        st = ingest(args.inputs or _default_inputs(), ocr=not args.no_ocr,
                    force=args.force, prune=args.prune)
        print(f"추가 {st['added']} · 갱신 {st['updated']} · 변경없음 {st['skipped']} · "
              f"실패 {st['failed']} · 삭제 {st['pruned']}")
        for e in st["errors"]:
            print("  !", e, file=sys.stderr)
        _summary(f"### 삼성노트 동기화\n\n| 추가 | 갱신 | 변경없음 | 실패 | 삭제 |\n|---|---|---|---|---|\n"
                 f"| {st['added']} | {st['updated']} | {st['skipped']} | {st['failed']} | {st['pruned']} |\n"
                 + "".join(f"\n- ⚠️ {e}" for e in st["errors"]))
        return 0
    if args.cmd == "reindex":
        print(f"색인 {len(build_index())}건")
        return 0
    if args.cmd == "search":
        hits = search(load_index(), args.query, args.n)
        if args.json:
            print(json.dumps([{"title": h.doc["title"], "note": f"samsung-notes/notes/{h.doc['note']}",
                               "source": h.doc["source"], "modified": h.doc["modified"],
                               "score": h.score, "snippet": h.snippet} for h in hits],
                             ensure_ascii=False, indent=1))
            return 0
        lines = [f"'{args.query}' 검색 결과 {len(hits)}건"]
        for i, h in enumerate(hits, 1):
            lines.append(f"\n{i}. {h.doc['title']}  [{h.doc['modified'][:10]}]"
                         f"  samsung-notes/notes/{h.doc['note']}")
            lines.append("   " + (h.doc["text"] if args.full else h.snippet))
        print("\n".join(lines))
        _summary("### 검색: `" + args.query + "`\n\n" + "\n".join(
            f"{i}. **{h.doc['title']}** ({h.doc['modified'][:10]}) — `samsung-notes/notes/{h.doc['note']}`"
            f"\n   > {h.snippet}" for i, h in enumerate(hits, 1)) if hits else "결과 없음")
        return 0
    if args.cmd == "site":
        print(build_site(args.out))
        return 0
    if args.cmd == "stats":
        docs = load_index()
        q = {}
        for d in docs:
            q[d["quality"]] = q.get(d["quality"], 0) + 1
        print(f"노트 {len(docs)}개 · 품질 {q}")
        return 0
    return 1


def _summary(md: str) -> None:
    """GitHub Actions 실행 요약(모바일 GitHub 앱에서도 보임)에 결과 기록."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(md + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
