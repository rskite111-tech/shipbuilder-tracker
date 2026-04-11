# 조선 수주 트래커 — Claude Code 프로젝트

## 프로젝트 개요

DART 공시(단일판매·공급계약체결)를 자동 수집·파싱하여 조선사별 수주 데이터를 구조화하고,
수주잔고 기반 매출 추정 → 컨센서스 비교까지 자동화하는 투자 리서치 파이프라인.

**대상 기업:**
- HD현대중공업 (329180, 구 현대중공업 009540)
- 한화오션 (042660)
- 삼성중공업 (010140)
- HD한국조선해양 (009540) — 지주사
- HD현대미포 (010620) — 중소형선

---

## 시스템 아키텍처

```
[DART OpenAPI] ──→ [수집 스크립트] ──→ [LLM 파싱] ──→ [구조화 DB]
                         │                                    │
                    공시목록 조회              계약금액/선종/척수/인도시기
                    원문 다운로드              상대방/매출액 대비 비중
                         │                                    │
                         ▼                                    ▼
                [Raw HTML/XML 저장]          [Notion DB] + [Google Sheets]
                   (Obsidian vault)                           │
                                                              ▼
                                              [매출 인식 추정 엔진]
                                                    │
                                                    ▼
                                        [컨센서스 비교 대시보드]
```

---

## 디렉토리 구조

```
shipbuilder-tracker/
├── CLAUDE.md                    # Claude Code 지시 파일
├── .env                         # API 키 (DART_API_KEY, ANTHROPIC_API_KEY)
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── dart_collector.py        # DART 공시 수집
│   ├── disclosure_parser.py     # 공시 원문 파싱 (LLM 기반)
│   ├── revenue_estimator.py     # POC 기반 매출 추정
│   ├── consensus_comparator.py  # 컨센서스 비교
│   ├── notion_sync.py           # Notion DB 동기화
│   └── sheets_sync.py           # Google Sheets 동기화
├── data/
│   ├── raw/                     # DART 원문 HTML
│   ├── parsed/                  # 파싱된 JSON
│   └── companies.json           # 기업 메타정보 (종목코드, DART 고유번호)
├── scripts/
│   ├── backfill.py              # 과거 수주 데이터 일괄 수집
│   ├── daily_update.py          # 일일 신규 공시 체크
│   └── generate_report.py       # 분석 리포트 생성
└── tests/
    └── test_parser.py
```

---

## CLAUDE.md (Claude Code에 넣을 파일)

```markdown
# Shipbuilder Order Tracker

## 프로젝트 목적
DART 전자공시에서 조선사(HD현대중공업, 한화오션, 삼성중공업 등)의 
수주 공시(단일판매·공급계약체결)를 자동 수집하고, 비정형 공시 텍스트에서
구조화된 수주 데이터를 추출하여, 수주잔고 기반 매출을 추정하는 시스템.

## 기술 스택
- Python 3.11+
- OpenDartReader (DART API wrapper)
- Anthropic SDK (공시 파싱용)
- Notion API (MCP 또는 notion-client)
- gspread (Google Sheets)
- pandas, json

## 핵심 데이터 모델

### Order (수주 건)
```json
{
  "disclosure_id": "20240315000XXX",
  "company": "HD현대중공업",
  "company_code": "329180",
  "disclosure_date": "2024-03-15",
  "contract_amount_krw": 1600000000000,
  "contract_amount_usd": null,
  "ship_type": "컨테이너선",
  "vessel_count": 8,
  "per_vessel_price_krw": 200000000000,
  "counterparty": "비공개 (유럽 선사)",
  "delivery_start": "2027-01",
  "delivery_end": "2028-06",
  "revenue_ratio": 12.5,
  "remarks": "메탄올 이중연료 추진"
}
```

## DART API 사용법

### 1. 공시 목록 조회
```python
import OpenDartReader
dart = OpenDartReader(os.getenv('DART_API_KEY'))

# 주요사항보고서(kind='B')만 필터
filings = dart.list('329180', start='2022-01-01', kind='B')
# '단일판매' 포함 건만 추출
orders = filings[filings['report_nm'].str.contains('단일판매|공급계약')]
```

### 2. 공시 원문 가져오기
```python
# rcept_no로 원문 HTML 조회
html = dart.document(rcept_no)
# 또는 sub_docs로 세부 문서 접근
sub = dart.sub_docs(rcept_no)
```

### 3. LLM 파싱 프롬프트
공시 원문 HTML을 Claude에 넘겨서 구조화:
```
이 DART 단일판매·공급계약체결 공시에서 다음 정보를 추출해주세요:
- 계약금액 (원화, 가능하면 USD)
- 선종 (LNG운반선, VLCC, 컨테이너선, LPG운반선, 벌크선, FPSO 등)
- 척수
- 계약상대방 (공개된 경우)
- 인도 예정 시기 (시작~종료)
- 최근 매출액 대비 비중 (%)
- 비고 (이중연료, 특수 사양 등)
JSON으로만 응답하세요.
```

## 매출 추정 로직

### POC(진행기준) 매출 인식
조선은 건조 진행률에 따라 매출을 인식한다.
- 통상 건조 기간: 인도 18~30개월 전부터
- 강재 절단(steel cutting) → 블록 조립 → 도크 탑재 → 진수 → 인도
- 간이 추정: 인도시점에서 24개월 역산하여 균등 인식

```python
def estimate_revenue_recognition(order):
    delivery_start = parse_date(order['delivery_start'])
    construction_start = delivery_start - timedelta(months=24)
    total_months = 24 + delivery_spread_months
    monthly_revenue = order['contract_amount_krw'] / total_months
    # 월별 매출 배분 리턴
```

### 고도화 옵션
- 실제 공정률 반영 (S-curve: 초기 느림 → 중반 빠름 → 후반 느림)
- 선종별 건조 기간 차등 적용 (LNG 30개월, VLCC 18개월, 컨테이너 24개월)
- 환율 가정 (USD 계약 → KRW 매출 전환)

## Notion DB 스키마

### 수주 DB (Orders)
| Property | Type | 설명 |
|----------|------|------|
| 공시일 | Date | DART 공시일 |
| 기업 | Select | HD현대중공업/한화오션/삼성중공업 |
| 선종 | Select | LNG/VLCC/컨테이너/LPG/기타 |
| 척수 | Number | |
| 계약금액(억원) | Number | |
| 척당단가(억원) | Number | formula |
| 인도시작 | Date | |
| 인도종료 | Date | |
| 매출비중(%) | Number | |
| DART링크 | URL | 원문 링크 |
| 상대방 | Text | |
| 비고 | Text | |

### 매출추정 DB (Revenue Estimates)
| Property | Type | 설명 |
|----------|------|------|
| 분기 | Title | 2025Q1 등 |
| 기업 | Select | |
| 추정매출(억원) | Number | 수주잔고 기반 |
| 컨센서스(억원) | Number | FnGuide 등 |
| 괴리율(%) | Formula | |
| 수주잔고(억원) | Number | 해당 시점 잔고 |

## 실행 커맨드

### 초기 세팅
```bash
pip install opendartreader anthropic notion-client gspread pandas
cp .env.example .env  # API 키 입력
```

### 과거 데이터 백필
```bash
python scripts/backfill.py --company 329180 --start 2020-01-01
python scripts/backfill.py --company 042660 --start 2020-01-01
python scripts/backfill.py --company 010140 --start 2020-01-01
```

### 일일 업데이트
```bash
python scripts/daily_update.py  # 신규 공시 체크 + 파싱 + Notion 동기화
```

### 리포트 생성
```bash
python scripts/generate_report.py --quarter 2025Q2
```

## 주의사항
- DART API 일일 호출 한도: 개인 10,000건
- 공시 원문 파싱 시 Claude API 비용 발생 (건당 ~$0.01)
- rcept_no가 유니크 키 — 중복 수집 방지 필수
- 환율은 공시일 기준 매매기준율 적용
```

---

## 구현 순서 (Claude Code에서)

### Phase 1: 데이터 수집 (1일)
1. `.env` 세팅 (DART_API_KEY)
2. `companies.json` 작성 (종목코드 → DART 고유번호 매핑)
3. `dart_collector.py` 구현 — 공시 목록 조회 + 원문 다운로드
4. `backfill.py`로 2020년부터 과거 데이터 수집

### Phase 2: 파싱 엔진 (1일)
1. `disclosure_parser.py` — Claude API로 비정형 공시 → 구조화 JSON
2. 파싱 결과 `data/parsed/` 에 저장
3. 파싱 정확도 검증 (수동으로 5~10건 크로스체크)

### Phase 3: 분석 엔진 (1일)
1. `revenue_estimator.py` — 수주잔고 → 분기별 매출 추정
2. 선종별 건조 기간 파라미터 테이블
3. S-curve 가중치 적용

### Phase 4: 외부 연동 (1일)
1. `notion_sync.py` — Notion MCP로 수주 DB 자동 적재
2. `sheets_sync.py` — Google Sheets에 매출 추정 테이블 동기화
3. `daily_update.py` — 크론/스케줄러 연동

### Phase 5: 고도화 (ongoing)
1. 컨센서스 자동 수집 (FnGuide 스크래핑 or 수동 입력)
2. 신조선가 implied price 추이 자동 계산
3. 주가 데이터 연동 (yfinance) → 상관성 대시보드
4. 알림 시스템 (신규 수주 공시 → 카카오톡/텔레그램)

---

## Claude Code 세션 시작 시 프롬프트 예시

```
이 프로젝트는 DART 공시에서 조선사 수주 데이터를 자동 수집하는 시스템이야.
CLAUDE.md 읽고, Phase 1부터 시작하자.
먼저 .env 파일 만들고, dart_collector.py를 구현해줘.
HD현대중공업(329180)의 2022년부터 '단일판매공급계약' 공시를 조회하는 것부터.
```

---

## 확장 가능성

이 파이프라인은 조선뿐 아니라 **모든 수주산업**에 적용 가능:
- **방산** (한화에어로스페이스, LIG넥스원) — 방위산업 공급계약
- **건설** (현대건설, 대우건설) — 도급공사 수주
- **전력기기** (HD현대일렉트릭) — 변압기/차단기 공급계약
- **플랜트** (삼성엔지니어링) — EPC 계약

`companies.json`에 기업만 추가하면 동일 파이프라인으로 확장됨.
