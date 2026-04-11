"""
일일 신규 공시 체크
- 최근 7일간 신규 수주공시 확인
- 신규 건만 다운로드 + 파싱
- orders.json 업데이트
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dart_collector import load_companies, fetch_order_filings, download_document
from disclosure_parser import parse_file, DATA_DIR, PARSED_DIR


def daily_update(days: int = 7):
    companies = load_companies()
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # 기존 orders.json 로드
    orders_file = DATA_DIR / "orders.json"
    existing = []
    existing_rcept = set()
    if orders_file.exists():
        with open(orders_file, "r", encoding="utf-8") as f:
            existing = json.load(f)
            existing_rcept = {o["rcept_no"] for o in existing}

    new_orders = []

    for code, info in companies.items():
        name = info["name"]
        filings = fetch_order_filings(code, start)

        for f in filings:
            if f["rcept_no"] in existing_rcept:
                continue

            print(f"[신규] {name} | {f['rcept_dt']} | {f['report_nm'][:40]}")

            path = download_document(f["rcept_no"])
            if path:
                result = parse_file(
                    f["rcept_no"],
                    rcept_dt=f["rcept_dt"],
                    corp_code=code,
                    corp_name=name,
                )
                if result:
                    new_orders.append(result)

    if new_orders:
        all_orders = existing + new_orders
        all_orders.sort(key=lambda x: x["rcept_no"])

        with open(orders_file, "w", encoding="utf-8") as f:
            json.dump(all_orders, f, ensure_ascii=False, indent=2)

        print(f"\n신규 {len(new_orders)}건 추가 (총 {len(all_orders)}건)")
    else:
        print(f"\n신규 수주 공시 없음 (최근 {days}일)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="조회 일수 (기본 7일)")
    args = parser.parse_args()
    daily_update(args.days)
