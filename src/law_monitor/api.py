"""국가법령정보 공동활용 DRF XML API. 조회 실패를 '변경 없음'으로 바꾸지 않는다."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

import requests

BASE = "https://www.law.go.kr/DRF/"


class LawAPIError(RuntimeError):
    pass


def normalized(value: str) -> str:
    return re.sub(r"[\sㆍ·]", "", value)


def text(node: ET.Element, path: str) -> str:
    found = node.find(path)
    return "" if found is None else "".join(found.itertext()).strip()


def parse_date(value: str) -> date | None:
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    if len(digits) != 8:
        raise LawAPIError("API 날짜 형식을 해석할 수 없습니다")
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:]))
    except ValueError as exc:
        raise LawAPIError("API 날짜가 유효하지 않습니다") from exc


@dataclass(frozen=True)
class Version:
    serial: str
    law_id: str
    name: str
    announced: date | None
    effective: date | None
    number: str
    kind: str
    amendment: str

    @property
    def url(self) -> str:
        # API에서 받은 임의 링크 대신 공식 원문 주소를 직접 만든다.
        return "https://www.law.go.kr/LSW/lsInfoP.do?" + urlencode({"lsiSeq": self.serial})


@dataclass
class Detail:
    reason: str = ""
    amendment_text: str = ""
    supplements: str = ""
    articles: dict[str, str] = field(default_factory=dict)


def blocks(root: ET.Element, path: str) -> str:
    return "\n\n".join("\n".join(part.strip() for part in item.itertext() if part.strip())
                       for item in root.findall(path))


def parse_detail(root: ET.Element) -> Detail:
    if root.tag != "법령" or root.find("기본정보") is None:
        raise LawAPIError("법령 본문 응답 구조가 예상과 다릅니다")
    articles = {}
    for item in root.findall(".//조문단위"):
        if text(item, "조문여부") == "전문":
            continue
        key = text(item, "조문번호")
        branch = text(item, "조문가지번호")
        if not key:
            continue
        label = f"제{key}조" + (f"의{branch}" if branch and branch != "0" else "")
        # Include paragraphs/subparagraphs without emitting XML metadata as prose.
        content = ["".join(el.itertext()).strip() for el in item.iter()
                   if el.tag in {"조문내용", "항내용", "호내용", "목내용"}]
        articles[label] = "\n".join(x for x in content if x)
    return Detail(
        reason=blocks(root, ".//제개정이유내용"),
        amendment_text=blocks(root, ".//개정문내용"),
        supplements=blocks(root, ".//부칙내용"),
        articles=articles,
    )


class LawClient:
    def __init__(self, oc: str, *, session=None, delay: float = 0.3):
        if not oc.strip():
            raise LawAPIError("LAW_API_OC 미설정: 공동활용 API 이용 신청 후 승인된 OC를 설정하세요")
        self.oc = oc.strip()
        self.session = session or requests.Session()
        self.delay = delay
        self.cache: dict[str, Detail] = {}

    def xml(self, endpoint: str, **params) -> ET.Element:
        params.update(OC=self.oc, type="XML", target="law")
        for attempt in range(3):
            if self.delay:
                time.sleep(self.delay)
            try:
                response = self.session.get(BASE + endpoint, params=params, timeout=(10, 45))
            except requests.RequestException:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                # requests 예외 URL에는 OC가 들어가므로 원문 예외를 출력하지 않는다.
                raise LawAPIError("법제처 연결 실패: 네트워크 허용 정책·서비스 상태 확인 필요") from None
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
            if response.status_code != 200:
                raise LawAPIError(f"법제처 HTTP {response.status_code}: 접근 권한·서비스 상태 확인 필요")
            payload = response.content
            if len(payload) > 20_000_000 or re.search(br"<!\s*(?:DOCTYPE|ENTITY)", payload, re.I):
                raise LawAPIError("허용하지 않는 XML 응답")
            try:
                root = ET.fromstring(payload)
            except ET.ParseError:
                raise LawAPIError("법제처 응답이 XML이 아닙니다: OC 승인·응답 형식 확인 필요") from None
            return root
        raise LawAPIError("법제처 요청 실패")

    def versions(self, name: str) -> list[Version]:
        versions = {}
        # 현행만 조회하면 최근 시행 후 연혁으로 이동한 버전과 시행예정을 놓친다.
        for mode in (1, 2, 3):
            consumed = 0
            page_signatures = set()
            for page in range(1, 101):
                root = self.xml("lawSearch.do", query=name, search=1, nw=mode,
                                display=100, page=page, sort="dasc")
                total_value = text(root, "totalCnt")
                if root.tag != "LawSearch" or not total_value.isdigit():
                    raise LawAPIError("법령 목록 응답 구조 오류: OC 승인·API 권한 확인 필요")
                total = int(total_value)
                rows = root.findall("law")
                if not rows and consumed < total:
                    raise LawAPIError("법령 목록 페이지가 누락되었습니다")
                signature = tuple(text(row, "법령일련번호") for row in rows)
                if rows and signature in page_signatures:
                    raise LawAPIError("법령 목록 페이지가 반복되었습니다: 전체 조회 미완료")
                page_signatures.add(signature)
                for row in rows:
                    title = text(row, "법령명한글")
                    if normalized(title) != normalized(name):
                        continue
                    serial = text(row, "법령일련번호")
                    if not serial.isdigit():
                        raise LawAPIError("법령일련번호가 유효하지 않습니다")
                    version = Version(serial, text(row, "법령ID"), title,
                                      parse_date(text(row, "공포일자")),
                                      parse_date(text(row, "시행일자")),
                                      text(row, "공포번호"), text(row, "법령구분명"),
                                      text(row, "제개정구분명"))
                    if version.announced is None or version.effective is None:
                        raise LawAPIError("공포일·시행일 누락: 변경 여부 판정 불가")
                    versions[serial] = version
                consumed += len(rows)
                if consumed >= total:
                    break
            else:
                raise LawAPIError("법령 목록 페이지 한도 초과: 전체 조회 미완료")
        if not versions:
            raise LawAPIError("정확히 일치하는 법령이 없습니다: 명칭 변경·조회 권한 확인 필요")
        return sorted(versions.values(), key=lambda v: (v.effective or date.min,
                                                       v.announced or date.min, v.serial))

    def detail(self, version: Version) -> Detail:
        if version.serial not in self.cache:
            self.cache[version.serial] = parse_detail(self.xml("lawService.do", MST=version.serial))
        return self.cache[version.serial]
