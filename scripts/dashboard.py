"""
Inventory Shrinkage — Actor-Based Dashboard
============================================
Launch:  streamlit run scripts/dashboard.py
"""

from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from generator import config

DATA_DIR = config.DATA_DIR / "csv"

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="Inventory Shrinkage Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Data loader (cached) ──────────────────────────────────────
@st.cache_data(show_spinner="Loading data …")
def load(name: str, cols=None) -> pd.DataFrame:
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, usecols=cols, low_memory=False)


def load_all():
    stores    = load("stores")
    skus      = load("skus")
    employees = load("employees")
    movements = load("inventory_movements")
    counts    = load("cycle_counts")
    returns   = load("returns")
    alerts    = load("shrinkage_alerts")
    invs      = load("investigations")
    promos    = load("promotions")
    gt        = load("ground_truth")
    return stores, skus, employees, movements, counts, returns, alerts, invs, promos, gt


# ── Sidebar — store filter ────────────────────────────────────
st.sidebar.title("📦 Inventory Shrinkage")
st.sidebar.markdown("**Actor-based data explorer**")
st.sidebar.divider()

stores, skus, employees, movements, counts, returns, alerts, invs, promos, gt = load_all()

all_stores = sorted(stores["store_id"].tolist()) if not stores.empty else []
selected_store = st.sidebar.selectbox(
    "Filter by Store", ["All Stores"] + all_stores, index=0
)

def filter_store(df, col="store_id"):
    if selected_store == "All Stores" or df.empty or col not in df.columns:
        return df
    return df[df[col] == selected_store]

mov_f   = filter_store(movements)
cnt_f   = filter_store(counts)
ret_f   = filter_store(returns)
alr_f   = filter_store(alerts)
inv_f   = filter_store(invs)
pro_f   = filter_store(promos)

st.sidebar.divider()
st.sidebar.caption(
    f"**Full dataset**\n\n"
    f"- {len(stores):,} stores\n"
    f"- {len(skus):,} SKUs\n"
    f"- {len(movements):,} movements\n"
    f"- {len(alerts):,} alerts\n"
    f"- {len(invs):,} investigations"
)

# ── Tabs — one per actor ──────────────────────────────────────
t1, t2, t3, t4 = st.tabs([
    "🛒  Customer",
    "🏭  Store / Warehouse Operator",
    "📊  Merchandising / Analyst",
    "🔒  Operations Manager",
])

# ═══════════════════════════════════════════════════════════════
# TAB 1 — CUSTOMER
# ═══════════════════════════════════════════════════════════════
with t1:
    st.header("🛒 Customer View")
    st.caption("Returns experience and active promotions.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Returns", f"{len(ret_f):,}")
    c2.metric("Active Promotions", f"{len(pro_f[pro_f['status']=='active']) if not pro_f.empty else 0:,}")
    if not ret_f.empty:
        avg_refund = ret_f["refund_amount"].mean()
        c3.metric("Avg Refund Amount", f"${avg_refund:,.2f}")
    else:
        c3.metric("Avg Refund Amount", "—")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Return Reasons")
        if not ret_f.empty:
            rc = ret_f["reason"].value_counts().reset_index()
            rc.columns = ["reason", "count"]
            fig = px.bar(rc, x="count", y="reason", orientation="h",
                         color="count", color_continuous_scale="Blues",
                         title="Why customers return items")
            fig.update_layout(showlegend=False, yaxis_title="", xaxis_title="Count",
                              coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No return data for selected store.")

    with col_b:
        st.subheader("Returned Item Condition")
        if not ret_f.empty:
            cond = ret_f["condition"].value_counts().reset_index()
            cond.columns = ["condition", "count"]
            fig = px.pie(cond, names="condition", values="count",
                         title="Condition when returned",
                         color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Active Promotions")
    if not pro_f.empty:
        active = pro_f[pro_f["status"] == "active"].copy()
        if not active.empty:
            # Join SKU name
            if not skus.empty:
                active = active.merge(
                    skus[["sku_id","name","category"]], on="sku_id", how="left"
                )
            show_cols = [c for c in ["promo_id","name","category","promo_type",
                                      "discount_pct","start_date","end_date"] if c in active.columns]
            st.dataframe(active[show_cols].sort_values("discount_pct", ascending=False)
                         .head(50).reset_index(drop=True), use_container_width=True)
        else:
            st.info("No active promotions.")
    else:
        st.info("No promotion data.")


# ═══════════════════════════════════════════════════════════════
# TAB 2 — STORE / WAREHOUSE OPERATOR
# ═══════════════════════════════════════════════════════════════
with t2:
    st.header("🏭 Store / Warehouse Operator View")
    st.caption("Day-to-day stock movements, cycle counts, and shrinkage alerts.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Movements", f"{len(mov_f):,}")
    if not mov_f.empty:
        c2.metric("Receipts", f"{(mov_f['movement_type']=='receipt').sum():,}")
        c3.metric("Sales", f"{(mov_f['movement_type']=='sale').sum():,}")
        c4.metric("Shrinkage Events", f"{(mov_f['movement_type']=='shrinkage').sum():,}")
    else:
        c2.metric("Receipts", "—"); c3.metric("Sales", "—"); c4.metric("Shrinkage Events", "—")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Movement Types Breakdown")
        if not mov_f.empty:
            mt = mov_f["movement_type"].value_counts().reset_index()
            mt.columns = ["type", "count"]
            fig = px.bar(mt, x="type", y="count", color="type",
                         color_discrete_sequence=px.colors.qualitative.Set2,
                         title="All movement types")
            fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="Count")
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Movements Over Time (by week)")
        if not mov_f.empty:
            df_ts = mov_f.copy()
            df_ts["week"] = pd.to_datetime(df_ts["timestamp"]).dt.to_period("W").astype(str)
            weekly = df_ts.groupby(["week","movement_type"]).size().reset_index(name="count")
            # top 4 types for readability
            top_types = mov_f["movement_type"].value_counts().head(4).index.tolist()
            weekly = weekly[weekly["movement_type"].isin(top_types)]
            fig = px.line(weekly, x="week", y="count", color="movement_type",
                          title="Weekly movement volume by type")
            fig.update_xaxes(tickangle=45)
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Cycle Count Variances")
    if not cnt_f.empty:
        col_x, col_y = st.columns(2)
        with col_x:
            status_counts = cnt_f["status"].value_counts().reset_index()
            status_counts.columns = ["status", "count"]
            fig = px.pie(status_counts, names="status", values="count",
                         title="Cycle count status distribution",
                         color_discrete_map={
                             "clean":"#2ecc71","variance_low":"#f39c12",
                             "variance_high":"#e74c3c","anomaly":"#8e44ad"})
            st.plotly_chart(fig, use_container_width=True)
        with col_y:
            top_var = cnt_f.nlargest(10, "variance_value")[
                ["count_id","store_id","sku_id","expected_qty","actual_qty",
                 "variance","variance_pct","variance_value","status"]
            ].reset_index(drop=True)
            st.markdown("**Top 10 highest-value variances**")
            st.dataframe(top_var, use_container_width=True)

    st.subheader("Open Shrinkage Alerts")
    if not alr_f.empty:
        open_alr = alr_f[alr_f["status"].isin(["open","under_investigation"])].copy()
        sev_order = {"critical":0,"high":1,"medium":2,"low":3}
        open_alr["_ord"] = open_alr["severity"].map(sev_order)
        open_alr = open_alr.sort_values("_ord").drop(columns="_ord")
        st.dataframe(open_alr.head(50).reset_index(drop=True), use_container_width=True)
    else:
        st.success("No open alerts for selected store.")


# ═══════════════════════════════════════════════════════════════
# TAB 3 — MERCHANDISING / ANALYST
# ═══════════════════════════════════════════════════════════════
with t3:
    st.header("📊 Merchandising / E-commerce Analyst View")
    st.caption("SKU performance, shrinkage by category, and promotion analysis.")

    if not mov_f.empty and not skus.empty:
        mov_sku = mov_f.merge(skus[["sku_id","category","subcategory",
                                     "unit_price","is_high_value"]], on="sku_id", how="left")
    else:
        mov_sku = mov_f.copy()

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Sales Value by SKU Category")
        if not mov_sku.empty and "category" in mov_sku.columns:
            sales_cat = (
                mov_sku[mov_sku["movement_type"] == "sale"]
                .groupby("category")["total_value"].sum()
                .reset_index()
                .sort_values("total_value", ascending=False)
            )
            fig = px.bar(sales_cat, x="category", y="total_value",
                         color="category", title="Total sales value by category ($)",
                         color_discrete_sequence=px.colors.qualitative.Vivid)
            fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="$",
                              xaxis_tickangle=30)
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Shrinkage Value by Category")
        if not mov_sku.empty and "category" in mov_sku.columns:
            shr_cat = (
                mov_sku[mov_sku["movement_type"] == "shrinkage"]
                .groupby("category")["total_value"].sum()
                .reset_index()
                .sort_values("total_value", ascending=False)
            )
            fig = px.bar(shr_cat, x="category", y="total_value",
                         color="category", title="Total shrinkage value by category ($)",
                         color_discrete_sequence=px.colors.qualitative.Bold)
            fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="$",
                              xaxis_tickangle=30)
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Shrinkage vs Sales Ratio by Category")
    if not mov_sku.empty and "category" in mov_sku.columns:
        sales_v = mov_sku[mov_sku["movement_type"]=="sale"].groupby("category")["total_value"].sum()
        shr_v   = mov_sku[mov_sku["movement_type"]=="shrinkage"].groupby("category")["total_value"].sum()
        ratio   = (shr_v / sales_v * 100).reset_index()
        ratio.columns = ["category", "shrinkage_pct_of_sales"]
        ratio = ratio.sort_values("shrinkage_pct_of_sales", ascending=False)
        fig = px.bar(ratio, x="category", y="shrinkage_pct_of_sales",
                     color="shrinkage_pct_of_sales", color_continuous_scale="Reds",
                     title="Shrinkage as % of sales value (lower = better)")
        fig.update_layout(xaxis_tickangle=30, xaxis_title="",
                          yaxis_title="Shrinkage %", coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    col_c, col_d = st.columns(2)
    with col_c:
        st.subheader("Top 10 Shrinkage SKUs (by value)")
        if not mov_sku.empty:
            top_shr = (
                mov_sku[mov_sku["movement_type"]=="shrinkage"]
                .groupby(["sku_id","category"])["total_value"].sum()
                .reset_index()
                .nlargest(10, "total_value")
                .reset_index(drop=True)
            )
            st.dataframe(top_shr, use_container_width=True)

    with col_d:
        st.subheader("High-Value Item Losses")
        if not mov_sku.empty and "is_high_value" in mov_sku.columns:
            hv = mov_sku[
                (mov_sku["movement_type"]=="shrinkage") &
                (mov_sku["is_high_value"]==True)
            ].groupby("category")["total_value"].sum().reset_index()
            hv.columns = ["category","lost_value"]
            fig = px.pie(hv, names="category", values="lost_value",
                         title="High-value shrinkage by category ($)")
            st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# TAB 4 — OPERATIONS MANAGER
# ═══════════════════════════════════════════════════════════════
with t4:
    st.header("🔒 Operations Manager View")
    st.caption("Investigations, severity escalations, store-level KPIs, and anomaly ground truth.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Alerts", f"{len(alr_f):,}")
    if not alr_f.empty:
        critical = (alr_f["severity"]=="critical").sum()
        high     = (alr_f["severity"]=="high").sum()
        c2.metric("Critical Alerts", f"{critical:,}", delta=None)
        c3.metric("High Alerts", f"{high:,}")
    else:
        c2.metric("Critical", "—"); c3.metric("High", "—")
    c4.metric("Investigations", f"{len(inv_f):,}")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Alert Severity Distribution")
        if not alr_f.empty:
            sev = alr_f["severity"].value_counts().reset_index()
            sev.columns = ["severity","count"]
            fig = px.bar(sev, x="severity", y="count", color="severity",
                         color_discrete_map={"critical":"#c0392b","high":"#e67e22",
                                             "medium":"#f1c40f","low":"#2ecc71"},
                         title="Alerts by severity",
                         category_orders={"severity":["critical","high","medium","low"]})
            fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="Count")
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Alert Status")
        if not alr_f.empty:
            st_ = alr_f["status"].value_counts().reset_index()
            st_.columns = ["status","count"]
            fig = px.pie(st_, names="status", values="count",
                         title="Alert resolution status",
                         color_discrete_sequence=px.colors.qualitative.Set3)
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Investigation Findings")
    if not inv_f.empty:
        col_x, col_y = st.columns(2)
        with col_x:
            findings = inv_f["finding"].value_counts().reset_index()
            findings.columns = ["finding","count"]
            fig = px.bar(findings, x="count", y="finding", orientation="h",
                         color="count", color_continuous_scale="Reds",
                         title="Investigation findings")
            fig.update_layout(showlegend=False, yaxis_title="", coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
        with col_y:
            theft_count  = int(inv_f["is_confirmed_theft"].astype(str).str.lower().isin(["true","1"]).sum())
            total_impact = inv_f["financial_impact"].sum()
            st.metric("Confirmed Theft Cases", f"{theft_count:,}")
            st.metric("Total Financial Impact", f"${total_impact:,.0f}")
            closed = inv_f["closed_date"].notna().sum()
            open_  = inv_f["closed_date"].isna().sum()
            st.metric("Closed Investigations", f"{closed:,}")
            st.metric("Open Investigations", f"{open_:,}")

    st.subheader("Alerts by Store (Top 20)")
    if not alerts.empty:
        store_alerts = (
            alerts.groupby("store_id")
            .agg(total=("alert_id","count"),
                 critical=("severity", lambda x: (x=="critical").sum()),
                 financial_impact=("trigger_value","sum"))
            .reset_index()
            .sort_values("total", ascending=False)
            .head(20)
        )
        fig = px.bar(store_alerts, x="store_id", y="total",
                     color="critical", color_continuous_scale="OrRd",
                     title="Alerts per store (coloured by critical count)",
                     hover_data=["critical","financial_impact"])
        fig.update_layout(xaxis_tickangle=45, xaxis_title="Store",
                          yaxis_title="Alert count")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("🔬 Ground-Truth Anomaly Labels")
    if not gt.empty:
        ec_summary = gt.groupby("anomaly_type").size().reset_index(name="count")
        col_p, col_t = st.columns([1, 2])
        with col_p:
            fig = px.pie(ec_summary, names="anomaly_type", values="count",
                         title="Injected anomaly types",
                         color_discrete_sequence=px.colors.qualitative.Prism)
            st.plotly_chart(fig, use_container_width=True)
        with col_t:
            st.dataframe(gt.reset_index(drop=True), use_container_width=True)
    else:
        st.info("No ground-truth data found.")
