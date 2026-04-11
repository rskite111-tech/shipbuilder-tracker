"""
조선 수주 트래커 대시보드
- Streamlit + Plotly 기반 인터랙티브 시각화
"""

import json
from pathlib import Path
from collections import defaultdict

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"

st.set_page_config(page_title="조선 수주 트래커", layout="wide", page_icon="🚢")


@st.cache_data
def load_data():
    with open(DATA_DIR / "orders.json", "r", encoding="utf-8") as f:
        orders = json.load(f)

    df = pd.DataFrame(orders)
    df["rcept_dt"] = pd.to_datetime(df["rcept_dt"], format="%Y%m%d", errors="coerce")
    df["year"] = df["rcept_dt"].dt.year
    df["quarter"] = df["rcept_dt"].dt.to_period("Q").astype(str)
    df["year_month"] = df["rcept_dt"].dt.to_period("M").astype(str)

    # 인도 종료일
    df["delivery_end_dt"] = pd.to_datetime(df["delivery_end"], format="%Y-%m", errors="coerce")

    return df


@st.cache_data
def load_revenue():
    rev_file = DATA_DIR / "revenue_estimate.json"
    if rev_file.exists():
        with open(rev_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def main():
    st.title("🚢 조선 4사 수주 트래커")
    st.caption("DART 공시 기반 | HD현대중공업 · 한화오션 · 삼성중공업 · HD현대미포")

    df = load_data()
    rev_data = load_revenue()

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

    # 필터 적용
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

    # 올해 수주
    current_year = df["year"].max()
    ytd = filtered[filtered["year"] == current_year]
    ytd_amt = ytd["contract_amount_krw"].sum()

    col1.metric("총 수주 건수", f"{total_count}건")
    col2.metric("총 수주 금액", f"{total_amt/10000:,.1f}조원")
    col3.metric(f"{current_year}년 YTD", f"{ytd_amt/10000:,.1f}조원")
    col4.metric("평균 척당 단가", f"{avg_per_vessel:,.0f}억원" if pd.notna(avg_per_vessel) else "-")

    st.divider()

    # ── 탭 ──
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 수주 추이", "🏢 기업별 비교", "🚢 선종 분석", "💰 매출 추정", "📋 수주 목록"
    ])

    # ── 탭1: 수주 추이 ──
    with tab1:
        st.subheader("분기별 수주 금액 추이")

        qtr_data = (
            filtered.groupby(["quarter", "corp_name"])["contract_amount_krw"]
            .sum().reset_index()
        )
        qtr_data.columns = ["분기", "기업", "금액"]

        fig = px.bar(
            qtr_data, x="분기", y="금액", color="기업",
            title="분기별 수주 금액 (억원)",
            color_discrete_map={
                "HD현대중공업": "#1f77b4", "한화오션": "#2ca02c",
                "삼성중공업": "#9467bd", "HD현대미포": "#ff7f0e"
            }
        )
        fig.update_layout(barmode="stack", xaxis_tickangle=-45, height=500)
        st.plotly_chart(fig, use_container_width=True)

        # 누적 수주 추이
        st.subheader("월별 누적 수주 금액")
        monthly = (
            filtered.groupby(["year_month", "corp_name"])["contract_amount_krw"]
            .sum().reset_index()
        )
        monthly.columns = ["월", "기업", "금액"]
        monthly = monthly.sort_values("월")

        # 기업별 누적
        cumsum_data = []
        for company in monthly["기업"].unique():
            comp_data = monthly[monthly["기업"] == company].copy()
            comp_data["누적"] = comp_data["금액"].cumsum()
            cumsum_data.append(comp_data)

        cumsum_df = pd.concat(cumsum_data)

        fig2 = px.line(
            cumsum_df, x="월", y="누적", color="기업",
            title="기업별 누적 수주 금액 (억원)",
            color_discrete_map={
                "HD현대중공업": "#1f77b4", "한화오션": "#2ca02c",
                "삼성중공업": "#9467bd", "HD현대미포": "#ff7f0e"
            }
        )
        fig2.update_layout(xaxis_tickangle=-45, height=450)
        st.plotly_chart(fig2, use_container_width=True)

    # ── 탭2: 기업별 비교 ──
    with tab2:
        c1, c2 = st.columns(2)

        with c1:
            st.subheader("기업별 수주 금액")
            comp_amt = (
                filtered.groupby("corp_name")["contract_amount_krw"]
                .sum().reset_index()
            )
            comp_amt.columns = ["기업", "금액"]
            fig3 = px.pie(comp_amt, values="금액", names="기업", title="수주 금액 점유율",
                         color="기업", color_discrete_map={
                             "HD현대중공업": "#1f77b4", "한화오션": "#2ca02c",
                             "삼성중공업": "#9467bd", "HD현대미포": "#ff7f0e"
                         })
            st.plotly_chart(fig3, use_container_width=True)

        with c2:
            st.subheader("기업별 수주 건수")
            comp_cnt = filtered.groupby("corp_name").size().reset_index(name="건수")
            comp_cnt.columns = ["기업", "건수"]
            fig4 = px.pie(comp_cnt, values="건수", names="기업", title="수주 건수 점유율",
                         color="기업", color_discrete_map={
                             "HD현대중공업": "#1f77b4", "한화오션": "#2ca02c",
                             "삼성중공업": "#9467bd", "HD현대미포": "#ff7f0e"
                         })
            st.plotly_chart(fig4, use_container_width=True)

        # 연도별 기업별 수주
        st.subheader("연도별 기업별 수주 금액")
        yearly = (
            filtered.groupby(["year", "corp_name"])["contract_amount_krw"]
            .sum().reset_index()
        )
        yearly.columns = ["연도", "기업", "금액"]

        fig5 = px.bar(
            yearly, x="연도", y="금액", color="기업", barmode="group",
            title="연도별 기업 수주 비교 (억원)",
            color_discrete_map={
                "HD현대중공업": "#1f77b4", "한화오션": "#2ca02c",
                "삼성중공업": "#9467bd", "HD현대미포": "#ff7f0e"
            }
        )
        fig5.update_layout(height=500)
        st.plotly_chart(fig5, use_container_width=True)

    # ── 탭3: 선종 분석 ──
    with tab3:
        c1, c2 = st.columns(2)

        with c1:
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

        with c2:
            st.subheader("선종별 평균 척당 단가 추이")
            price_data = filtered.dropna(subset=["per_vessel_price_krw"])
            if not price_data.empty:
                top_types = price_data["ship_type"].value_counts().head(5).index.tolist()
                price_top = price_data[price_data["ship_type"].isin(top_types)]

                yearly_price = (
                    price_top.groupby(["year", "ship_type"])["per_vessel_price_krw"]
                    .mean().reset_index()
                )
                yearly_price.columns = ["연도", "선종", "척당단가"]

                fig7 = px.line(yearly_price, x="연도", y="척당단가", color="선종",
                              title="주요 선종 척당 단가 추이 (억원)", markers=True)
                fig7.update_layout(height=400)
                st.plotly_chart(fig7, use_container_width=True)

        # 선종 x 기업 히트맵
        st.subheader("기업 × 선종 수주 금액 히트맵")
        pivot = filtered.pivot_table(
            values="contract_amount_krw", index="ship_type",
            columns="corp_name", aggfunc="sum", fill_value=0
        )
        fig8 = px.imshow(
            pivot, text_auto=".0f", aspect="auto",
            title="기업별 선종 수주 금액 (억원)",
            color_continuous_scale="Blues"
        )
        fig8.update_layout(height=500)
        st.plotly_chart(fig8, use_container_width=True)

    # ── 탭4: 매출 추정 ──
    with tab4:
        if rev_data:
            st.subheader("분기별 추정 매출 (S-curve 기반)")

            # 분기별 데이터를 DataFrame으로
            rows = []
            for qtr, company_data in rev_data["by_quarter"].items():
                for company, amt in company_data.items():
                    rows.append({"분기": qtr, "기업": company, "추정매출": round(amt)})

            rev_df = pd.DataFrame(rows)

            # 기간 필터
            rev_quarters = sorted(rev_df["분기"].unique())
            start_q = st.selectbox("시작 분기", rev_quarters,
                                   index=max(0, rev_quarters.index("2024Q1") if "2024Q1" in rev_quarters else 0))
            end_idx = min(len(rev_quarters)-1,
                         rev_quarters.index("2028Q4") if "2028Q4" in rev_quarters else len(rev_quarters)-1)
            end_q = st.selectbox("종료 분기", rev_quarters, index=end_idx)

            rev_filtered = rev_df[(rev_df["분기"] >= start_q) & (rev_df["분기"] <= end_q)]

            # 기업 필터
            rev_companies = st.multiselect(
                "기업 선택", rev_df["기업"].unique().tolist(),
                default=rev_df["기업"].unique().tolist(), key="rev_comp"
            )
            rev_filtered = rev_filtered[rev_filtered["기업"].isin(rev_companies)]

            fig9 = px.bar(
                rev_filtered, x="분기", y="추정매출", color="기업",
                title="분기별 추정 매출 (억원, S-curve)",
                barmode="stack",
                color_discrete_map={
                    "HD현대중공업": "#1f77b4", "한화오션": "#2ca02c",
                    "삼성중공업": "#9467bd", "HD현대미포": "#ff7f0e"
                }
            )
            fig9.update_layout(xaxis_tickangle=-45, height=500)
            st.plotly_chart(fig9, use_container_width=True)

            # 연도별 합계 테이블
            st.subheader("연도별 추정 매출 (억원)")
            rev_filtered["연도"] = rev_filtered["분기"].str[:4]
            yearly_rev = rev_filtered.pivot_table(
                values="추정매출", index="연도", columns="기업",
                aggfunc="sum", fill_value=0, margins=True, margins_name="합계"
            )
            st.dataframe(yearly_rev.style.format("{:,.0f}"), use_container_width=True)

            st.caption(f"처리: {rev_data['meta']['processed']}건 / 스킵: {rev_data['meta']['skipped']}건 (인도시기 미기재)")
        else:
            st.warning("revenue_estimate.json이 없습니다. revenue_estimator.py를 먼저 실행하세요.")

    # ── 탭5: 수주 목록 ──
    with tab5:
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
