"""삼성노트(Samsung Notes) 내보내기 파일 → 검색 가능한 Markdown 노트 저장소.

삼성노트는 공개 API가 없다. 따라서 '내보내기(PDF·Word·텍스트·이미지)'
또는 원본 .sdocx 를 클라우드 폴더/저장소에 두면, 이 모듈이 본문을 추출해
`samsung-notes/notes/*.md` 와 검색 색인 `samsung-notes/index.json` 을 만든다.
"""
