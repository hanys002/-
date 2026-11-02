# Claude 작업 안내

## 삼성노트 검색 (`src/samsung_notes`)

사용자가 "삼성노트에서 ○○ 찾아줘/요약해줘"라고 하면:

1. 노트 데이터는 이 공개 저장소가 아니라 **비공개 저장소 `hanys002/samsung-notes-data`** 에 있다.
   세션에 없으면 `add_repo` 로 붙여 클론한다. (이 저장소의 `samsung-notes/` 는 비어 있는 것이 정상)
2. 검색:
   ```bash
   NOTES_HOME=<데이터 저장소 경로> python -m src.samsung_notes search "검색어" --json
   ```
   문법: 공백=AND, `"구절"`, `-제외`, `tag:태그`. 결과의 `note` 경로(`notes/*.md`)를 읽어 답한다.
3. front-matter 의 `quality` 가 `ocr`(손글씨 인식)·`estimated`(.sdocx 추정)이면 원문과 다를 수 있다고 밝힌다.
4. 원본 PDF가 필요하면 Google Drive 커넥터로 「5. 삼성 노트」 폴더를 찾는다(`source` 필드가 파일명).
5. 노트 내용을 이 **공개** 저장소에 커밋하거나 공개 Artifact·이슈·PR 본문에 옮기지 않는다.

설정·운영: `docs/samsung-notes.md` · 테스트: `python tests/test_samsung_notes.py`
