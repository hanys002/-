# 기술사 채용공고 데일리 브리핑

**정보통신기술사 · 산업계측제어기술사 · 전자응용기술사** 채용공고를 매일 **09:00(KST)** 에
수집해 Gmail로 발송하는 자동화 파이프라인.

---

## 1. 동작 개요

```
GitHub Actions (cron 0 0 * * * UTC = 09:00 KST)
        │
        ├─ 협회 게시판 6곳  ─┐
        ├─ 사람인 (API/HTML) ├─→ 키워드 필터 → 중복제거 → 최신순 정렬
        ├─ 잡코리아          │                              │
        └─ 고용24 공공 API  ─┘                    ┌─────────┴─────────┐
                                              최근 6개월 이내      6개월 초과
                                                (본문 상단)      (하단 '참고')
                                                       └────┬────┘
                                                     HTML 메일 → Gmail SMTP
```

### 설계 근거

| 결정 | 근거 |
|---|---|
| GitHub Actions에서 실행 | 국내 채용 사이트는 해외 클라우드/프록시에서 403을 주는 경우가 많음. Actions 러너는 egress 제한이 없고 무료(퍼블릭) 또는 월 2,000분(프라이빗) 내에서 충분 |
| 소스별 오류 격리 | 한 사이트가 개편·차단돼도 나머지는 정상 발송. 실패 소스는 메일 하단 **수집 소스 상태**에 그대로 표기 |
| 선택자 YAML 분리 + 폴백 | 협회 게시판은 개편이 잦음. `config/sources.yaml`만 고치면 되고, 선택자가 완전히 빗나가면 전체 `<a>` 스캔 폴백으로 전환 |
| 공식 API 우선 | 사람인·고용24는 오픈 API 제공. 키가 있으면 API, 없으면 HTML 폴백 (`robots.txt`·이용약관 준수 범위 내 저빈도 1일 1회 조회) |
| 상태파일(`state/seen.json`) | 처음 보는 공고에만 **NEW** 배지. 매일 같은 공고를 다시 읽는 피로 제거 |

---

## 2. 수집 소스

| ID | 기관 | URL |
|---|---|---|
| `kpea` | 한국기술사회 | https://www.kpea.or.kr/kpea/member/OfferList.do |
| `itpe` | 한국정보통신기술사회 | https://www.itpe.or.kr/ |
| `pesk` | 대한기술사회 | https://pesk.or.kr/?pg_idx=145 |
| `kica` | 한국정보통신공사협회 | https://www.kica.or.kr/job/hireIndex |
| `etis` | 한국엔지니어링협회(ETIS) | https://www.etis.or.kr/jobGuinList.do |
| `kacem` | 한국건설엔지니어링협회 | http://www.ekacem.or.kr/openspace/job_offerring_li.asp |
| `saramin` | 사람인 | https://www.saramin.co.kr/ |
| `jobkorea` | 잡코리아 | https://www.jobkorea.co.kr/ |
| `work24` | 고용24(워크넷) | https://www.work24.go.kr/ |

---

## 3. 설정 (최초 1회, 약 5분)

### 3-1. Gmail 앱 비밀번호 발급 — **필수**

Google은 2022년 5월부터 일반 비밀번호를 통한 SMTP 인증을 폐지했습니다. 앱 비밀번호가 필요합니다.

1. https://myaccount.google.com/security → **2단계 인증**을 먼저 켭니다.
2. https://myaccount.google.com/apppasswords 접속
3. 앱 이름에 `job-digest` 입력 → **만들기**
4. 표시되는 **16자리 문자열**을 복사 (공백은 무시됨, 창을 닫으면 다시 못 봅니다)

### 3-2. 리포지터리 시크릿 등록 — **필수**

`Settings → Secrets and variables → Actions → New repository secret`

| 이름 | 값 |
|---|---|
| `GMAIL_USER` | `hanys002@gmail.com` |
| `GMAIL_APP_PASSWORD` | 위에서 받은 16자리 앱 비밀번호 |

> 다른 주소로 받으려면 `Variables` 탭에 `MAIL_TO`를 추가하세요. 없으면 `GMAIL_USER`로 발송됩니다.

### 3-3. 오픈 API 키 등록 — 선택 (권장)

키가 없어도 HTML 폴백으로 동작하지만, 있으면 수집 안정성과 정확도가 크게 올라갑니다.

| 시크릿 | 발급처 |
|---|---|
| `SARAMIN_API_KEY` | https://oapi.saramin.co.kr/ (무료, 승인 즉시) |
| `WORK24_API_KEY` | https://www.data.go.kr/ → '채용정보' 활용신청 (무료) |

### 3-4. 예약 실행 활성화 — **중요**

> GitHub Actions의 `schedule` 트리거는 **기본 브랜치(main)에 있는 워크플로만** 동작합니다.
> 작업 브랜치에 머물러 있으면 예약 실행이 되지 않으니, 반드시 `main`에 병합하세요.

병합 후 `Actions` 탭 → **기술사 채용공고 데일리 메일** → `Run workflow`로 즉시 1회 테스트하는 것을 권장합니다.

---

## 4. 로컬 실행

```bash
pip install -r requirements.txt

# 메일 없이 리포트만 생성 → out/digest.html
python -m src.main --dry-run

# 실제 발송
export GMAIL_USER=hanys002@gmail.com
export GMAIL_APP_PASSWORD='xxxxxxxxxxxxxxxx'
python -m src.main

# 테스트 (네트워크 불필요)
python tests/test_pipeline.py
```

---

## 5. 튜닝

`config/sources.yaml` 한 곳에서 조정합니다.

```yaml
recency_days: 183     # '최근' 기준일. 넘으면 하단 '참고' 섹션으로

keywords:
  qualifications:     # 이 자격증명이 직접 적힌 공고만 채택
    - 정보통신기술사
    - 전자응용기술사
    - 산업계측제어기술사
  hiring_signals:     # 게시판 목록에서 메뉴·뉴스를 걸러내는 채용 신호어
  exclude:            # 학원 광고·마감 공고
```

### 선별 기준을 자격증명 단독으로 둔 이유

초기에는 직무·등급 표현(`감리원`·`선임자`·`중급/고급/특급`·`기술자`)을
분야 한정어와 조합해 채택했습니다. 이 방식은 **기술사를 요구하지 않는 자리를
대량으로 통과**시킵니다. `정보통신감리원 모집`은 감리원 등급만 있으면 되는
자리이지 기술사 공고가 아닙니다. 실제로 이 방식으로 보낸 메일은 요양병원
영양실장·프랜차이즈 지부장까지 포함됐습니다.

따라서 **자격증명이 제목이나 본문에 직접 적힌 공고만** 채택합니다.
`normalize()`가 공백·특수문자를 지우므로 `정보통신 기술사`, `[정보통신기술사]`
같은 표기 차이는 자동으로 흡수됩니다.

**트레이드오프**: 자격증명을 제목에 쓰지 않은 공고는 놓칩니다. 감리협회처럼
상세 열람에 로그인이 필요한 게시판은 본문을 볼 수 없어 더 그렇습니다.
오탐 없는 쪽을 택한 결과이며, 메일 하단 *소스 바로가기*로 목록을 직접 확인할
수 있습니다.

**대상 자격을 늘리려면** `qualifications`에 추가하면 됩니다
(예: `정보공학기술사`). 직무·등급 표현은 추가하지 마십시오 — 위의 문제가
그대로 재발합니다.

## 6. 유지보수

메일 하단 **수집 소스 상태**가 진단 창구입니다.

| 증상 | 조치 |
|---|---|
| 특정 소스 `실패 — HTTPError: 404` | 사이트 개편. `config/sources.yaml`의 `url` 갱신 |
| `정상 — 0건 스캔` | 선택자 미적중. `row_selector`/`title_selector` 수정 |
| `정상 — N건 스캔 / 0건 적합` | 정상 동작이나 키워드 미매칭. `keywords` 확장 검토 |
| `건너뜀 — WORK24_API_KEY 미설정` | 3-3의 키 등록 (선택) |
| 메일이 아예 안 옴 | `Actions` 탭에서 실행 로그 확인. 앱 비밀번호 만료가 가장 흔함 |

JS 렌더링 기반으로 개편된 사이트는 정적 파싱이 불가합니다. 이 경우 해당 소스를
`enabled: false`로 내리고 Playwright 수집기를 추가하는 것이 정석입니다.

---

## 7. 소스별 실측 현황 (2026-09-15 진단 기준)

메일 하단 *수집 소스 상태*가 항상 최신 값을 보여줍니다. 아래는 `--diagnose`로
러너가 실제 받아온 HTML을 확인한 결과입니다.

| 소스 | 상태 | 근거 |
|---|---|---|
| 한국기술사회 | ✅ 동작 | 표 형식 게시판. `row_board`로 해결. **로그인 불필요** |
| 정보통신감리협회 | ✅ 동작 | 237건 스캔. 상세 링크는 로그인 필요 |
| 건설엔지니어링협회 | ✅ 정상 | 22행 파싱됨. 건설 분야라 3종 자격 공고 없음 |
| 사람인·잡코리아 | ✅ 동작 | 검색 + 상세 본문 확인(verify_detail) |
| 정보통신기술사회 | 🔧 미해결 | 메뉴가 전부 `javascript:menu()`. 게시판은 `/modules/bbs/` |
| 대한기술사회 | ⚠️ 미해결 | `<title>구인구직` 맞지만 `table=0`. 게시글이 AJAX |
| 인크루트 | ⚠️ 불안정 | `job.incruit.com` ConnectTimeout 발생 |
| 워크넷 | ⏸ 대기 | `WORK24_API_KEY` 미설정 |

### 다음에 할 일

1. **ITPE 구인 게시판 코드 특정**
   게시판 모듈 주소는 확인됐다: `https://itpe.or.kr/modules/bbs/bbsView.php?code=bbs_sb0407&xid=7`
   목록은 `bbsList.php?code=bbs_sbNNNN` 형태로 추정된다. 아래로 후보를 확인한다.

   ```
   Actions → Run workflow → probe 칸에 쉼표로 나열
   https://itpe.or.kr/modules/bbs/bbsList.php?code=bbs_sb0701,
   https://itpe.or.kr/modules/bbs/bbsList.php?code=bbs_sb0702,
   https://itpe.or.kr/modules/bbs/bbsList.php?code=bbs_sb0407&xid=7
   ```
   자격증명이 발견되는 코드를 찾으면 `config/sources.yaml`의 itpe url을 교체한다.

2. **대한기술사회 AJAX 엔드포인트 발굴**
   게시판 스크립트가 `/ahebf/board/` 아래에 있다(폼 action이 `./ahebf/board/_down.php`).
   목록 엔드포인트를 찾거나, 안 되면 Playwright 수집기를 도입한다.

3. **인크루트 호스트 교체** — `job.incruit.com` → `m.incruit.com` 확인

4. **워크넷 인증키 등록** (선택, 권장)
   전 산업을 포괄해 플랜트·계장 분야까지 들어온다. 세 자격 중 산업계측제어·
   전자응용기술사를 잡는 데 가장 유효한 소스다.
   발급: https://www.data.go.kr/data/3038225/openapi.do → `WORK24_API_KEY` 시크릿

### 등록이 필요한 시크릿

| 시크릿 | 필요성 |
|---|---|
| `GMAIL_USER`, `GMAIL_APP_PASSWORD` | ✅ 등록 완료 |
| `GAMLI_ID`, `GAMLI_PW` | 권장 — 감리협회 상세 링크가 살아난다 |
| `WORK24_API_KEY` | 권장 — 수집 범위가 가장 크게 넓어진다 |
| `KPEA_ID`, `KPEA_PW` | **불필요** (진단으로 확인) |

### 진단 도구 사용법

개발 환경에서 국내 사이트에 접속할 수 없어 선택자를 실물로 검증할 수 없다.
추측으로 고치면 오탐·누락이 반복되므로, 러너가 받아온 HTML을 직접 본다.

```
Actions → Run workflow
  diagnose : 소스 id (쉼표 구분, all 가능)   예) kpea,itpe
  probe    : 임의 URL (쉼표 구분)             예) https://…/bbsList.php?code=…
```

출력: HTTP 상태·최종 URL·인코딩·`<title>`, 로그인 폼 필드명, 구조 통계,
**자격증명이 HTML에 실제로 있는지**(주변 문맥 포함), 링크 상위 25개.
본문이 2000바이트 미만이면 원문을 그대로 출력한다.
