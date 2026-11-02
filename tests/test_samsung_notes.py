"""삼성노트 검색 파이프라인 테스트 (네트워크·OCR 불필요).

픽스처는 실제 삼성노트 내보내기 형식을 본뜸:
  PDF(텍스트 레이어), Word(.docx 문단+표), 텍스트(CP949, 삼성노트 기본 파일명),
  .sdocx(ZIP 안 UTF-16LE 바이너리).
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.samsung_notes import ingest as ing  # noqa: E402
from src.samsung_notes import site  # noqa: E402
from src.samsung_notes.search import search  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "samsung_notes"


def run() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        ing.ROOT, ing.NOTES_DIR = tmp, tmp / "notes"
        ing.MANIFEST, ing.INDEX = tmp / "manifest.json", tmp / "index.json"
        site.INDEX = ing.INDEX
        inbox = tmp / "inbox"
        shutil.copytree(FIX, inbox)

        st = ing.ingest([inbox], ocr=False)
        assert st["added"] == 4 and st["failed"] == 0, st
        # 증분: 두 번째 실행은 전부 건너뜀
        st2 = ing.ingest([inbox], ocr=False)
        assert st2["skipped"] == 4 and st2["added"] == 0, st2

        docs = ing.load_index()
        by_src = {d["source"]: d for d in docs}

        # 삼성노트 기본 파일명 → 첫 줄을 제목으로, CP949 디코딩
        txt = by_src["Samsung Notes_20261102_101500.txt"]
        assert txt["title"] == "기술사 2차 면접 준비", txt["title"]
        assert txt["tags"] == ["면접"]

        # .sdocx 추정 추출: 본문 문자열은 살리고 내부 식별자(a_b)는 버림
        sd = by_src["답안연습.sdocx"]
        assert "전자응용기술사 답안 구조" in sd["text"] and "IEC 61131-3" in sd["text"], sd["text"]
        assert "a_b" not in sd["text"] and sd["quality"] == "estimated"

        def titles(q):
            return [h.doc["title"] for h in search(docs, q)]

        assert titles("특화망") == ["회의록 5G 특화망"]
        assert titles("OTDR") == ["감리 체크리스트"]                 # docx 표 셀
        assert titles("4.7ghz") == ["회의록 5G 특화망"]               # 대소문자 무시
        assert titles("IEC") == sorted(titles("IEC")) and len(titles("IEC")) == 2
        assert titles("IEC -SCADA") == ["답안연습"]                   # 제외
        assert titles('"OPC UA 게이트웨이"') == ["회의록 5G 특화망"]   # 구절
        assert titles("tag:감리") == ["감리 체크리스트"]
        assert titles("특화망 감리") == []                            # AND
        assert titles("계측 제어") == ["회의록 5G 특화망"]            # 띄어쓰기 무시
        # 조사 붙은 질의: '접지저항은' → 조사 제거 후 일치
        assert titles("접지저항은") == ["감리 체크리스트"], titles("접지저항은")

        # 원본 수정 → 갱신, 원본 삭제 + prune → 노트 삭제
        (inbox / "Samsung Notes_20261102_101500.txt").write_text("기술사 2차 면접 준비\nTSN 시간동기\n", encoding="utf-8")
        (inbox / "답안연습.sdocx").unlink()
        st3 = ing.ingest([inbox], ocr=False, prune=True)
        assert st3["updated"] == 1 and st3["pruned"] == 1, st3
        docs = ing.load_index()
        assert len(docs) == 3 and titles("TSN") == ["기술사 2차 면접 준비"]

        # .pptx (삼성노트 'PowerPoint로 내보내기')
        import zipfile
        from src.samsung_notes.extract import extract
        px = tmp / "발표.pptx"
        with zipfile.ZipFile(px, "w") as z:
            for i, txt in ((2, "둘째 &amp; 마무리"), (10, "열째"), (1, "PLC 이중화")):
                z.writestr(f"ppt/slides/slide{i}.xml",
                           f'<p:sld><a:p><a:r><a:t>{txt}</a:t></a:r></a:p></p:sld>')
        ex = extract(px)
        assert ex.pages == 3 and ex.text.index("PLC") < ex.text.index("둘째 & 마무리") < ex.text.index("열째"), ex.text

        page = site.build_site(tmp / "site")
        html = page.read_text(encoding="utf-8")
        import re
        embedded = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S).group(1)
        assert json.loads(embedded)["count"] == 3 and "삼성노트 검색" in html
    finally:
        shutil.rmtree(tmp)
    print("samsung_notes: OK")


if __name__ == "__main__":
    run()
