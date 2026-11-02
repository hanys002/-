# 삼성노트 검색·클라우드·Claude 연동

삼성노트(Samsung Notes)에 쓴 내용을 **GitHub에서 읽고 검색**하고, **Google Drive/OneDrive 클라우드**와
**Claude**에서 같은 노트를 찾아볼 수 있게 하는 파이프라인입니다. 코드는 `src/samsung_notes/`,
자동 실행은 `.github/workflows/samsung-notes-sync.yml`입니다.

---

## 1. 구조와 설계 근거

```
[갤럭시 삼성노트]
   │  공유 → 파일로 저장(PDF·Word·PowerPoint·텍스트·이미지·.sdocx)
   ▼
[Google Drive 또는 OneDrive 폴더]  ←── (또는 비공개 저장소 inbox/ 에 직접 업로드)
   │  rclone copy (6시간마다 + 수동 실행)
   ▼
[GitHub Actions]  본문 추출 → OCR(손글씨 쪽) → Markdown + 검색 색인
   │  git push
   ▼
[비공개 데이터 저장소]  notes/*.md · index.json · index.html
   │
   ├─ Claude (GitHub·Google Drive 커넥터, Claude Code)  → "삼성노트에서 ○○ 찾아줘"
   ├─ GitHub 앱/웹 코드 검색
   └─ index.html 검색 페이지 · CLI(python -m src.samsung_notes search)
```

| 결정 | 근거 |
|---|---|
| **'내보내기 파일'을 입력으로 사용** | 삼성노트·Samsung Cloud는 **공개 API가 없습니다**. Microsoft OneNote/Outlook 연동은 동기화된 노트를 보여 주는 기능이며, 삼성노트 항목을 읽는 공개 문서화된 API(Microsoft Graph 포함)는 제공되지 않습니다. 기기에서 공식 지원하는 '파일로 저장' 결과만 안정적으로 자동화할 수 있습니다. |
| **PDF 내보내기 권장** | 타이핑한 글자는 PDF 텍스트 레이어로 **원문 그대로** 추출됩니다. 손글씨 쪽은 텍스트가 없어 OCR(Tesseract `kor+eng`)로 보완합니다. |
| **.sdocx는 '추정' 추출** | 삼성 비공개 포맷입니다. ZIP 내부 바이너리에서 UTF-16LE 한글·영문 문자열을 찾아내는 방식이어서 순서 뒤섞임·누락이 있을 수 있습니다. 결과에 `quality: estimated` 와 웹 화면의 **추정** 배지를 표시합니다. |
| **노트는 비공개 저장소에만 저장** | 이 저장소(`hanys002/-`)는 **공개**입니다. 공개 저장소의 커밋·Actions 로그·실행 요약·아티팩트는 외부에서 볼 수 있습니다. 그래서 노트·색인은 별도 비공개 저장소에만 커밋하고, 공개 저장소에서는 검색 결과를 로그에 출력하지 않습니다. 데이터 저장소를 지정하지 않으면 워크플로가 **실패하도록** 막아 두었습니다. |
| **해시 기반 증분 처리** | 원본 SHA-256이 같으면 다시 추출하지 않습니다. OCR이 포함된 PDF도 변경된 파일만 처리해 실행 시간을 줄입니다. |
| **형태소 분석기 없는 한국어 검색** | NFKC 정규화 부분문자열 일치 + 띄어쓰기 무시 + 끝 조사 제거(`접지저항은→접지저항`). 의존성이 없고 웹(JS)과 CLI(Python)가 **같은 결과**를 냅니다(테스트로 대조). bigram 유사도는 긴 노트에서 오탐이 많아 쓰지 않았습니다. |

### 지원 형식

| 삼성노트 내보내기 | 확장자 | 추출 방식 | 품질 |
|---|---|---|---|
| PDF | `.pdf` | 텍스트 레이어, 텍스트 없는 쪽은 OCR | 타이핑=정확, 손글씨=OCR |
| Microsoft Word | `.docx` | 문단 + 표 셀 | 정확 |
| Microsoft PowerPoint | `.pptx` | 슬라이드 텍스트(번호순) | 정확 |
| 텍스트 | `.txt` `.md` | UTF-8 → CP949 → UTF-16 순서로 판별 | 정확 |
| 이미지 | `.jpg` `.png` `.webp` … | OCR | 인쇄체 양호, 손글씨 제한 |
| 삼성노트 파일 | `.sdocx` | UTF-16LE 문자열 추정 | 추정 |
| 웹 문서 | `.html` | 본문 텍스트 | 정확 |

---

## 2. 설정 (최초 1회, 약 15분)

### 2-1. 비공개 데이터 저장소 만들기 — **필수**

1. https://github.com/new → 이름 예: `samsung-notes-data`, **Private** 선택 → *Add a README* 체크 → Create.
2. (선택) 클라우드 없이 쓰려면 이 저장소에 `inbox/` 폴더를 만들고 내보낸 파일을 올리면 됩니다.

### 2-2. 데이터 저장소 쓰기 토큰 — **필수**

1. https://github.com/settings/personal-access-tokens/new (Fine-grained token)
2. *Repository access* → **Only select repositories** → `samsung-notes-data`
3. *Permissions* → **Contents: Read and write** (그 외 불필요)
4. 만료일을 정하고 생성 → 값 복사

### 2-3. 이 저장소(`hanys002/-`)에 등록

*Settings → Secrets and variables → Actions*

| 종류 | 이름 | 값 |
|---|---|---|
| Variable | `NOTES_DATA_REPO` | `hanys002/samsung-notes-data` |
| Secret | `NOTES_DATA_TOKEN` | 2-2의 토큰 |
| Variable | `NOTES_REMOTE` | (클라우드 사용 시) 예: `gdrive:SamsungNotes` 또는 `onedrive:SamsungNotes` |
| Secret | `RCLONE_CONFIG` | (클라우드 사용 시) 2-4의 `rclone.conf` 전체 내용 |

### 2-4. 클라우드 연결 (Google Drive 또는 OneDrive)

PC에서 [rclone](https://rclone.org/downloads/)을 설치하고 한 번만 인증합니다.

```bash
rclone config
```

- `n` (새 remote) → 이름 `gdrive` → 종류 `drive`(Google Drive) 또는 `onedrive`
- `scope` 는 **`drive.readonly`**(읽기 전용) 선택 — 워크플로는 내려받기만 합니다.
- 브라우저 인증 완료 후 확인:

```bash
rclone lsf gdrive:SamsungNotes
```

```bash
rclone config file
```

위 명령이 알려주는 `rclone.conf` 파일 내용을 그대로 `RCLONE_CONFIG` 시크릿에 붙여 넣습니다.
(Google Drive 토큰은 refresh token으로 자동 갱신됩니다. OAuth 앱이 '테스트' 상태인 개인 클라이언트 ID를
쓰면 7일마다 만료되므로 rclone 기본 클라이언트 또는 '게시됨' 상태의 클라이언트를 쓰세요.)

### 2-5. 기본 브랜치에 반영

예약 실행(6시간마다)은 **기본 브랜치(main)** 의 워크플로만 동작합니다. 작업 브랜치를 main에 병합한 뒤
*Actions → 삼성노트 동기화·검색 → Run workflow* 로 첫 실행을 확인하세요.

---

## 3. 휴대폰에서 매일 쓰는 방법

1. 삼성노트에서 노트 열기 → **⋮ / 공유** → **파일로 저장** 또는 **공유 → PDF 파일**
2. 공유 대상에서 **Drive**(또는 OneDrive) → `SamsungNotes` 폴더 → 업로드
3. 최대 6시간 내 자동 반영(급하면 GitHub 앱에서 *Run workflow*)

여러 노트는 목록에서 길게 눌러 다중 선택 후 한꺼번에 PDF로 공유할 수 있습니다.
손글씨가 많은 노트는 PDF 내보내기 시 OCR로 처리되며, 정확도가 중요하면 삼성노트의
**'텍스트로 변환'**(손글씨 → 텍스트) 후 내보내는 것이 가장 정확합니다.

---

## 4. 검색하는 방법

### Claude에서 (권장)

- **claude.ai / Claude 앱**: GitHub 커넥터에서 `samsung-notes-data` 를 연결하면
  "삼성노트에서 OPC UA 관련 내용 찾아 요약해 줘"처럼 질의할 수 있습니다.
  Google Drive 커넥터가 연결되어 있으면 `SamsungNotes` 폴더의 원본 PDF도 직접 읽습니다.
- **Claude Code**: 이 저장소의 `CLAUDE.md` 에 검색 방법이 적혀 있어 다음처럼 요청하면 됩니다.
  "데이터 저장소를 클론해서 삼성노트에서 '접지저항' 찾아줘".

### 명령행 (PC)

```bash
git clone https://github.com/hanys002/samsung-notes-data.git
```

```bash
NOTES_HOME=samsung-notes-data python -m src.samsung_notes search '계측제어 "OPC UA" -초안'
```

| 문법 | 의미 | 예 |
|---|---|---|
| `단어 단어` | 모두 포함(AND) | `특화망 주파수` |
| `"구절"` | 구절 그대로 | `"OPC UA 게이트웨이"` |
| `-단어` | 제외 | `IEC -SCADA` |
| `tag:태그` | 노트 안 `#태그` | `tag:회의` |

옵션: `-n 30`(건수), `--full`(전문), `--json`(기계 처리용).

### 검색 페이지

데이터 저장소의 `index.html` 하나만 내려받아 열면 됩니다(색인 내장, 인터넷·웹서버 불필요).
모바일 화면에도 맞춰져 있고, 결과 제목을 누르면 전문이 펼쳐집니다.

### GitHub 앱/웹

비공개 저장소 안 `notes/*.md` 는 GitHub 코드 검색 대상입니다. 저장소 화면에서 `/` 를 눌러 검색합니다.

---

## 5. 운영·점검

| 증상 | 확인 |
|---|---|
| 워크플로가 즉시 실패 "공개입니다" | `NOTES_DATA_REPO` 변수 미설정. 2-3 참고 |
| `push` 403 | `NOTES_DATA_TOKEN` 권한(Contents: Read and write)·대상 저장소·만료일 |
| 클라우드 파일이 안 들어옴 | `NOTES_REMOTE` 경로 오타, `rclone lsf` 로 PC에서 먼저 확인 |
| 손글씨 노트가 검색 안 됨 | 노트 front-matter `warnings` 확인. OCR 인식 한계 → '텍스트로 변환' 후 재내보내기 |
| .sdocx 결과가 뒤죽박죽 | 비공개 포맷 한계. 같은 노트를 PDF로 내보내기 |
| 노트를 지웠는데 남아 있음 | *Run workflow* 에서 `prune` 체크(클라우드 폴더 기준으로 삭제) |

로컬 테스트(네트워크·OCR 불필요):

```bash
python tests/test_samsung_notes.py
```
