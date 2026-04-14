"""
조선 수주 트래커 대시보드
- Streamlit + Plotly 기반 인터랙티브 시각화
- 6개사: HD현대중공업, 한화오션, 삼성중공업, HD현대미포, 한화엔진, HD현대마린엔진
"""

import json
from pathlib import Path
from collections import defaultdict

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

DATA_DIR = Path(__file__).parent / "data"

st.set_page_config(page_title="조선 수주 트래커", layout="wide", page_icon="🚢")

# 사이드바 필터 색상 (녹색 계열)
st.markdown("""
<style>
    /* 멀티셀렉트 태그 */
    span[data-baseweb="tag"] {
        background-color: #2e7d32 !important;
    }
    /* 슬라이더 */
    div[data-baseweb="slider"] div[role="slider"] {
        background-color: #43a047 !important;
        border-color: #43a047 !important;
    }
    div[data-testid="stSlider"] div[data-testid="stThumbValue"] {
        color: #2e7d32 !important;
    }
    /* 슬라이더 트랙 */
    div[data-baseweb="slider"] div[style*="background-color"] {
        background-color: #a5d6a7 !important;
    }
    /* 라디오 / 체크박스 선택 */
    div[data-baseweb="radio"] label[data-baseweb="radio"] input:checked + div {
        background-color: #43a047 !important;
        border-color: #43a047 !important;
    }
    /* 셀렉트박스 포커스 */
    div[data-baseweb="select"] > div:focus-within {
        border-color: #43a047 !important;
    }
    /* 버튼 */
    .stButton > button {
        border-color: #43a047 !important;
        color: #2e7d32 !important;
    }
    .stButton > button:hover {
        background-color: #e8f5e9 !important;
    }
</style>
""", unsafe_allow_html=True)

# 기업 컬러맵 (6사)
COLOR_MAP = {
    "HD현대중공업": "#1f77b4",
    "한화오션": "#2ca02c",
    "삼성중공업": "#9467bd",
    "HD현대미포": "#ff7f0e",
    "한화엔진": "#d62728",
    "HD현대마린엔진": "#17becf",
    "대한조선": "#8c564b",
}


@st.cache_data
def load_data():
    with open(DATA_DIR / "orders.json", "r", encoding="utf-8") as f:
        orders = json.load(f)

    df = pd.DataFrame(orders)
    df["rcept_dt"] = pd.to_datetime(df["rcept_dt"], format="%Y%m%d", errors="coerce")
    df["year"] = df["rcept_dt"].dt.year
    df["quarter"] = df["rcept_dt"].dt.to_period("Q").astype(str)
    df["year_month"] = df["rcept_dt"].dt.to_period("M").astype(str)
    df["delivery_end_dt"] = pd.to_datetime(df["delivery_end"], format="%Y-%m", errors="coerce")
    return df


@st.cache_data(ttl=60)
def load_revenue():
    rev_file = DATA_DIR / "revenue_estimate.json"
    if rev_file.exists():
        with open(rev_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


@st.cache_data(ttl=60)
def load_backlogs():
    bl_file = DATA_DIR / "backlogs.json"
    if bl_file.exists():
        with open(bl_file, "r", encoding="utf-8") as f:
            return pd.DataFrame(json.load(f))
    return pd.DataFrame()


@st.cache_data(ttl=60)
def load_financials():
    fin_file = DATA_DIR / "financials.json"
    if fin_file.exists():
        with open(fin_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data:
            return pd.DataFrame(data)
    return pd.DataFrame()


@st.cache_data
def load_stock_prices():
    price_file = DATA_DIR / "stock_prices.csv"
    if price_file.exists():
        df = pd.read_csv(price_file, encoding="utf-8-sig")
        df["Date"] = pd.to_datetime(df["Date"])
        return df
    return pd.DataFrame()


def make_dual_axis(fig1_traces, fig2_traces, y1_title, y2_title, title, height=500):
    """듀얼 Y축 차트 생성"""
    fig = go.Figure()
    for t in fig1_traces:
        t.yaxis = "y"
        fig.add_trace(t)
    for t in fig2_traces:
        t.yaxis = "y2"
        fig.add_trace(t)
    fig.update_layout(
        title=title, height=height,
        yaxis=dict(title=y1_title, side="left"),
        yaxis2=dict(title=y2_title, side="right", overlaying="y"),
        legend=dict(orientation="h", y=-0.2),
        xaxis_tickangle=-45,
    )
    return fig


def main():
    st.title("🚢 조선 7사 수주 트래커")
    st.caption("DART 공시 기반 | HD현대중공업 · 한화오션 · 삼성중공업 · HD현대미포 · 한화엔진 · HD현대마린엔진 · 대한조선")

    df = load_data()
    rev_data = load_revenue()
    fin_df = load_financials()
    stock_df = load_stock_prices()
    backlog_df = load_backlogs()

    # ── 사이드바 필터 ──
    st.sidebar.header("필터")

    companies = st.sidebar.multiselect(
        "기업", df["corp_name"].unique().tolist(),
        default=df["corp_name"].unique().tolist()
    )

    ship_types = st.sidebar.multiselect(
        "선종", df["ship_type"].unique().tolist(),
        default=df["ship_type"].unique().tolist()
    )

    year_range = st.sidebar.slider(
        "공시 연도",
        int(df["year"].min()), int(df["year"].max()),
        (int(df["year"].min()), int(df["year"].max()))
    )

    mask = (
        df["corp_name"].isin(companies) &
        df["ship_type"].isin(ship_types) &
        df["year"].between(year_range[0], year_range[1])
    )
    filtered = df[mask].copy()

    # ── KPI 카드 ──
    col1, col2, col3, col4 = st.columns(4)
    total_amt = filtered["contract_amount_krw"].sum()
    total_count = len(filtered)
    avg_per_vessel = filtered["per_vessel_price_krw"].dropna().mean()
    current_year = df["year"].max()
    ytd = filtered[filtered["year"] == current_year]
    ytd_amt = ytd["contract_amount_krw"].sum()

    col1.metric("총 수주 건수", f"{total_count}건")
    col2.metric("총 수주 금액", f"{total_amt/10000:,.1f}조원")
    col3.metric(f"{current_year}년 YTD", f"{ytd_amt/10000:,.1f}조원")
    col4.metric("평균 척당 단가", f"{avg_per_vessel:,.0f}억원" if pd.notna(avg_per_vessel) else "-")

    st.divider()

    # ── 탭 ──
    tabs = st.tabs([
        "🔧 신조선가", "📊 수주 추이", "🏢 기업별 비교", "🚢 선종 분석",
        "💰 매출·영업이익 추정", "📈 재무 실적", "📋 수주 목록"
    ])

    # ── 탭2: 수주 추이 ──
    with tabs[1]:
        st.subheader("분기별 수주 금액 추이")
        qtr_data = (
            filtered.groupby(["quarter", "corp_name"])["contract_amount_krw"]
            .sum().reset_index()
        )
        qtr_data.columns = ["분기", "기업", "금액"]

        fig = px.bar(
            qtr_data, x="분기", y="금액", color="기업",
            title="분기별 수주 금액 (억원)",
            color_discrete_map=COLOR_MAP
        )
        fig.update_layout(barmode="stack", xaxis_tickangle=-45, height=500)
        st.plotly_chart(fig, use_container_width=True)

        # 수주잔고 (공식 vs 추정) + 잔고/매출 비율
        st.divider()
        st.subheader("수주잔고 추이")

        if not backlog_df.empty and not fin_df.empty:
            # 공식 잔고 (사업보고서 + 분기/반기보고서)
            official_bl = backlog_df[backlog_df["corp_name"].isin(companies)].copy()

            # 추정 잔고 (수주 데이터 기반, 분기말 기준)
            est_bl_rows = []
            quarter_ends = {
                "Q1": (3, 31), "Q2": (6, 30), "Q3": (9, 30), "Q4": (12, 31)
            }
            for corp in companies:
                corp_orders = filtered[filtered["corp_name"] == corp].copy()
                # 공식 잔고에 있는 분기 기준으로 추정잔고도 계산
                for _, bl_row in official_bl[official_bl["corp_name"] == corp].iterrows():
                    qtr = bl_row["quarter"]
                    yr = int(qtr[:4])
                    q = qtr[4:]  # "Q1", "Q2", etc.
                    m, d = quarter_ends.get(q, (12, 31))
                    cutoff = pd.Timestamp(yr, m, d)
                    mask = (
                        (corp_orders["rcept_dt"] <= cutoff) &
                        (corp_orders["delivery_end_dt"].notna()) &
                        (corp_orders["delivery_end_dt"] > cutoff - pd.Timedelta(days=30))
                    )
                    backlog_est = corp_orders[mask]["contract_amount_krw"].sum()
                    if backlog_est > 0:
                        est_bl_rows.append({
                            "quarter": qtr, "corp_name": corp,
                            "추정잔고": round(backlog_est)
                        })

            est_bl = pd.DataFrame(est_bl_rows)

            # 공식 + 추정 합치기
            if not official_bl.empty:
                bl_compare = official_bl[["quarter", "corp_name", "backlog"]].rename(
                    columns={"backlog": "공식잔고"}
                )
                if not est_bl.empty:
                    bl_compare = bl_compare.merge(est_bl, on=["quarter", "corp_name"], how="outer")
                bl_compare = bl_compare.sort_values(["corp_name", "quarter"])

                bl_company = st.selectbox("기업 선택", companies, key="bl_company")
                bl_comp = bl_compare[bl_compare["corp_name"] == bl_company]

                if not bl_comp.empty:
                    all_qtrs = sorted(bl_comp["quarter"].unique())
                    fig_bl = go.Figure()
                    if "공식잔고" in bl_comp.columns and bl_comp["공식잔고"].notna().any():
                        fig_bl.add_trace(go.Bar(
                            x=bl_comp["quarter"], y=bl_comp["공식잔고"],
                            name="공식 잔고",
                            marker_color=COLOR_MAP.get(bl_company, "#1f77b4"),
                            opacity=0.7,
                        ))
                    if "추정잔고" in bl_comp.columns and bl_comp["추정잔고"].notna().any():
                        fig_bl.add_trace(go.Scatter(
                            x=bl_comp["quarter"], y=bl_comp["추정잔고"],
                            name="추정 잔고 (수주공시 기반)",
                            mode="lines+markers",
                            line=dict(color="red", width=2, dash="dash"),
                        ))
                    fig_bl.update_layout(
                        title=f"{bl_company} 분기별 수주잔고 (억원)",
                        xaxis_title="분기", yaxis_title="수주잔고 (억원)",
                        xaxis=dict(categoryorder="array", categoryarray=all_qtrs),
                        height=450, legend=dict(orientation="h", y=-0.15),
                    )
                    st.plotly_chart(fig_bl, use_container_width=True)
                    st.caption("공식 잔고: DART 사업/분기/반기보고서 수주현황 / 추정 잔고: 수주공시 기반 (인도종료 미도래분 합산)")

            # 잔고 / 연매출 비율 (Q4 기준)
            st.subheader("수주잔고 / 연매출 비율 (일감 연수)")
            st.caption("연말(Q4) 공식 수주잔고를 해당 연도 매출로 나눈 값. 높을수록 일감이 풍부.")

            q4_bl = official_bl[official_bl["quarter"].str.endswith("Q4")].copy()
            if not q4_bl.empty:
                q4_bl["bl_year"] = q4_bl["quarter"].str[:4].astype(int)
                # 연간 매출 계산
                fin_yearly = fin_df[fin_df["corp_name"].isin(companies)].copy()
                fin_yearly["fin_year"] = fin_yearly["quarter"].str[:4].astype(int)
                annual_rev = fin_yearly.groupby(["fin_year", "corp_name"])["revenue"].sum().reset_index()
                annual_rev.columns = ["bl_year", "corp_name", "연매출"]

                ratio_df = q4_bl[["bl_year", "corp_name", "backlog"]].merge(
                    annual_rev, on=["bl_year", "corp_name"], how="inner"
                )
                ratio_df["잔고/매출(년)"] = (ratio_df["backlog"] / ratio_df["연매출"]).round(1)
                ratio_df = ratio_df[ratio_df["잔고/매출(년)"].notna() & (ratio_df["잔고/매출(년)"] > 0)]

                if not ratio_df.empty:
                    fig_ratio = px.line(
                        ratio_df, x="bl_year", y="잔고/매출(년)", color="corp_name",
                        title="수주잔고 / 연매출 비율 (년)", markers=True,
                        labels={"bl_year": "연도", "corp_name": "기업"},
                        color_discrete_map=COLOR_MAP,
                    )
                    fig_ratio.update_layout(height=450)
                    st.plotly_chart(fig_ratio, use_container_width=True)

                    ratio_pivot = ratio_df.pivot_table(
                        values="잔고/매출(년)", index="bl_year", columns="corp_name"
                    )
                    st.dataframe(ratio_pivot.style.format("{:.1f}", na_rep="-"), use_container_width=True)
        elif backlog_df.empty:
            st.info("backlogs.json이 없습니다. backlog_collector.py를 실행하세요.")

    # ── 탭3: 기업별 비교 ──
    with tabs[2]:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("기업별 수주 금액")
            comp_amt = filtered.groupby("corp_name")["contract_amount_krw"].sum().reset_index()
            comp_amt.columns = ["기업", "금액"]
            fig3 = px.pie(comp_amt, values="금액", names="기업", title="수주 금액 점유율",
                         color="기업", color_discrete_map=COLOR_MAP)
            st.plotly_chart(fig3, use_container_width=True)

        with c2:
            st.subheader("기업별 수주 건수")
            comp_cnt = filtered.groupby("corp_name").size().reset_index(name="건수")
            comp_cnt.columns = ["기업", "건수"]
            fig4 = px.pie(comp_cnt, values="건수", names="기업", title="수주 건수 점유율",
                         color="기업", color_discrete_map=COLOR_MAP)
            st.plotly_chart(fig4, use_container_width=True)

        st.subheader("연도별 기업별 수주 금액")
        yearly = filtered.groupby(["year", "corp_name"])["contract_amount_krw"].sum().reset_index()
        yearly.columns = ["연도", "기업", "금액"]
        fig5 = px.bar(yearly, x="연도", y="금액", color="기업", barmode="group",
                     title="연도별 기업 수주 비교 (억원)", color_discrete_map=COLOR_MAP)
        fig5.update_layout(height=500)
        st.plotly_chart(fig5, use_container_width=True)

    # ── 탭4: 선종 분석 ──
    with tabs[3]:
        st.subheader("선종별 수주 금액")
        type_amt = (
            filtered.groupby("ship_type")["contract_amount_krw"]
            .sum().sort_values(ascending=True).reset_index()
        )
        type_amt.columns = ["선종", "금액"]
        fig6 = px.bar(type_amt, x="금액", y="선종", orientation="h",
                     title="선종별 수주 금액 (억원)")
        fig6.update_layout(height=400)
        st.plotly_chart(fig6, use_container_width=True)

        # 히트맵
        st.subheader("기업 × 선종 수주 금액 히트맵")
        pivot = filtered.pivot_table(
            values="contract_amount_krw", index="ship_type",
            columns="corp_name", aggfunc="sum", fill_value=0
        )
        fig8 = px.imshow(pivot, text_auto=".0f", aspect="auto",
                        title="기업별 선종 수주 금액 (억원)", color_continuous_scale="Blues")
        fig8.update_layout(height=500)
        st.plotly_chart(fig8, use_container_width=True)

    # ── 탭5: 매출·영업이익 추정 ──
    with tabs[4]:
        if rev_data:
            # 추정 방법론 설명
            with st.expander("추정 방법론", expanded=False):
                st.markdown("""
**매출 추정 (POC 진행기준)**

조선업은 건조 진행률에 따라 매출을 나눠서 인식합니다(진행기준 수익인식).
DART 수주 공시의 계약금액·인도시기를 기반으로 분기별 매출을 역산합니다.

**1단계: 건조 시작일 역산**
- 인도 종료일에서 선종별 건조기간만큼 차감
- 선종별 건조기간: LNG운반선 30개월, VLCC/탱커 18개월, 컨테이너선 24개월, FPSO/해양플랜트 36개월, 잠수함 48개월

**2단계: S-curve 매출 배분**
- 건조 기간을 3등분하여 차등 가중치 적용:
  - 초기 1/3 → 30% (설계·강재절단·블록 제작)
  - 중반 1/3 → 50% (블록 조립·도크 탑재 — 공정률 최대 구간)
  - 후반 1/3 → 20% (진수 후 의장·시운전)

**3단계: 분기별 집계**
- 월별 배분 금액을 분기로 합산, 전 수주 건을 기업별로 합계

**영업이익 추정**
- 각 기업의 최근 4분기 실적 기반 평균 영업이익률(OPM)을 산출
- 추정 매출에 해당 OPM을 적용하여 영업이익 추정

**한계점**
- 인도 종료일 기준 역산 (복수 척의 순차 인도 미구분)
- 실제 공정률 없이 고정 S-curve 사용
- 계약 변경(금액 조정, 인도 연기) 미반영
- 영업이익률은 최근 실적 기반 고정 — 향후 마진 변동 미반영
""")
                opm_used = rev_data.get("opm_used", {})
                if opm_used:
                    st.markdown("**적용된 영업이익률 (최근 4분기 평균)**")
                    opm_items = sorted(opm_used.items())
                    n_cols = len(opm_items)
                    opm_cols = st.columns(n_cols)
                    for i, (comp, rate) in enumerate(opm_items):
                        opm_cols[i].metric(comp, f"{rate}%")

            # --- 데이터 준비 ---
            rev_rows = []
            for qtr, company_data in rev_data["by_quarter"].items():
                for company, amt in company_data.items():
                    rev_rows.append({"분기": qtr, "기업": company, "추정매출": round(amt)})
            rev_df = pd.DataFrame(rev_rows)

            op_rows = []
            for qtr, company_data in rev_data.get("op_by_quarter", {}).items():
                for company, amt in company_data.items():
                    op_rows.append({"분기": qtr, "기업": company, "추정영업이익": round(amt)})
            op_df = pd.DataFrame(op_rows) if op_rows else pd.DataFrame()

            # vintage 데이터
            vintage_rows = []
            for qtr, year_data in rev_data.get("by_vintage", {}).items():
                for order_year, amt in year_data.items():
                    vintage_rows.append({"분기": qtr, "수주연도": f"{order_year}년", "금액": round(amt)})
            vintage_df = pd.DataFrame(vintage_rows) if vintage_rows else pd.DataFrame()

            company_vintage_data = rev_data.get("by_company_vintage", {})

            # --- 필터 ---
            rev_quarters = sorted(rev_df["분기"].unique())
            rc1, rc2 = st.columns(2)
            with rc1:
                start_q = st.selectbox("시작 분기", rev_quarters,
                    index=max(0, rev_quarters.index("2024Q1") if "2024Q1" in rev_quarters else 0))
            with rc2:
                end_idx = min(len(rev_quarters)-1,
                    rev_quarters.index("2028Q4") if "2028Q4" in rev_quarters else len(rev_quarters)-1)
                end_q = st.selectbox("종료 분기", rev_quarters, index=end_idx)

            rev_filtered = rev_df[(rev_df["분기"] >= start_q) & (rev_df["분기"] <= end_q)]
            rev_companies = st.multiselect(
                "기업 선택", rev_df["기업"].unique().tolist(),
                default=rev_df["기업"].unique().tolist(), key="rev_comp"
            )
            rev_filtered = rev_filtered[rev_filtered["기업"].isin(rev_companies)]

            op_filtered = pd.DataFrame()
            if not op_df.empty:
                op_filtered = op_df[(op_df["분기"] >= start_q) & (op_df["분기"] <= end_q)]
                op_filtered = op_filtered[op_filtered["기업"].isin(rev_companies)]

            # --- 추정 매출: 수주 연도별(Vintage) 구성 ---
            st.subheader("분기별 추정 매출 — 수주 연도별 구성")
            st.caption("각 분기 추정 매출이 어느 연도에 수주된 물량에서 나오는지 표시 (S-curve 기반)")

            vintage_mode = st.radio("범위", ["전체 합산", "기업별"], horizontal=True, key="vintage_mode")

            if vintage_mode == "기업별" and rev_companies:
                vintage_company = st.selectbox("기업", rev_companies, key="vintage_comp")
                cv_data = company_vintage_data.get(vintage_company, {})
                cv_rows = []
                for qtr, year_data in cv_data.items():
                    for yr, amt in year_data.items():
                        cv_rows.append({"분기": qtr, "수주연도": f"{yr}년", "금액": round(amt)})
                v_df = pd.DataFrame(cv_rows) if cv_rows else pd.DataFrame()
                vintage_title = f"{vintage_company} 분기별 추정 매출 — 수주연도별 (억원)"
            else:
                v_df = vintage_df.copy()
                vintage_title = "전체 분기별 추정 매출 — 수주연도별 (억원)"

            if not v_df.empty:
                v_df = v_df[(v_df["분기"] >= start_q) & (v_df["분기"] <= end_q)]
                v_df = v_df.sort_values(["분기", "수주연도"])

                fig_v = px.bar(
                    v_df, x="분기", y="금액", color="수주연도",
                    title=vintage_title, barmode="stack",
                )
                fig_v.update_layout(xaxis_tickangle=-45, height=500)
                st.plotly_chart(fig_v, use_container_width=True)
            else:
                st.info("Vintage 데이터가 없습니다.")

            # --- 추정 영업이익 ---
            st.subheader("분기별 추정 영업이익")

            opm_used = rev_data.get("opm_used", {})
            if opm_used and not fin_df.empty:
                with st.expander("영업이익 추정 로직", expanded=True):
                    st.markdown("**추정 매출 x 최근 4분기 평균 OPM = 추정 영업이익**")
                    st.markdown(
                        "각 기업의 최근 4분기 실적에서 영업이익률(OPM)을 산출하고, "
                        "위에서 추정한 분기별 매출에 해당 OPM을 곱하여 영업이익을 추정합니다. "
                        "실제로는 수주 시점의 선가·원자재 가격·환율에 따라 마진이 달라지지만, "
                        "최근 실적이 향후에도 유지된다는 가정입니다."
                    )

                    # OPM 산출 근거 테이블
                    opm_detail_rows = []
                    for comp in sorted(opm_used.keys()):
                        comp_fin = fin_df[fin_df["corp_name"] == comp].sort_values("quarter")
                        recent4 = comp_fin.tail(4)
                        if len(recent4) == 4:
                            rev_sum = recent4["revenue"].sum()
                            op_sum = recent4["operating_profit"].sum()
                            qtrs = recent4["quarter"].tolist()
                            opm_detail_rows.append({
                                "기업": comp,
                                "기간": f"{qtrs[0]}~{qtrs[-1]}",
                                "매출 합계": f"{rev_sum:,.0f}",
                                "영업이익 합계": f"{op_sum:,.0f}",
                                "OPM": f"{opm_used[comp]}%",
                            })
                    if opm_detail_rows:
                        st.dataframe(pd.DataFrame(opm_detail_rows).set_index("기업"), use_container_width=True)

            if not op_filtered.empty:
                fig_op = px.bar(
                    op_filtered, x="분기", y="추정영업이익", color="기업",
                    title="분기별 추정 영업이익 (억원)", barmode="stack",
                    color_discrete_map=COLOR_MAP
                )
                fig_op.update_layout(xaxis_tickangle=-45, height=500)
                st.plotly_chart(fig_op, use_container_width=True)
            else:
                st.info("영업이익 추정 데이터가 없습니다. financials.json이 필요합니다.")

            # --- 추정 vs 실적 비교 ---
            if not fin_df.empty:
                st.subheader("추정 vs 실적 비교")
                compare_company = st.selectbox("비교 기업", rev_companies, key="compare_comp")
                compare_metric = st.radio(
                    "비교 지표", ["매출", "영업이익"], horizontal=True, key="compare_metric"
                )
                if compare_company:
                    actual = fin_df[fin_df["corp_name"] == compare_company].copy()
                    if not actual.empty:
                        actual = actual.sort_values("quarter")

                        if compare_metric == "매출":
                            est = rev_filtered[rev_filtered["기업"] == compare_company].copy()
                            est_x, est_y = est["분기"], est["추정매출"]
                            act_y = actual["revenue"]
                            est_label, act_label = "추정 매출 (수주기반)", "실적 매출 (DART)"
                            title_suffix = "매출"
                        else:
                            est = op_filtered[op_filtered["기업"] == compare_company].copy() if not op_filtered.empty else pd.DataFrame()
                            est_x = est["분기"] if not est.empty else pd.Series(dtype=str)
                            est_y = est["추정영업이익"] if not est.empty else pd.Series(dtype=float)
                            act_y = actual["operating_profit"]
                            est_label, act_label = "추정 영업이익 (수주기반)", "실적 영업이익 (DART)"
                            title_suffix = "영업이익"

                        all_quarters_cmp = sorted(set(
                            est_x.tolist() + actual["quarter"].tolist()
                        ))

                        fig_cmp = go.Figure()
                        if not est_x.empty:
                            fig_cmp.add_trace(go.Bar(
                                x=est_x, y=est_y,
                                name=est_label, marker_color="rgba(31,119,180,0.5)"
                            ))
                        fig_cmp.add_trace(go.Scatter(
                            x=actual["quarter"], y=act_y,
                            name=act_label, mode="lines+markers",
                            line=dict(color="red", width=2)
                        ))
                        fig_cmp.update_layout(
                            title=f"{compare_company} 추정 vs 실적 {title_suffix} (억원)",
                            xaxis=dict(categoryorder="array", categoryarray=all_quarters_cmp, tickangle=-45),
                            height=450,
                            legend=dict(orientation="h", y=-0.15)
                        )
                        st.plotly_chart(fig_cmp, use_container_width=True)

            # --- 연도별 합계 테이블 ---
            st.subheader("연도별 추정 매출 (억원)")
            rev_filtered_copy = rev_filtered.copy()
            rev_filtered_copy["연도"] = rev_filtered_copy["분기"].str[:4]
            yearly_rev = rev_filtered_copy.pivot_table(
                values="추정매출", index="연도", columns="기업",
                aggfunc="sum", fill_value=0, margins=True, margins_name="합계"
            )
            st.dataframe(yearly_rev.style.format("{:,.0f}"), use_container_width=True)

            if not op_filtered.empty:
                st.subheader("연도별 추정 영업이익 (억원)")
                op_filtered_copy = op_filtered.copy()
                op_filtered_copy["연도"] = op_filtered_copy["분기"].str[:4]
                yearly_op = op_filtered_copy.pivot_table(
                    values="추정영업이익", index="연도", columns="기업",
                    aggfunc="sum", fill_value=0, margins=True, margins_name="합계"
                )
                st.dataframe(yearly_op.style.format("{:,.0f}"), use_container_width=True)

            st.caption(f"처리: {rev_data['meta']['processed']}건 / 스킵: {rev_data['meta']['skipped']}건 (인도시기 미기재)")
        else:
            st.warning("revenue_estimate.json이 없습니다. revenue_estimator.py를 먼저 실행하세요.")

    # ── 탭6: 재무 실적 ──
    with tabs[5]:
        if not fin_df.empty:
            fin_companies = st.multiselect(
                "기업 선택", fin_df["corp_name"].unique().tolist(),
                default=[c for c in companies if c in fin_df["corp_name"].values],
                key="fin_companies"
            )
            fin_filtered = fin_df[fin_df["corp_name"].isin(fin_companies)].copy()
            fin_filtered = fin_filtered.sort_values("quarter")

            # 재무 차트: 지표 선택
            METRIC_MAP = {
                "revenue": "매출액", "cogs": "매출원가", "gross_profit": "매출총이익",
                "sga": "판관비", "operating_profit": "영업이익", "net_income": "당기순이익"
            }
            available_metrics = [m for m in METRIC_MAP if m in fin_filtered.columns and fin_filtered[m].notna().any()]

            st.subheader("분기별 재무 실적 비교")
            metric = st.radio(
                "지표", available_metrics,
                format_func=lambda x: METRIC_MAP[x], horizontal=True
            )

            chart_df = fin_filtered.dropna(subset=[metric])
            fig_fin = px.bar(
                chart_df, x="quarter", y=metric, color="corp_name",
                title=f"분기별 {METRIC_MAP[metric]} (억원)", barmode="group",
                labels={"quarter": "분기", metric: f"{METRIC_MAP[metric]}(억원)", "corp_name": "기업"},
                color_discrete_map=COLOR_MAP
            )
            fig_fin.update_layout(xaxis_tickangle=-45, height=500)
            st.plotly_chart(fig_fin, use_container_width=True)

            # 기업별 상세 재무 테이블
            st.subheader("기업별 손익 요약")
            fin_company = st.selectbox("기업 선택", fin_companies, key="fin_detail_company")
            comp_fin_detail = fin_filtered[fin_filtered["corp_name"] == fin_company].sort_values("quarter")

            display_metrics = [m for m in ["revenue", "cogs", "gross_profit", "sga", "operating_profit", "net_income"]
                              if m in comp_fin_detail.columns]
            metric_labels = {"revenue": "매출액", "cogs": "매출원가", "gross_profit": "매출총이익",
                            "sga": "판관비", "operating_profit": "영업이익", "net_income": "당기순이익"}

            table_data = comp_fin_detail.set_index("quarter")[display_metrics].T
            table_data.index = [metric_labels.get(m, m) for m in table_data.index]
            st.dataframe(table_data.style.format("{:,.0f}", na_rep="-"), use_container_width=True)

            # 마진율 추이
            st.subheader("마진율 추이")
            margin_df = fin_filtered.copy()
            if "gross_profit" in margin_df.columns:
                margin_df["매출총이익률"] = (margin_df["gross_profit"] / margin_df["revenue"] * 100).round(1)
            margin_df["영업이익률"] = (margin_df["operating_profit"] / margin_df["revenue"] * 100).round(1)
            margin_df["순이익률"] = (margin_df["net_income"] / margin_df["revenue"] * 100).round(1)

            margin_cols = [c for c in ["매출총이익률", "영업이익률", "순이익률"] if c in margin_df.columns]
            margin_melted = margin_df.melt(
                id_vars=["quarter", "corp_name"], value_vars=margin_cols,
                var_name="마진", value_name="비율(%)"
            )

            fig_margin = px.line(
                margin_melted[margin_melted["corp_name"] == fin_company],
                x="quarter", y="비율(%)", color="마진",
                title=f"{fin_company} 마진율 추이 (%)", markers=True
            )
            fig_margin.update_layout(xaxis_tickangle=-45, height=400)
            st.plotly_chart(fig_margin, use_container_width=True)

        else:
            st.warning("financials.json 데이터가 없습니다.")

    # ── 탭1: 신조선가 ──
    with tabs[0]:
        st.subheader("신조선가 추이 (척당 단가)")
        st.caption("DART 수주공시의 계약금액/척수 기반. 실제 신조선가 지수와 다를 수 있음.")

        # 척당단가가 있는 데이터만
        price_data = filtered[
            (filtered["per_vessel_price_krw"].notna()) &
            (filtered["per_vessel_price_krw"] > 0)
        ].copy()

        if not price_data.empty:
            price_data["rcept_dt"] = pd.to_datetime(price_data["rcept_dt"])
            price_data["quarter"] = price_data["rcept_dt"].dt.to_period("Q").astype(str)

            # 주요 선종 필터 (데이터 충분한 것만)
            type_counts = price_data["ship_type"].value_counts()
            major_types = type_counts[type_counts >= 5].index.tolist()

            # 1) 선종별 분기 평균 단가 추이
            st.subheader("선종별 분기 평균 단가 추이")
            selected_types = st.multiselect(
                "선종 선택", major_types, default=major_types[:4], key="nb_types"
            )

            if selected_types:
                nb_data = price_data[price_data["ship_type"].isin(selected_types)].copy()
                qtr_avg = nb_data.groupby(["quarter", "ship_type"])["per_vessel_price_krw"].mean().reset_index()
                qtr_avg.columns = ["분기", "선종", "척당단가"]

                all_qtrs = sorted(qtr_avg["분기"].unique())
                fig_nb = px.line(
                    qtr_avg, x="분기", y="척당단가", color="선종",
                    title="선종별 신조선가 추이 (분기 평균, 억원)",
                    markers=True,
                    labels={"척당단가": "척당 단가 (억원)"},
                )
                fig_nb.update_layout(
                    height=500, xaxis_tickangle=-45,
                    xaxis=dict(categoryorder="array", categoryarray=all_qtrs),
                )
                st.plotly_chart(fig_nb, use_container_width=True)

            # 2) 선종별 scatter (개별 계약 건)
            st.subheader("개별 수주 건 단가 분포")
            scatter_type = st.selectbox("선종", major_types, key="nb_scatter_type")
            scatter_data = price_data[price_data["ship_type"] == scatter_type].copy()

            if not scatter_data.empty:
                fig_scatter = px.scatter(
                    scatter_data, x="rcept_dt", y="per_vessel_price_krw",
                    color="corp_name", size="vessel_count",
                    hover_data=["counterparty", "contract_amount_krw", "fuel_type"],
                    title=f"{scatter_type} 척당 단가 분포 (억원)",
                    labels={
                        "rcept_dt": "공시일", "per_vessel_price_krw": "척당 단가 (억원)",
                        "corp_name": "기업", "vessel_count": "척수",
                    },
                    color_discrete_map=COLOR_MAP,
                )
                fig_scatter.update_layout(height=500)

                # 추세선 추가 (OLS)
                scatter_data["days"] = (scatter_data["rcept_dt"] - scatter_data["rcept_dt"].min()).dt.days
                if len(scatter_data) >= 3:
                    import numpy as np
                    z = np.polyfit(scatter_data["days"], scatter_data["per_vessel_price_krw"], 1)
                    p = np.poly1d(z)
                    x_range = pd.date_range(scatter_data["rcept_dt"].min(), scatter_data["rcept_dt"].max(), periods=50)
                    days_range = (x_range - scatter_data["rcept_dt"].min()).days
                    fig_scatter.add_trace(go.Scatter(
                        x=x_range, y=p(days_range),
                        mode="lines", name="추세선",
                        line=dict(color="gray", dash="dash", width=1.5),
                    ))

                st.plotly_chart(fig_scatter, use_container_width=True)

                # 연도별 통계 테이블
                scatter_data["year"] = scatter_data["rcept_dt"].dt.year
                yearly_stats = scatter_data.groupby("year")["per_vessel_price_krw"].agg(
                    ["count", "mean", "min", "max"]
                ).round(0)
                yearly_stats.columns = ["건수", "평균(억)", "최저(억)", "최고(억)"]
                st.dataframe(yearly_stats, use_container_width=True)

        else:
            st.info("척당 단가 데이터가 없습니다.")

    # ── 탭7: 수주 목록 ──
    with tabs[6]:
        st.subheader(f"수주 목록 ({len(filtered)}건)")

        display_cols = [
            "rcept_dt", "corp_name", "contract_name", "ship_type",
            "vessel_count", "contract_amount_krw", "per_vessel_price_krw",
            "counterparty", "delivery_end", "fuel_type"
        ]
        display_names = {
            "rcept_dt": "공시일", "corp_name": "기업", "contract_name": "계약명",
            "ship_type": "선종", "vessel_count": "척수",
            "contract_amount_krw": "금액(억)", "per_vessel_price_krw": "척당(억)",
            "counterparty": "상대방", "delivery_end": "인도종료", "fuel_type": "연료"
        }

        show_df = filtered[display_cols].rename(columns=display_names).sort_values("공시일", ascending=False)
        st.dataframe(show_df, use_container_width=True, height=600)


if __name__ == "__main__":
    main()
