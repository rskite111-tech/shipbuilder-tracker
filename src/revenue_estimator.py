"""
수주잔고 기반 매출 추정 엔진
- 인도시기에서 건조기간 역산 → 건조 시작일
- S-curve로 분기별 매출 배분
- 기업별/분기별 추정 매출 산출
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent / "data"

# 선종별 건조 기간 (개월)
CONSTRUCTION_MONTHS = {
    "LNG운반선": 30,
    "VLCC": 18,
    "컨테이너선": 24,
    "LPG운반선": 20,
    "탱커": 18,
    "FPSO": 36,
    "해양플랜트": 36,
    "잠수함": 48,
    "자동차운반선": 20,
    "암모니아운반선": 24,
    "벌크선": 18,
    "기타": 24,
}

# S-curve 가중치 (건조 진행률별)
# 초기 1/3: 30%, 중반 1/3: 50%, 후반 1/3: 20%
def s_curve_weights(total_months: int) -> list[float]:
    """월별 S-curve 가중치 생성"""
    if total_months <= 0:
        return []

    third = total_months / 3
    weights = []

    for m in range(total_months):
        if m < third:
            w = 0.30 / third
        elif m < 2 * third:
            w = 0.50 / third
        else:
            w = 0.20 / third
        weights.append(w)

    # 정규화 (합이 1이 되도록)
    total = sum(weights)
    return [w / total for w in weights]


def month_add(year: int, month: int, delta: int) -> tuple[int, int]:
    """년월에 개월 수 더하기"""
    total = (year * 12 + month - 1) + delta
    return total // 12, total % 12 + 1


def month_to_quarter(year: int, month: int) -> str:
    """년월 → 분기 문자열 (예: 2025Q1)"""
    q = (month - 1) // 3 + 1
    return f"{year}Q{q}"


def estimate_order_revenue(order: dict) -> dict[str, float]:
    """
    단일 수주 건의 분기별 매출 추정

    Returns:
        {"2025Q1": 1234.5, "2025Q2": 2345.6, ...} (억원)
    """
    amount = order.get("contract_amount_krw")
    if not amount or amount <= 0:
        return {}

    ship_type = order.get("ship_type", "기타")
    construction_months = CONSTRUCTION_MONTHS.get(ship_type, 24)

    # 인도 종료일 파싱
    delivery_end = order.get("delivery_end", "")
    if not delivery_end:
        # delivery_end가 없으면 계약기간 종료일 사용
        return {}

    try:
        parts = delivery_end.split("-")
        end_year = int(parts[0])
        end_month = int(parts[1]) if len(parts) > 1 else 12
    except (ValueError, IndexError):
        return {}

    # 건조 시작일 역산
    start_year, start_month = month_add(end_year, end_month, -construction_months)

    # 월별 S-curve 가중치
    weights = s_curve_weights(construction_months)

    # 분기별 매출 배분
    quarterly = defaultdict(float)
    for i, w in enumerate(weights):
        y, m = month_add(start_year, start_month, i)
        qtr = month_to_quarter(y, m)
        quarterly[qtr] += amount * w

    return dict(quarterly)


def _load_recent_opm(n_quarters: int = 4) -> dict[str, float]:
    """재무 데이터에서 기업별 최근 N분기 평균 영업이익률(%) 계산"""
    fin_file = DATA_DIR / "financials.json"
    if not fin_file.exists():
        return {}

    with open(fin_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    opm = {}
    from itertools import groupby
    from operator import itemgetter

    data_sorted = sorted(data, key=itemgetter("corp_name"))
    for corp, rows in groupby(data_sorted, key=itemgetter("corp_name")):
        rows = sorted(rows, key=lambda x: x["quarter"], reverse=True)
        recent = rows[:n_quarters]
        rev_sum = sum(r.get("revenue", 0) or 0 for r in recent)
        op_sum = sum(r.get("operating_profit", 0) or 0 for r in recent)
        if rev_sum > 0:
            opm[corp] = round(op_sum / rev_sum * 100, 1)

    return opm


def estimate_all(orders: list[dict] = None) -> dict:
    """
    전체 수주에 대한 분기별 매출 추정

    Returns:
        {
            "by_company": {
                "HD현대중공업": {"2025Q1": xxx, ...},
                ...
            },
            "by_quarter": {
                "2025Q1": {"HD현대중공업": xxx, "한화오션": xxx, ...},
                ...
            },
            "totals": {"2025Q1": xxx, ...}
        }
    """
    if orders is None:
        orders_file = DATA_DIR / "orders.json"
        with open(orders_file, "r", encoding="utf-8") as f:
            orders = json.load(f)

    by_company = defaultdict(lambda: defaultdict(float))
    by_quarter = defaultdict(lambda: defaultdict(float))
    totals = defaultdict(float)
    # vintage: 분기별 매출이 어느 연도에 수주된 물량인지
    # {quarter: {order_year: amount}}
    by_vintage = defaultdict(lambda: defaultdict(float))
    # 기업별 vintage: {company: {quarter: {order_year: amount}}}
    by_company_vintage = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

    skipped = 0
    processed = 0

    for order in orders:
        rev = estimate_order_revenue(order)
        if not rev:
            skipped += 1
            continue

        processed += 1
        company = order.get("corp_name", "?")

        # 수주 연도 추출 (rcept_dt: "20240315" 형식)
        rcept_dt = order.get("rcept_dt", "")
        order_year = rcept_dt[:4] if len(rcept_dt) >= 4 else "기타"

        for qtr, amt in rev.items():
            by_company[company][qtr] += amt
            by_quarter[qtr][company] += amt
            totals[qtr] += amt
            by_vintage[qtr][order_year] += amt
            by_company_vintage[company][qtr][order_year] += amt

    # 영업이익 추정: 재무 데이터에서 최근 4분기 OPM 평균 적용
    opm_by_company = _load_recent_opm()
    op_by_company = defaultdict(lambda: defaultdict(float))
    op_by_quarter = defaultdict(lambda: defaultdict(float))
    op_totals = defaultdict(float)

    for company, qtrs in by_company.items():
        opm = opm_by_company.get(company, 0)
        for qtr, rev_amt in qtrs.items():
            op_amt = rev_amt * opm / 100
            op_by_company[company][qtr] += op_amt
            op_by_quarter[qtr][company] += op_amt
            op_totals[qtr] += op_amt

    return {
        "by_company": {k: dict(v) for k, v in by_company.items()},
        "by_quarter": {k: dict(v) for k, v in sorted(by_quarter.items())},
        "totals": dict(sorted(totals.items())),
        "op_by_company": {k: dict(v) for k, v in op_by_company.items()},
        "op_by_quarter": {k: dict(v) for k, v in sorted(op_by_quarter.items())},
        "op_totals": dict(sorted(op_totals.items())),
        "opm_used": opm_by_company,
        "by_vintage": {k: dict(v) for k, v in sorted(by_vintage.items())},
        "by_company_vintage": {
            comp: {qtr: dict(years) for qtr, years in sorted(qtrs.items())}
            for comp, qtrs in by_company_vintage.items()
        },
        "meta": {
            "total_orders": len(orders),
            "processed": processed,
            "skipped": skipped,
        }
    }


def generate_report(start_quarter: str = None, end_quarter: str = None):
    """매출 추정 리포트 생성"""
    result = estimate_all()

    companies = sorted(result["by_company"].keys())
    quarters = sorted(result["totals"].keys())

    # 기간 필터
    if start_quarter:
        quarters = [q for q in quarters if q >= start_quarter]
    if end_quarter:
        quarters = [q for q in quarters if q <= end_quarter]

    lines = []
    lines.append("=" * 90)
    lines.append("조선 4사 분기별 추정 매출 (수주잔고 기반, S-curve)")
    lines.append(f"처리: {result['meta']['processed']}건 / 스킵: {result['meta']['skipped']}건")
    lines.append("=" * 90)

    # 헤더
    header = f"{'분기':<10}"
    for c in companies:
        short = c.replace("HD현대", "HD").replace("삼성중공업", "삼성중")
        header += f"{short:>14}"
    header += f"{'합계':>14}"
    lines.append(header)
    lines.append("-" * 90)

    # 데이터
    for qtr in quarters:
        row = f"{qtr:<10}"
        qtr_total = 0
        for c in companies:
            amt = result["by_quarter"].get(qtr, {}).get(c, 0)
            qtr_total += amt
            row += f"{amt:>13,.0f}"
        row += f"{qtr_total:>13,.0f}"
        lines.append(row)

    # 연도별 소계
    lines.append("-" * 90)
    years = sorted(set(q[:4] for q in quarters))
    for year in years:
        year_qs = [q for q in quarters if q.startswith(year)]
        row = f"{year}년계   "
        yr_total = 0
        for c in companies:
            amt = sum(result["by_quarter"].get(q, {}).get(c, 0) for q in year_qs)
            yr_total += amt
            row += f"{amt:>13,.0f}"
        row += f"{yr_total:>13,.0f}"
        lines.append(row)

    output = "\n".join(lines)
    report_file = DATA_DIR / "revenue_estimate.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(output)

    # JSON도 저장
    json_file = DATA_DIR / "revenue_estimate.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(output)
    print(f"\n저장: {report_file}")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="수주잔고 기반 매출 추정")
    parser.add_argument("--start", default="2024Q1", help="시작 분기")
    parser.add_argument("--end", default="2029Q4", help="종료 분기")
    args = parser.parse_args()

    generate_report(args.start, args.end)
