"""
재무 데이터 수집기
- DART API로 분기/연간 재무제표 수집
- yfinance로 주가 데이터 수집
"""

import os
import json
from pathlib import Path
from datetime import datetime

import OpenDartReader
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DART_API_KEY = os.getenv("DART_API_KEY")
DATA_DIR = PROJECT_ROOT / "data"

dart = OpenDartReader(DART_API_KEY)

# 종목코드 → yfinance 티커
TICKERS = {
    "329180": "329180.KS",
    "042660": "042660.KS",
    "010140": "010140.KS",
    "010620": "010620.KS",
    "082740": "082740.KS",
    "071970": "071970.KS",
}


def load_companies() -> dict:
    with open(DATA_DIR / "companies.json", "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_row(is_df, corp_code, name, year, period, quarter_label):
    """손익계산서 DataFrame에서 주요 항목 추출"""
    row = {
        "corp_code": corp_code,
        "corp_name": name,
        "year": year,
        "period": period,
        "quarter": quarter_label,
    }

    # account_nm 매칭 맵 (우선순위: 첫 매칭 사용)
    field_patterns = {
        "revenue": ["^매출액$", "^수익\\(매출액\\)$", "^영업수익$"],
        "cogs": ["^매출원가$"],
        "gross_profit": ["^매출총이익$"],
        "sga": ["^판매비와관리비$", "^판매비와 관리비$"],
        "operating_profit": ["^영업이익"],
        "net_income": ["^당기순이익"],
    }

    for field, patterns in field_patterns.items():
        for pat in patterns:
            matched = is_df[is_df["account_nm"].str.match(pat, na=False)]
            if not matched.empty:
                row[field] = parse_amount(matched.iloc[0].get("thstrm_amount", ""))
                break

    if any(k in row for k in ["revenue", "operating_profit", "net_income"]):
        return row
    return None


def _get_is_df(corp_code, year, reprt_code):
    """DART에서 손익계산서 DataFrame 가져오기 (finstate_all 우선)"""
    # finstate_all: 상세 항목 포함 (매출원가, 매출총이익, 판관비 등)
    for fs_div in ["CFS", "OFS"]:
        try:
            fs = dart.finstate_all(corp_code, year, reprt_code=reprt_code, fs_div=fs_div)
            if fs is not None and not fs.empty:
                is_df = fs[fs["sj_div"] == "IS"]
                if not is_df.empty:
                    return is_df
        except Exception:
            pass

    # fallback: finstate (요약)
    try:
        fs = dart.finstate(corp_code, year, reprt_code=reprt_code)
        if fs is None or fs.empty:
            return None
        cfs = fs[fs["fs_div"] == "CFS"]
        if cfs.empty:
            cfs = fs[fs["fs_div"] == "OFS"]
        if cfs.empty:
            return None
        is_df = cfs[cfs["sj_div"] == "IS"]
        return is_df if not is_df.empty else None
    except Exception:
        return None


def fetch_financials(corp_code: str, years: list[int] = None) -> list[dict]:
    """
    DART 연결재무제표에서 매출/영업이익/당기순이익 추출
    분기보고서(Q1~Q3)는 단독 분기값, 사업보고서(Q4)만 연간 누적이므로:
      Q1, Q2, Q3 = 각 보고서 값 그대로
      Q4 = 사업보고서(연간) - Q1 - Q2 - Q3
    """
    if years is None:
        years = list(range(2020, datetime.now().year + 1))

    companies = load_companies()
    name = companies.get(corp_code, {}).get("name", corp_code)
    metrics = ["revenue", "cogs", "gross_profit", "sga", "operating_profit", "net_income"]

    results = []

    for year in years:
        quarterly = {}
        for reprt_code, period in [("11013", "Q1"), ("11012", "Q2"), ("11014", "Q3"), ("11011", "FY")]:
            is_df = _get_is_df(corp_code, year, reprt_code)
            if is_df is not None:
                row = _extract_row(is_df, corp_code, name, year, period, f"{year}{period}")
                if row:
                    quarterly[period] = row

        # Q1, Q2, Q3: 단독 분기값 그대로 사용
        for period in ["Q1", "Q2", "Q3"]:
            if period in quarterly:
                r = quarterly[period].copy()
                r["period"] = period
                r["quarter"] = f"{year}{period}"
                results.append(r)

        # Q4 = 사업보고서(연간) - Q1 - Q2 - Q3
        # Q1~Q3가 모두 있어야 Q4 계산 가능, 없으면 건너뜀 (연간 전체가 Q4로 잡히는 문제 방지)
        if "FY" in quarterly and all(p in quarterly for p in ["Q1", "Q2", "Q3"]):
            q4 = quarterly["FY"].copy()
            q4["period"] = "Q4"
            q4["quarter"] = f"{year}Q4"
            for m in metrics:
                if m in q4 and q4[m] is not None:
                    subtotal = sum(
                        quarterly[p].get(m, 0) or 0
                        for p in ["Q1", "Q2", "Q3"]
                    )
                    q4[m] = q4[m] - subtotal
            results.append(q4)

    return results


def parse_amount(val) -> int | None:
    """DART 금액 문자열 → 억원"""
    if not val or val == "":
        return None
    try:
        cleaned = str(val).replace(",", "").replace(" ", "")
        return round(int(cleaned) / 100_000_000)
    except (ValueError, TypeError):
        return None


def fetch_stock_prices(start: str = "2020-01-01") -> pd.DataFrame:
    """전체 대상 기업 주가 수집"""
    companies = load_companies()
    all_data = []

    for code, info in companies.items():
        ticker = TICKERS.get(code, f"{code}.KS")
        name = info["name"]

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start, auto_adjust=True)

            if hist.empty:
                print(f"  {name}: 주가 데이터 없음")
                continue

            hist = hist.reset_index()
            hist["corp_code"] = code
            hist["corp_name"] = name
            hist["Date"] = hist["Date"].dt.tz_localize(None)
            all_data.append(hist[["Date", "Close", "Volume", "corp_code", "corp_name"]])
            print(f"  {name}: {len(hist)}일치 주가")

        except Exception as e:
            print(f"  {name}: 주가 수집 실패 - {e}")

    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return pd.DataFrame()


def collect_all():
    """전체 재무 + 주가 데이터 수집"""
    companies = load_companies()

    # 1. 재무 데이터
    print("=== 재무 데이터 수집 ===")
    all_financials = []
    for code in companies:
        name = companies[code]["name"]
        print(f"  {name}...")
        fins = fetch_financials(code)
        all_financials.extend(fins)
        print(f"    → {len(fins)}건")

    fin_file = DATA_DIR / "financials.json"
    with open(fin_file, "w", encoding="utf-8") as f:
        json.dump(all_financials, f, ensure_ascii=False, indent=2)
    print(f"저장: {fin_file} ({len(all_financials)}건)")

    # 2. 주가 데이터
    print("\n=== 주가 데이터 수집 ===")
    prices = fetch_stock_prices()
    if not prices.empty:
        price_file = DATA_DIR / "stock_prices.csv"
        prices.to_csv(price_file, index=False, encoding="utf-8-sig")
        print(f"저장: {price_file} ({len(prices)}행)")

    return all_financials, prices


if __name__ == "__main__":
    collect_all()
