"""
Notion DB에 수주 데이터 일괄 적재
- orders.json → Notion 페이지 생성
- notion-client 라이브러리 사용
"""

import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"

# 이미 적재된 공시번호 추적
UPLOADED_FILE = DATA_DIR / "notion_uploaded.json"


def fmt_date(dt_str):
    if not dt_str:
        return None
    if len(dt_str) == 8 and dt_str.isdigit():
        return f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:]}"
    if len(dt_str) == 7:
        return f"{dt_str}-01"
    if len(dt_str) == 10:
        return dt_str
    return None


def order_to_notion_props(o):
    p = {
        "계약명": o.get("contract_name") or o.get("rcept_no", "?"),
        "기업": o.get("corp_name", ""),
        "선종": o.get("ship_type", "기타"),
        "연료타입": o.get("fuel_type", "기존연료"),
        "상대방": (o.get("counterparty", "") or "")[:100],
        "공시번호": o.get("rcept_no", ""),
        "DART링크": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={o.get('rcept_no', '')}",
    }
    if o.get("contract_amount_krw"):
        p["계약금액_억원"] = o["contract_amount_krw"]
    if o.get("vessel_count"):
        p["척수"] = o["vessel_count"]
    if o.get("per_vessel_price_krw"):
        p["척당단가_억원"] = o["per_vessel_price_krw"]
    if o.get("revenue_ratio_pct"):
        p["매출비중_pct"] = o["revenue_ratio_pct"]

    d = fmt_date(o.get("rcept_dt", ""))
    if d:
        p["date:공시일:start"] = d
    ds = fmt_date(o.get("delivery_start", ""))
    if ds:
        p["date:인도시작:start"] = ds
    de = fmt_date(o.get("delivery_end", ""))
    if de:
        p["date:인도종료:start"] = de

    return p


def load_uploaded():
    if UPLOADED_FILE.exists():
        with open(UPLOADED_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_uploaded(uploaded_set):
    with open(UPLOADED_FILE, "w") as f:
        json.dump(list(uploaded_set), f)


def prepare_remaining():
    """아직 업로드되지 않은 주문 준비"""
    with open(DATA_DIR / "orders.json", "r", encoding="utf-8") as f:
        orders = json.load(f)

    uploaded = load_uploaded()
    remaining = [o for o in orders if o["rcept_no"] not in uploaded]

    # 배치로 나누기 (25건씩)
    batches = []
    for i in range(0, len(remaining), 25):
        batch = remaining[i:i+25]
        batch_pages = [{"properties": order_to_notion_props(o)} for o in batch]
        batches.append((batch, batch_pages))

    print(f"전체: {len(orders)}건, 업로드 완료: {len(uploaded)}건, 남은: {len(remaining)}건, 배치: {len(batches)}개")

    # JSON 배치 파일 생성
    for i, (raw_batch, pages_batch) in enumerate(batches):
        out_file = DATA_DIR / f"_upload_batch_{i}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(pages_batch, f, ensure_ascii=False)

    return len(remaining), len(batches)


if __name__ == "__main__":
    remaining, num_batches = prepare_remaining()
    print(f"\n{num_batches}개 배치 파일이 data/_upload_batch_N.json에 생성됨")
    print("Claude Code에서 Notion MCP로 적재해주세요.")
