"""
Notion DB 동기화
- 파싱된 수주 데이터를 Notion 데이터베이스에 적재
- 이 모듈은 Notion MCP를 통해 실행됨 (Claude Code에서 호출)
- 독립 실행 시에는 notion-client 사용
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def load_orders() -> list[dict]:
    """통합 수주 데이터 로드"""
    orders_file = DATA_DIR / "orders.json"
    with open(orders_file, "r", encoding="utf-8") as f:
        return json.load(f)


def format_for_notion(order: dict) -> dict:
    """수주 데이터를 Notion DB 속성 형식으로 변환"""
    props = {
        "공시번호": order["rcept_no"],
        "공시일": order.get("rcept_dt", ""),
        "기업": order.get("corp_name", ""),
        "계약명": order.get("contract_name", ""),
        "선종": order.get("ship_type", "기타"),
        "척수": order.get("vessel_count"),
        "계약금액_억원": order.get("contract_amount_krw"),
        "척당단가_억원": order.get("per_vessel_price_krw"),
        "인도시작": order.get("delivery_start", ""),
        "인도종료": order.get("delivery_end", ""),
        "매출비중_pct": order.get("revenue_ratio_pct"),
        "상대방": order.get("counterparty", ""),
        "연료타입": order.get("fuel_type", ""),
        "비고": order.get("remarks", "")[:200],
        "DART링크": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={order['rcept_no']}",
    }
    return props


def print_notion_ready():
    """Notion 적재용 데이터 요약 출력"""
    orders = load_orders()
    print(f"Notion 적재 대상: {len(orders)}건\n")

    for o in orders[:5]:
        props = format_for_notion(o)
        print(f"[{props['공시일']}] {props['기업']} | {props['계약명']} | {props['계약금액_억원']:,}억")

    print(f"\n... 외 {len(orders)-5}건")
    print("\nNotion MCP를 통해 데이터베이스에 적재하려면:")
    print("  Claude Code에서 'Notion에 수주 데이터 동기화해줘' 라고 요청하세요.")


if __name__ == "__main__":
    print_notion_ready()
