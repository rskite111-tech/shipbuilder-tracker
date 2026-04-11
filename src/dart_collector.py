"""
DART 공시 수집기
- 조선사 단일판매·공급계약체결 공시 목록 조회
- 공시 원문 HTML 다운로드 및 저장
"""

import os
import json
from pathlib import Path
from datetime import datetime

import OpenDartReader
from dotenv import load_dotenv

# 프로젝트 루트 기준 .env 로드
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DART_API_KEY = os.getenv("DART_API_KEY")
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
COMPANIES_FILE = DATA_DIR / "companies.json"

dart = OpenDartReader(DART_API_KEY)


def load_companies() -> dict:
    with open(COMPANIES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_order_filings(corp_code: str, start: str, end: str = None) -> list[dict]:
    """
    특정 기업의 단일판매·공급계약 공시 목록 조회

    Args:
        corp_code: 종목코드 (예: '329180')
        start: 시작일 (YYYY-MM-DD)
        end: 종료일 (기본: 오늘)

    Returns:
        수주 관련 공시 리스트 (dict)
    """
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")

    # kind 없이 전체 공시에서 필터 (단일판매공급계약은 kind='B'에 안 잡히는 경우 있음)
    filings = dart.list(corp_code, start=start, end=end)

    if filings is None or filings.empty:
        print(f"  공시 없음: {corp_code} ({start} ~ {end})")
        return []

    # '단일판매' 또는 '공급계약' 포함 건만 필터
    mask = filings['report_nm'].str.contains('단일판매|공급계약', na=False)
    orders = filings[mask].copy()

    if orders.empty:
        print(f"  수주 공시 없음: {corp_code} ({start} ~ {end}), 전체 공시 {len(filings)}건")
        return []

    results = []
    for _, row in orders.iterrows():
        results.append({
            "rcept_no": row["rcept_no"],
            "corp_code": corp_code,
            "corp_name": row.get("corp_name", ""),
            "report_nm": row["report_nm"],
            "rcept_dt": row["rcept_dt"],
            "flr_nm": row.get("flr_nm", ""),
        })

    return results


def download_document(rcept_no: str) -> str | None:
    """
    공시 원문 HTML 다운로드 및 저장

    Returns:
        저장된 파일 경로 (이미 존재하면 스킵)
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    filepath = RAW_DIR / f"{rcept_no}.html"

    if filepath.exists():
        return str(filepath)

    try:
        html = dart.document(rcept_no)
        if html:
            filepath.write_text(html, encoding="utf-8")
            return str(filepath)
        else:
            print(f"  원문 비어있음: {rcept_no}")
            return None
    except Exception as e:
        print(f"  원문 다운로드 실패: {rcept_no} - {e}")
        return None


def collect_company(corp_code: str, start: str, end: str = None, download: bool = False):
    """기업 하나의 수주 공시 수집"""
    companies = load_companies()
    name = companies.get(corp_code, {}).get("name", corp_code)

    print(f"\n{'='*60}")
    print(f"[{name}] ({corp_code}) 수주 공시 수집: {start} ~ {end or '현재'}")
    print(f"{'='*60}")

    filings = fetch_order_filings(corp_code, start, end)
    print(f"  → 수주 공시 {len(filings)}건 발견")

    for i, f in enumerate(filings, 1):
        print(f"  {i:3d}. [{f['rcept_dt']}] {f['report_nm']}")
        print(f"       접수번호: {f['rcept_no']}")

        if download:
            path = download_document(f["rcept_no"])
            if path:
                print(f"       원문 저장: {path}")

    return filings


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DART 조선 수주 공시 수집")
    parser.add_argument("--company", default="329180", help="종목코드 (기본: HD현대중공업)")
    parser.add_argument("--start", default="2020-01-01", help="시작일")
    parser.add_argument("--end", default=None, help="종료일 (기본: 오늘)")
    parser.add_argument("--download", action="store_true", help="원문 HTML 다운로드")
    parser.add_argument("--all", action="store_true", help="전체 대상 기업")
    args = parser.parse_args()

    if args.all:
        companies = load_companies()
        all_filings = []
        for code in companies:
            filings = collect_company(code, args.start, args.end, args.download)
            all_filings.extend(filings)
        print(f"\n총 {len(all_filings)}건")
    else:
        collect_company(args.company, args.start, args.end, args.download)
