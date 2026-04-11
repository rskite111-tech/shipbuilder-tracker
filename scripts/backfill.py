"""
과거 수주 데이터 일괄 수집 + 파싱
- 전체 대상 기업의 2020년~현재 수주공시 수집
- HTML 원문 다운로드
- 구조화 JSON 파싱
- 통합 orders.json 생성
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dart_collector import collect_company, load_companies, fetch_order_filings, download_document
from disclosure_parser import parse_file, PARSED_DIR, DATA_DIR


def backfill(start: str, company: str = None, skip_download: bool = False):
    companies = load_companies()

    if company:
        targets = {company: companies[company]}
    else:
        targets = companies

    all_orders = []

    for code, info in targets.items():
        name = info["name"]
        print(f"\n{'='*60}")
        print(f"[{name}] ({code}) 백필 시작: {start} ~ 현재")
        print(f"{'='*60}")

        # 1. 공시 목록 수집
        filings = fetch_order_filings(code, start)
        print(f"  수주 공시: {len(filings)}건")

        # 2. 원문 다운로드
        if not skip_download:
            for f in filings:
                path = download_document(f["rcept_no"])
                if path:
                    print(f"  ✓ {f['rcept_dt']} {f['report_nm'][:40]}")

        # 3. 파싱
        for f in filings:
            result = parse_file(
                f["rcept_no"],
                rcept_dt=f["rcept_dt"],
                corp_code=code,
                corp_name=name,
            )
            if result:
                all_orders.append(result)

    # 4. 통합 데이터 저장
    # 정정 공시 처리: 같은 기업의 같은 날짜에 정정이 있으면 최신 것만 유지
    # rcept_no가 큰 게 최신
    all_orders.sort(key=lambda x: x["rcept_no"])

    orders_file = DATA_DIR / "orders.json"
    with open(orders_file, "w", encoding="utf-8") as f:
        json.dump(all_orders, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"백필 완료: 총 {len(all_orders)}건")
    print(f"통합 데이터: {orders_file}")
    print(f"{'='*60}")

    # 요약 통계
    by_company = {}
    for o in all_orders:
        name = o.get("corp_name", "?")
        by_company.setdefault(name, []).append(o)

    for name, orders in by_company.items():
        total_amt = sum(o["contract_amount_krw"] or 0 for o in orders)
        print(f"  {name}: {len(orders)}건, 총 {total_amt:,}억원")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="조선 수주 데이터 백필")
    parser.add_argument("--start", default="2020-01-01", help="시작일")
    parser.add_argument("--company", default=None, help="종목코드 (미지정시 전체)")
    parser.add_argument("--skip-download", action="store_true", help="다운로드 스킵 (이미 있는 경우)")
    args = parser.parse_args()

    backfill(args.start, args.company, args.skip_download)
