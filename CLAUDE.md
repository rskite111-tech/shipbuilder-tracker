# Shipbuilder Order Tracker

## 프로젝트 목적
DART 전자공시에서 조선사의 수주 공시(단일판매·공급계약체결)를 자동 수집하고,
비정형 공시 텍스트에서 구조화된 수주 데이터를 추출하여,
수주잔고 기반 매출을 추정하고 컨센서스와 비교하는 투자 리서치 파이프라인.

## 대상 기업
| 기업 | 종목코드 | 비고 |
|------|----------|------|
| HD현대중공업 | 329180 | 주력 (대형선) |
| 한화오션 | 042660 | LNG + 방산(잠수함) |
| 삼성중공업 | 010140 | LNG + FPSO |
| HD현대미포 | 010620 | 중소형선 (PC선, MR탱커) |
| 한화엔진 | 082740 | 선박엔진 (2행정 디젤엔진) |
| HD현대마린엔진 | 071970 | 선박엔진 (HiMSEN 4행정) |
| 대한조선 | 439260 | 중소형선 (벌크선, 탱커) |

## 기술 스택
- Python 3.11+
- OpenDartReader (DART API)
- Anthropic SDK (공시 파싱)
- notion-client 또는 Notion MCP (DB 동기화)
- gspread + oauth2client (Google Sheets)
- pandas, yfinance

## 핵심 데이터 모델

### Order (수주 건)
```json
{
  "rcept_no": "20240315000XXX",
  "company": "HD현대중공업",
  "company_code": "329180",
  "disclosure_date": "2024-03-15",
  "contract_amount_krw": 16000,
  "contract_amount_usd": null,
  "ship_type": "컨테이너선",
  "vessel_count": 8,
  "per_vessel_price_krw": 2000,
  "counterparty": "비공개",
  "delivery_start": "2027-01",
  "delivery_end": "2028-06",
  "revenue_ratio_pct": 12.5,
  "fuel_type": "메탄올 이중연료",
  "remarks": ""
}
```
금액 단위: 억원 (계약금액, 척당단가 모두)

## DART API 사용 패턴

### 공시 목록 조회
```python
import OpenDartReader
dart = OpenDartReader(os.getenv('DART_API_KEY'))
filings = dart.list('329180', start='2022-01-01', kind='B')
orders = filings[filings['report_nm'].str.contains('단일판매|공급계약')]
```

### 공시 원문
```python
html = dart.document(rcept_no)  # HTML 원문 전체
sub = dart.sub_docs(rcept_no)   # 하위 문서 목록
```

### LLM 파싱 프롬프트
```
이 DART 단일판매·공급계약체결 공시 원문에서 다음을 JSON으로 추출:
- contract_amount_krw: 계약금액 (억원 단위 숫자만)
- ship_type: 선종 (LNG운반선/VLCC/컨테이너선/LPG운반선/벌크선/FPSO/잠수함/기타)
- vessel_count: 척수 (숫자만)
- counterparty: 계약상대방 (비공개면 "비공개")
- delivery_start: 인도 시작 (YYYY-MM 형식)
- delivery_end: 인도 종료 (YYYY-MM 형식)
- revenue_ratio_pct: 최근 매출액 대비 비중 (% 숫자만)
- fuel_type: 연료 타입 (LNG이중연료/메탄올이중연료/기존연료/기타)
- remarks: 특이사항

JSON만 출력. 마크다운 코드블록 없이.
```

## 매출 추정 로직 (POC)

선종별 건조 기간:
- LNG운반선: 30개월
- VLCC: 18개월
- 컨테이너선: 24개월
- LPG운반선: 20개월
- FPSO: 36개월
- 기타: 24개월 (기본값)

추정 방법:
1. 인도시기에서 건조기간만큼 역산 → 건조 시작일
2. 건조 시작일 ~ 인도일까지 S-curve로 매출 배분
3. S-curve 가중치: 초기 30% (1/3 기간) → 중반 50% (1/3 기간) → 후반 20% (1/3 기간)

## Notion DB 연동

수주 DB properties:
- 공시일(Date), 기업(Select), 선종(Select), 척수(Number)
- 계약금액_억원(Number), 척당단가_억원(Formula)
- 인도시작(Date), 인도종료(Date), 매출비중_pct(Number)
- DART링크(URL), 상대방(Rich text), 비고(Rich text)
- 연료타입(Select)

## 파일 구조
```
src/
├── dart_collector.py      # DART 공시 수집 + raw HTML 저장
├── disclosure_parser.py   # Claude API로 HTML → JSON 파싱
├── revenue_estimator.py   # 수주잔고 → 분기별 매출 추정
├── notion_sync.py         # 파싱 결과 → Notion DB
├── sheets_sync.py         # 매출 추정 → Google Sheets
data/
├── raw/{rcept_no}.html    # 공시 원문
├── parsed/{rcept_no}.json # 파싱 결과
├── companies.json         # 기업 메타
├── orders.json            # 전체 수주 통합 데이터
scripts/
├── backfill.py            # 과거 데이터 일괄 수집+파싱
├── daily_update.py        # 신규 공시 체크
├── generate_report.py     # 분석 리포트 생성
```

## 중요 주의사항
- DART API 일일 한도: 개인 10,000건 (초과 시 차단)
- rcept_no 기반 중복 체크 필수 — 이미 파싱한 건 재처리하지 않음
- 정정 공시 처리: report_nm에 '정정'이 포함되면 기존 건 업데이트
- 환율: 달러 계약은 공시 본문의 원화 환산액 사용 (별도 환율 적용 불필요)
- Claude API 파싱 비용: 건당 ~$0.01 (sonnet 기준), 전체 백필 ~$1-2

## 실행
```bash
# 초기 세팅
pip install opendartreader anthropic notion-client gspread pandas yfinance
cp .env.example .env

# 백필 (2020~현재)
python scripts/backfill.py --start 2020-01-01

# 일일 업데이트
python scripts/daily_update.py

# 매출 추정 리포트
python scripts/generate_report.py --quarter 2025Q2
```
