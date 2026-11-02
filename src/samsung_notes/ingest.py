"""입력 폴더 → Markdown 노트 + 검색 색인. 해시 기반 증분 처리."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .extract import SUPPORTED, extract

# 노트 데이터 위치. 공개 저장소에서는 비공개 데이터 저장소 체크아웃 경로를 NOTES_HOME 으로 준다.
ROOT = Path(os.environ.get("NOTES_HOME") or Path(__file__).resolve().parents[2] / "samsung-notes").resolve()
NOTES_DIR = ROOT / "notes"
MANIFEST = ROOT / "manifest.json"
INDEX = ROOT / "index.json"

_TAG = re.compile(r"(?<![\w&])#([0-9A-Za-z가-힣_]{1,30})")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def slugify(s: str) -> str:
    s = re.sub(r"[^\w가-힣\- ]+", "", s).strip()
    s = re.sub(r"\s+", "-", s)
    return s[:80] or "note"


def _title(path: Path, text: str) -> str:
    # 삼성노트 '파일로 저장'은 '제목_YYMMDD_HHMMSS' 로 저장한다(실측: '…주간회의260811_260818_164255.pdf').
    stem = re.sub(r"_\d{6}_\d{6}$", "", path.stem) or path.stem
    # 삼성노트 기본 파일명(예: 'Samsung Notes_20261102_101500', '노트_2026...')이면 첫 줄 사용
    if re.fullmatch(r"(samsung ?notes?|노트|note)[_ -]?[\d_ -]*", stem, re.I) or stem.isdigit():
        for line in text.splitlines():
            line = line.strip().lstrip("#").strip()
            if line and not line.startswith("<!--"):
                return line[:80]
    return stem


def _yaml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"files": {}}


def iter_inputs(dirs: list[Path]):
    for base in dirs:
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix.lower() in SUPPORTED and not p.name.startswith("."):
                yield base, p


def ingest(dirs: list[Path], ocr: bool = True, force: bool = False, prune: bool = False) -> dict:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    files: dict = manifest["files"]
    used_slugs = {v["note"] for v in files.values()}
    stats = {"added": 0, "updated": 0, "skipped": 0, "failed": 0, "pruned": 0, "errors": []}
    seen_keys: set[str] = set()

    for base, p in iter_inputs(dirs):
        key = p.relative_to(base).as_posix()
        seen_keys.add(key)
        digest = sha256(p)
        prev = files.get(key)
        if prev and prev["sha256"] == digest and not force and (NOTES_DIR / prev["note"]).exists():
            stats["skipped"] += 1
            continue
        try:
            ex = extract(p, ocr=ocr)
        except Exception as e:  # 한 파일 실패가 전체를 멈추지 않게
            stats["failed"] += 1
            stats["errors"].append(f"{key}: {e}")
            continue
        title = _title(p, ex.text)
        if prev:
            note_name = prev["note"]
        else:
            slug = slugify(title)
            note_name, n = f"{slug}.md", 2
            while note_name in used_slugs:
                note_name, n = f"{slug}-{n}.md", n + 1
            used_slugs.add(note_name)
        mtime = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        tags = sorted(set(_TAG.findall(ex.text)))
        front = [
            "---",
            f"title: {_yaml_str(title)}",
            f"source: {_yaml_str(key)}",
            f"sha256: {digest}",
            f"modified: {mtime}",
            f"method: {ex.method}",
            f"quality: {ex.quality}",
        ]
        if ex.pages:
            front.append(f"pages: {ex.pages}")
        if tags:
            front.append("tags: [" + ", ".join(_yaml_str(t) for t in tags) + "]")
        if ex.warnings:
            front.append("warnings:")
            front += [f"  - {_yaml_str(w)}" for w in ex.warnings]
        front.append("---")
        body = f"# {title}\n\n{ex.text.strip()}\n"
        (NOTES_DIR / note_name).write_text("\n".join(front) + "\n\n" + body, encoding="utf-8")
        files[key] = {"sha256": digest, "note": note_name, "title": title, "modified": mtime,
                      "quality": ex.quality, "tags": tags}
        stats["updated" if prev else "added"] += 1

    if prune:
        for key in [k for k in files if k not in seen_keys]:
            (NOTES_DIR / files[key]["note"]).unlink(missing_ok=True)
            del files[key]
            stats["pruned"] += 1

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                        encoding="utf-8")
    build_index(manifest)
    return stats


def _strip_front(md: str) -> str:
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end >= 0:
            md = md[end + 4:]
    md = re.sub(r"<!-- page \d+ -->", "", md).strip()
    return re.sub(r"\A# [^\n]*\n+", "", md)   # 색인 본문에서 제목 줄 중복 제거


def build_index(manifest: dict | None = None) -> list[dict]:
    manifest = manifest or load_manifest()
    notes = []
    for key, v in sorted(manifest["files"].items()):
        path = NOTES_DIR / v["note"]
        if not path.exists():
            continue
        notes.append({
            "title": v["title"], "note": v["note"], "source": key,
            "modified": v["modified"], "quality": v.get("quality", "exact"),
            "tags": v.get("tags", []),
            "text": _strip_front(path.read_text(encoding="utf-8")),
        })
    notes.sort(key=lambda d: d["modified"], reverse=True)
    INDEX.write_text(json.dumps({"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "count": len(notes), "notes": notes},
                                ensure_ascii=False) + "\n", encoding="utf-8")
    return notes


def load_index() -> list[dict]:
    if not INDEX.exists():
        return build_index()
    return json.loads(INDEX.read_text(encoding="utf-8"))["notes"]
