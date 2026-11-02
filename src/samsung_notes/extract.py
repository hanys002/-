"""형식별 본문 추출.

| 형식 | 방법 | 품질 |
|---|---|---|
| .pdf | pypdf 텍스트 레이어. 텍스트가 없는 쪽(손글씨·스캔)은 OCR 선택 | 타이핑 원문 = 정확 |
| .docx | python-docx 문단·표 | 정확 |
| .pptx | 슬라이드 XML 의 <a:t> 텍스트 | 정확 |
| .txt/.md | 그대로 (UTF-8 → CP949 순서로 시도) | 정확 |
| .html/.htm | BeautifulSoup 본문 텍스트 | 정확 |
| .jpg/.png 등 | tesseract OCR (kor+eng) | 손글씨는 인식률 제한 |
| .sdocx | ZIP 내부 바이너리에서 UTF-16LE 문자열 추정 추출 | 추정(best-effort) |

.sdocx 는 삼성 비공개 포맷이다. 공개 명세가 없으므로 결과를 '추정'으로 표기하고,
정확한 검색이 필요하면 삼성노트의 'PDF로 내보내기'를 권장한다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

TEXT_EXT = {".txt", ".md", ".markdown"}
HTML_EXT = {".html", ".htm"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
SUPPORTED = TEXT_EXT | HTML_EXT | IMAGE_EXT | {".pdf", ".docx", ".pptx", ".sdocx"}

# 텍스트가 이보다 적은 PDF 쪽은 손글씨/이미지로 간주해 OCR 대상으로 삼는다.
MIN_PAGE_CHARS = 10


@dataclass
class Extracted:
    text: str
    method: str
    quality: str = "exact"          # exact | ocr | estimated
    pages: int | None = None
    warnings: list[str] = field(default_factory=list)


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def _ocr_image(path: Path, lang: str) -> str:
    out = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", lang],
        capture_output=True, text=True, timeout=180,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:300])
    return out.stdout


def _read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp949", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _pdf(path: Path, ocr: bool, lang: str) -> Extracted:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts: list[str] = []
    ocr_pages: list[int] = []
    warnings: list[str] = []
    can_ocr = ocr and ocr_available() and shutil.which("pdftoppm")
    for i, page in enumerate(reader.pages, start=1):
        txt = (page.extract_text() or "").strip()
        if len(txt) < MIN_PAGE_CHARS and can_ocr:
            with tempfile.TemporaryDirectory() as tmp:
                prefix = Path(tmp) / "p"
                subprocess.run(
                    ["pdftoppm", "-r", "300", "-png", "-f", str(i), "-l", str(i),
                     str(path), str(prefix)],
                    check=True, capture_output=True, timeout=180,
                )
                imgs = sorted(Path(tmp).glob("p*.png"))
                if imgs:
                    try:
                        txt = _ocr_image(imgs[0], lang).strip()
                        ocr_pages.append(i)
                    except RuntimeError as e:
                        warnings.append(f"{i}쪽 OCR 실패: {e}")
        elif len(txt) < MIN_PAGE_CHARS:
            warnings.append(f"{i}쪽 텍스트 없음(손글씨/이미지 추정, OCR 비활성)")
        parts.append(f"<!-- page {i} -->\n{txt}")
    method = "pdf-text" + (f"+ocr(p{','.join(map(str, ocr_pages))})" if ocr_pages else "")
    return Extracted("\n\n".join(parts), method,
                     "ocr" if ocr_pages else "exact", len(reader.pages), warnings)


def _docx(path: Path) -> Extracted:
    import docx

    d = docx.Document(str(path))
    lines = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            lines.append(" | ".join(c.text.strip() for c in row.cells))
    return Extracted("\n".join(lines), "docx")


def _pptx(path: Path) -> Extracted:
    from html import unescape

    with zipfile.ZipFile(path) as zf:
        slides = sorted((n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
        parts = []
        for i, n in enumerate(slides, 1):
            xml = zf.read(n).decode("utf-8", errors="ignore")
            paras = [" ".join(unescape(t) for t in re.findall(r"<a:t>([^<]*)</a:t>", p))
                     for p in re.findall(r"<a:p>.*?</a:p>", xml, re.S)]
            parts.append(f"<!-- page {i} -->\n" + "\n".join(p for p in paras if p.strip()))
    return Extracted("\n\n".join(parts), "pptx", pages=len(slides))


def _html(path: Path) -> Extracted:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_read_text_file(path), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return Extracted(soup.get_text("\n"), "html")


# UTF-16LE: 출력 가능한 ASCII, 줄바꿈, 한글 음절(AC00–D7A3), 호환 자모(3130–318F),
# 일반 구두점(2000–206F)과 CJK 기호(3000–303F)로 이루어진 연속 구간.
_UTF16_RUN = re.compile(
    rb"(?:[\x20-\x7e]\x00|[\x0a\x0d\x09]\x00|[\x00-\xff][\xac-\xd7]"
    rb"|[\x30-\x8f]\x31|[\x00-\x6f]\x20|[\x00-\x3f]\x30){4,}"
)


def _plausible(s: str) -> bool:
    s = s.strip()
    if len(s) < 2:
        return False
    hangul = sum(1 for c in s if "가" <= c <= "힣")
    alpha = sum(1 for c in s if c.isalnum())
    if hangul >= 2:
        return True
    # 영문/숫자만인 구간은 내부 식별자(키·경로·UUID)가 많아 엄격히 거른다.
    return alpha >= 6 and " " in s and not re.search(r"[{}<>\\/=_]", s)


def _sdocx(path: Path) -> Extracted:
    seen: set[str] = set()
    out: list[str] = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            name = info.filename.lower()
            if name.startswith("media/") or name.endswith((".jpg", ".png", ".jpeg", ".webp")):
                continue
            data = zf.read(info)
            for m in _UTF16_RUN.finditer(data):
                start = m.start()
                chunk = data[start: m.end() - ((m.end() - start) % 2)]
                s = chunk.decode("utf-16-le", errors="ignore").replace("\r", "\n").strip()
                if _plausible(s) and s not in seen:
                    seen.add(s)
                    out.append(s)
    return Extracted("\n".join(out), "sdocx-utf16-scan", "estimated",
                     warnings=["sdocx 비공개 포맷: 본문을 추정 추출함. 정확도가 필요하면 PDF로 내보내기 권장"])


def extract(path: Path, ocr: bool = True, lang: str = "kor+eng") -> Extracted:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _pdf(path, ocr, lang)
    if ext == ".docx":
        return _docx(path)
    if ext == ".pptx":
        return _pptx(path)
    if ext in TEXT_EXT:
        return Extracted(_read_text_file(path), "text")
    if ext in HTML_EXT:
        return _html(path)
    if ext == ".sdocx":
        return _sdocx(path)
    if ext in IMAGE_EXT:
        if not (ocr and ocr_available()):
            return Extracted("", "image", "ocr", warnings=["이미지: OCR 비활성(tesseract 없음)"])
        return Extracted(_ocr_image(path, lang), "image-ocr", "ocr")
    raise ValueError(f"지원하지 않는 형식: {ext}")
