"""
사업보고서에서 공식 수주잔고 수집
- DART 사업보고서의 "매출 및 수주상황" 섹션에서 기말수주잔고 추출
- 단위: 백만원 → 억원 변환
"""

import os
import re
import json
import requests
from pathlib import Path

import OpenDartReader
from bs4 import BeautifulSoup
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DART_API_KEY = os.getenv("DART_API_KEY")
DATA_DIR = PROJECT_ROOT / "data"

dart = OpenDartReader(DART_API_KEY)


def load_companies() -> dict:
    with open(DATA_DIR / "companies.json", "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_raw_number(text: str) -> int | None:
    """테이블 셀의 숫자 문자열 → 정수 (단위 변환 없이)"""
    if not text:
        return None
    cleaned = text.replace(",", "").replace(" ", "").replace("\xa0", "")
    cleaned = cleaned.replace("(", "-").replace(")", "")
    # "315.350" 같은 천단위 구분자용 마침표 처리
    # 정수 금액이므로 소수점 아래가 3자리면 천단위 구분자로 간주
    if re.match(r"^-?\d+\.\d{3}$", cleaned):
        cleaned = cleaned.replace(".", "")
    cleaned = re.sub(r"[^\d\-.]", "", cleaned)
    if not cleaned or cleaned == "-":
        return None
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def _detect_unit(soup: BeautifulSoup, table_element) -> str:
    """수주잔고 테이블 직전의 단위 표기를 감지 (억원 / 백만원)"""
    # 테이블 앞쪽 형제/부모 요소에서 단위 찾기
    for sibling in table_element.previous_siblings:
        text = sibling.get_text(strip=True) if hasattr(sibling, "get_text") else str(sibling).strip()
        if "단위" in text:
            if "억원" in text:
                return "억원"
            if "백만원" in text:
                return "백만원"

    # 전체 페이지에서 수주잔고 테이블 이전의 마지막 단위 표기
    all_texts = []
    for elem in soup.find_all(string=True):
        t = elem.strip()
        if t:
            all_texts.append((elem, t))

    # 테이블의 첫 텍스트 위치 찾기
    table_texts = table_element.get_text(strip=True)[:30]
    found_table = False
    last_unit = "백만원"  # 기본값
    for elem, t in all_texts:
        if "단위" in t:
            if "억원" in t:
                last_unit = "억원"
            elif "백만원" in t:
                last_unit = "백만원"
        if table_texts[:15] in t:
            found_table = True
            break

    return last_unit


def _find_backlog_table(soup: BeautifulSoup) -> tuple[list[list[str]], str] | tuple[None, None]:
    """수주잔고 테이블을 찾아서 (행 리스트, 단위) 반환"""
    tables = soup.find_all("table")
    for tbl in tables:
        rows = tbl.find_all("tr")
        if len(rows) < 3:
            continue
        header_text = ""
        for row in rows[:2]:
            cells = [td.get_text(strip=True).replace("\xa0", " ")
                     for td in row.find_all(["td", "th"])]
            header_text += " ".join(cells)

        if any(k in header_text for k in ["수주잔고", "수주잔액", "수주총액"]):
            parsed_rows = []
            for row in rows:
                cells = [td.get_text(strip=True).replace("\xa0", " ")
                         for td in row.find_all(["td", "th"])]
                parsed_rows.append(cells)
            unit = _detect_unit(soup, tbl)
            return parsed_rows, unit
    return None, None


def _extract_backlog_from_table(rows: list[list[str]], unit: str) -> int | None:
    """테이블에서 합계 행의 기말수주잔고(마지막 숫자 열) 추출 → 억원"""
    total_row = None
    for row in reversed(rows):
        row_text = " ".join(row)
        if any(k in row_text for k in ["합 계", "합계", "소 계"]):
            total_row = row
            break
    if total_row is None:
        total_row = rows[-1]

    for cell in reversed(total_row):
        raw = _parse_raw_number(cell)
        if raw is not None and raw > 0:
            if unit == "백만원":
                return round(raw / 100)  # 백만원 → 억원
            else:  # 억원
                return raw
    return None


def fetch_backlog_for_report(rcept_no: str) -> int | None:
    """사업보고서 1건에서 수주잔고 추출 (억원)"""
    try:
        sub = dart.sub_docs(rcept_no)
    except Exception:
        return None

    if sub is None or sub.empty:
        return None

    # "수주" 관련 하위 문서 찾기
    target_url = None
    for _, r in sub.iterrows():
        title = str(r.get("title", ""))
        if any(k in title for k in ["수주", "매출 및 수주"]):
            target_url = r["url"]
            break

    if not target_url:
        return None

    try:
        resp = requests.get(target_url, timeout=10)
        resp.encoding = "utf-8"
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    rows, unit = _find_backlog_table(soup)
    if rows is None:
        return None

    return _extract_backlog_from_table(rows, unit)


def _extract_report_period(report_nm: str) -> tuple[int, str] | tuple[None, None]:
    """
    보고서명에서 사업연도 + 분기 추출
    '사업보고서 (2024.12)' → (2024, 'Q4')
    '분기보고서 (2024.03)' → (2024, 'Q1')
    '반기보고서 (2024.06)' → (2024, 'Q2')
    '분기보고서 (2024.09)' → (2024, 'Q3')
    """
    m = re.search(r"\((\d{4})\.(\d{2})\)", report_nm)
    if not m:
        return None, None
    year = int(m.group(1))
    month = int(m.group(2))
    quarter_map = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}
    quarter = quarter_map.get(month)
    if quarter is None:
        return None, None
    return year, quarter


def collect_all_backlogs() -> list[dict]:
    """전체 기업의 사업/분기/반기보고서에서 수주잔고 수집"""
    companies = load_companies()
    results = []

    for code, info in companies.items():
        name = info["name"]
        print(f"  {name}...")

        filings = dart.list(code, start="2019-01-01", kind="A")
        if filings is None or filings.empty:
            continue

        # 사업보고서 + 분기보고서 + 반기보고서
        reports = filings[
            filings["report_nm"].str.contains("사업보고서|분기보고서|반기보고서", na=False)
        ]
        # 최신 우선 (정정보고서가 같은 기간에 있으면 정정이 먼저 잡힘)
        reports = reports.sort_values("rcept_dt", ascending=False)

        seen_periods = set()
        for _, row in reports.iterrows():
            year, quarter = _extract_report_period(row["report_nm"])
            if year is None or quarter is None:
                continue
            period_key = f"{year}{quarter}"
            if period_key in seen_periods:
                continue
            seen_periods.add(period_key)

            backlog = fetch_backlog_for_report(row["rcept_no"])
            source = "사업보고서" if "사업" in row["report_nm"] else (
                "반기보고서" if "반기" in row["report_nm"] else "분기보고서"
            )
            if backlog is not None:
                results.append({
                    "corp_code": code,
                    "corp_name": name,
                    "year": year,
                    "quarter": period_key,
                    "backlog": backlog,
                    "rcept_no": row["rcept_no"],
                    "source": source,
                })
                print(f"    {period_key}: {backlog:,}억원 ({source})")
            else:
                print(f"    {period_key}: 추출 실패")

    # 정렬
    results.sort(key=lambda x: (x["corp_name"], x["quarter"]))

    # 저장
    out_file = DATA_DIR / "backlogs.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n저장: {out_file} ({len(results)}건)")

    return results


if __name__ == "__main__":
    collect_all_backlogs()
