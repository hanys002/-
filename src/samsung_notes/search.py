"""한국어 친화 전문 검색.

형태소 분석기 없이 동작하도록 **NFKC 정규화 부분문자열 일치**를 기본으로 하고,
일치하지 않을 때만 두 가지 완화 규칙을 쓴다.
  1) 띄어쓰기 무시   '계측 제어' ↔ '계측제어'
  2) 끝 조사 제거    '접지저항은' → '접지저항'
부분문자열 방식이라 '계측제어' 로 '산업계측제어기술사는' 도 찾는다(접두·접미 무관).
문자 bigram 유사도는 긴 노트에서 흩어진 bigram 이 우연히 겹쳐 오탐이 커서 쓰지 않는다.

질의 문법
  단어 단어      모든 단어 포함(AND)
  "구절 그대로"  구절 일치
  -단어          제외
  tag:태그       front-matter 태그 필터
같은 규칙을 site.py 의 JavaScript 에도 그대로 구현해 웹과 CLI 결과가 같다.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"\s+", " ", s)


# 긴 것부터 검사해야 '에서' 가 '서' 보다 먼저 떨어진다.
JOSA = ("에서는", "으로는", "에게서", "이라고", "에서", "에게", "으로", "까지", "부터", "처럼",
        "보다", "이나", "은", "는", "이", "가", "을", "를", "에", "의", "와", "과", "로", "도", "만", "나")


def strip_josa(term: str) -> str:
    for j in JOSA:
        if term.endswith(j) and len(term) - len(j) >= 2:
            return term[: -len(j)]
    return term


def _nospace(s: str) -> str:
    return s.replace(" ", "")


@dataclass
class Query:
    include: list[str]
    phrases: list[str]
    exclude: list[str]
    tags: list[str]


def parse_query(q: str) -> Query:
    phrases = [normalize(p) for p in re.findall(r'"([^"]+)"', q)]
    rest = re.sub(r'"[^"]*"', " ", q).split()
    inc, exc, tags = [], [], []
    for t in rest:
        if t.startswith("-") and len(t) > 1:
            exc.append(normalize(t[1:]))
        elif t.lower().startswith("tag:") and len(t) > 4:
            tags.append(normalize(t[4:]))
        else:
            inc.append(normalize(t))
    return Query(inc, phrases, exc, tags)


@dataclass
class Hit:
    doc: dict
    score: float
    snippet: str


def _snippet(text: str, terms: list[str], width: int = 60) -> str:
    low = normalize(text)
    flat = re.sub(r"\s+", " ", text)
    for t in terms:
        i = low.find(t)
        if i >= 0:
            a, b = max(0, i - width), min(len(flat), i + len(t) + width)
            return ("…" if a else "") + flat[a:b].strip() + ("…" if b < len(flat) else "")
    return flat[: width * 2].strip()


def search(docs: list[dict], q: str, limit: int = 20) -> list[Hit]:
    """docs: index.json 의 notes 배열 (title, text, tags …)."""
    query = parse_query(q)
    must = query.include + query.phrases
    hits: list[Hit] = []
    for d in docs:
        title = normalize(d.get("title", ""))
        body = normalize(d.get("text", ""))
        hay = title + " " + body
        hay_ns = None
        tags = [normalize(t) for t in d.get("tags", [])]
        if any(t not in tags for t in query.tags):
            continue
        if any(e in hay for e in query.exclude):
            continue
        score = 0.0
        ok = True
        for term in must:
            if term in hay:
                score += 10 + 5 * (term in title) + min(hay.count(term), 10)
            else:
                hay_ns = hay_ns if hay_ns is not None else _nospace(hay)
                if _nospace(term) in hay_ns or _nospace(strip_josa(term)) in hay_ns:
                    score += 6
                else:
                    ok = False
                    break
        if not ok or (not must and not query.tags):
            continue
        hits.append(Hit(d, score, _snippet(d.get("text", ""), must + [strip_josa(t) for t in must])))
    hits.sort(key=lambda h: h.doc.get("modified", ""), reverse=True)   # 동점이면 최신 우선
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]
