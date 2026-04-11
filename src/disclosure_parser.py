"""
DART 단일판매·공급계약체결 공시 파서
- HTML 원문에서 구조화된 수주 데이터 추출
- 정형 필드는 HTML 파싱, 비정형 필드(선종/연료타입)는 계약명에서 추출
"""

import os
import re
import json
from pathlib import Path
from html.parser import HTMLParser

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PARSED_DIR = DATA_DIR / "parsed"


class TableExtractor(HTMLParser):
    """HTML 테이블에서 라벨-값 쌍 추출"""

    def __init__(self):
        super().__init__()
        self.cells = []
        self.current_text = ""
        self.in_td = False
        self.in_span = False

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            self.in_td = True
            self.current_text = ""
        elif tag == "span" and self.in_td:
            self.in_span = True
        elif tag == "br":
            self.current_text += "\n"

    def handle_endtag(self, tag):
        if tag == "td":
            self.cells.append(self.current_text.strip())
            self.in_td = False
            self.in_span = False
        elif tag == "span":
            self.in_span = False

    def handle_data(self, data):
        if self.in_td:
            self.current_text += data


def extract_cells(html: str) -> list[str]:
    """HTML에서 테이블 셀 텍스트 추출"""
    parser = TableExtractor()
    parser.feed(html)
    return parser.cells


def find_value(cells: list[str], *labels) -> str:
    """셀 리스트에서 라벨 다음에 오는 값을 찾기"""
    for i, cell in enumerate(cells):
        for label in labels:
            if label in cell and i + 1 < len(cells):
                val = cells[i + 1].strip()
                if val and val != "-":
                    return val
    return ""


def find_value_after_two(cells: list[str], label1: str, label2: str) -> str:
    """두 개의 라벨이 연속으로 나오고 그 다음 값을 찾기 (rowspan 구조)"""
    for i, cell in enumerate(cells):
        if label1 in cell:
            for j in range(i + 1, min(i + 5, len(cells))):
                if label2 in cells[j] and j + 1 < len(cells):
                    return cells[j + 1].strip()
    return ""


def parse_amount(text: str) -> int | None:
    """금액 문자열 → 억원 단위 정수"""
    if not text:
        return None
    # 콤마 제거
    cleaned = text.replace(",", "").replace(" ", "")
    try:
        won = int(cleaned)
        return round(won / 100_000_000)  # 원 → 억원
    except ValueError:
        return None


def parse_percentage(text: str) -> float | None:
    """퍼센트 문자열 → float"""
    if not text:
        return None
    try:
        return float(text.replace("%", "").strip())
    except ValueError:
        return None


def classify_ship_type(contract_name: str, remarks: str = "") -> str:
    """계약명에서 선종 분류"""
    text = (contract_name + " " + remarks).upper()

    patterns = {
        "LNG운반선": ["LNG", "LNGC", "LNG운반"],
        "LPG운반선": ["LPG", "LPGC", "LPG운반", "VLGC"],
        "컨테이너선": ["컨테이너", "CONTAINER"],
        "VLCC": ["VLCC", "원유운반"],
        "탱커": ["탱커", "TANKER", "PC선", "P/C선", "MR", "석유화학제품운반"],
        "벌크선": ["벌크", "BULK", "광석운반", "철광석"],
        "FPSO": ["FPSO", "FPU", "부유식"],
        "잠수함": ["잠수함", "SUBMARINE"],
        "해양플랜트": ["해양", "OFFSHORE", "플랫폼"],
        "자동차운반선": ["자동차운반", "PCTC", "PCC"],
        "암모니아운반선": ["암모니아", "AMMONIA"],
    }

    for ship_type, keywords in patterns.items():
        for kw in keywords:
            if kw in text:
                return ship_type

    return "기타"


def classify_fuel_type(contract_name: str, remarks: str = "") -> str:
    """계약명/비고에서 연료 타입 분류"""
    text = (contract_name + " " + remarks).upper()

    if any(k in text for k in ["메탄올", "METHANOL"]):
        return "메탄올이중연료"
    elif any(k in text for k in ["LNG이중", "DFDE", "이중연료", "DUAL FUEL"]):
        return "LNG이중연료"
    elif any(k in text for k in ["암모니아", "AMMONIA"]):
        return "암모니아연료"
    elif "LNG" in text and "운반" in text:
        return "LNG"  # LNG 운반선은 LNG 연료 기본
    return "기존연료"


def extract_vessel_count(contract_name: str) -> int | None:
    """계약명에서 척수 추출"""
    m = re.search(r'(\d+)\s*척', contract_name)
    if m:
        return int(m.group(1))
    return None


def parse_date_field(text: str) -> str:
    """날짜 필드 정규화 → YYYY-MM"""
    if not text or text == "-":
        return ""
    # 2026-04-02 → 2026-04
    m = re.search(r'(\d{4})-(\d{2})', text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return text


def parse_disclosure(html: str, rcept_no: str = "", rcept_dt: str = "",
                     corp_code: str = "", corp_name: str = "") -> dict:
    """공시 HTML → 구조화된 수주 데이터"""
    cells = extract_cells(html)

    # 계약명
    contract_name = find_value(cells, "체결계약명")

    # 계약금액 (원)
    amount_str = find_value_after_two(cells, "계약내역", "계약금액")
    if not amount_str:
        amount_str = find_value(cells, "계약금액(원)")
    contract_amount = parse_amount(amount_str)

    # 최근매출액
    revenue_str = find_value_after_two(cells, "계약내역", "최근매출액")
    if not revenue_str:
        revenue_str = find_value(cells, "최근매출액(원)")

    # 매출액대비(%)
    ratio_str = find_value_after_two(cells, "계약내역", "매출액대비")
    if not ratio_str:
        ratio_str = find_value(cells, "매출액대비(%)")
    revenue_ratio = parse_percentage(ratio_str)

    # 계약상대
    counterparty = find_value(cells, "계약상대")
    if not counterparty or counterparty == "-":
        counterparty = "비공개"

    # 계약기간
    start_str = find_value_after_two(cells, "계약기간", "시작일")
    end_str = find_value_after_two(cells, "계약기간", "종료일")

    # 계약(수주)일자
    order_date = find_value(cells, "계약(수주)일자", "수주일자")

    # 기타 투자판단 관련 중요사항
    remarks = find_value(cells, "기타 투자판단과 관련한 중요사항")
    if not remarks:
        # 9번 항목 이후 전체 텍스트
        for i, cell in enumerate(cells):
            if "기타 투자판단" in cell and i + 1 < len(cells):
                remarks = cells[i + 1]
                break

    # 선종/척수/연료타입 추출
    ship_type = classify_ship_type(contract_name, remarks)
    vessel_count = extract_vessel_count(contract_name)
    fuel_type = classify_fuel_type(contract_name, remarks)

    # 척당 단가 계산
    per_vessel = None
    if contract_amount and vessel_count and vessel_count > 0:
        per_vessel = round(contract_amount / vessel_count)

    return {
        "rcept_no": rcept_no,
        "corp_code": corp_code,
        "corp_name": corp_name,
        "rcept_dt": rcept_dt,
        "contract_name": contract_name,
        "contract_amount_krw": contract_amount,
        "revenue_ratio_pct": revenue_ratio,
        "ship_type": ship_type,
        "vessel_count": vessel_count,
        "per_vessel_price_krw": per_vessel,
        "counterparty": counterparty,
        "delivery_start": parse_date_field(start_str),
        "delivery_end": parse_date_field(end_str),
        "order_date": order_date,
        "fuel_type": fuel_type,
        "remarks": remarks[:500] if remarks else "",
    }


def parse_file(rcept_no: str, rcept_dt: str = "", corp_code: str = "",
               corp_name: str = "") -> dict | None:
    """저장된 HTML 파일 파싱"""
    filepath = RAW_DIR / f"{rcept_no}.html"
    if not filepath.exists():
        print(f"  파일 없음: {filepath}")
        return None

    html = filepath.read_text(encoding="utf-8")
    result = parse_disclosure(html, rcept_no, rcept_dt, corp_code, corp_name)

    # 파싱 결과 저장
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PARSED_DIR / f"{rcept_no}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def parse_all_raw() -> list[dict]:
    """data/raw/ 에 있는 모든 HTML 파싱"""
    results = []
    html_files = sorted(RAW_DIR.glob("*.html"))

    print(f"파싱 대상: {len(html_files)}건")

    for filepath in html_files:
        rcept_no = filepath.stem
        html = filepath.read_text(encoding="utf-8")
        result = parse_disclosure(html, rcept_no=rcept_no)
        results.append(result)

        # 저장
        PARSED_DIR.mkdir(parents=True, exist_ok=True)
        out_path = PARSED_DIR / f"{rcept_no}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    return results


if __name__ == "__main__":
    results = parse_all_raw()

    # 요약 출력을 파일로
    summary = []
    summary.append(f"파싱 완료: {len(results)}건\n")
    summary.append(f"{'날짜':<12} {'계약명':<30} {'금액(억)':<10} {'선종':<14} {'척수':<6} {'척당(억)':<10} {'상대방':<20}")
    summary.append("-" * 110)

    for r in results:
        amt = f"{r['contract_amount_krw']:,}" if r['contract_amount_krw'] else "?"
        pv = f"{r['per_vessel_price_krw']:,}" if r['per_vessel_price_krw'] else "-"
        vc = str(r['vessel_count']) if r['vessel_count'] else "?"
        summary.append(
            f"{r['rcept_dt'] or r['rcept_no'][:8]:<12} "
            f"{r['contract_name'][:28]:<30} "
            f"{amt:<10} "
            f"{r['ship_type']:<14} "
            f"{vc:<6} "
            f"{pv:<10} "
            f"{r['counterparty'][:18]:<20}"
        )

    output = "\n".join(summary)
    out_file = DATA_DIR / "parsed_summary.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"요약 저장: {out_file}")
