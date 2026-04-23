"""
Finance Team Analytics Dashboard
Streamlit + Plotly + Pandas, fully in-memory.
Run: streamlit run app.py
"""
import base64
import os as _os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from parser import parse_excel
from db import init_db, insert_orders, load_all_orders, get_uploads, delete_upload, get_total_order_count, clear_all
from metrics import (
    apply_filters,
    bhd,
    bracket_analysis,
    customer_kpis,
    daily_series,
    num,
    pct,
    restaurant_kpis,
    rfm_segmentation,
    time_based_kpis,
    top_line,
)

# Initialize database on startup
init_db()

# ============ CONFIG ============
st.set_page_config(
    page_title="Finance Team Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for a cleaner look
st.markdown(
    """
<style>
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1600px; }
    [data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 600; }
    [data-testid="stMetricLabel"] { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding: 8px 16px; font-size: 14px; }
    .stTabs [aria-selected="true"] { background: #fef2f2; color: #C0232A; border-radius: 6px; }
    h1, h2, h3 { color: #1f2937; }
    .main-header { display:flex; align-items:center; gap:12px; margin-bottom: 0.5rem; }
    .brand-mark { width:36px; height:36px; background:#C0232A; border-radius:8px;
                  display:flex; align-items:center; justify-content:center; color:white;
                  font-weight:700; font-size:18px; }
</style>
""",
    unsafe_allow_html=True,
)

_logo_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "Jahez-Logo-Red-1-scaled.webp")

# ============ PASSWORD GATE ============
def check_password():
    if st.session_state.get("authenticated"):
        return True
    # Hide sidebar and push content to center
    st.markdown(
        """
    <style>
        [data-testid="stSidebar"] { display: none; }
        .block-container { display:flex; justify-content:center; align-items:center; min-height:80vh; }
    </style>
    """,
        unsafe_allow_html=True,
    )
    _, col, _ = st.columns([1, 1, 1])
    with col:
        if _os.path.exists(_logo_path):
            with open(_logo_path, "rb") as _f:
                _b64 = base64.b64encode(_f.read()).decode()
            st.markdown(
                f'<div style="text-align:center;"><img src="data:image/webp;base64,{_b64}" style="height:80px; margin-bottom:8px;" /></div>',
                unsafe_allow_html=True,
            )
        st.markdown('<h3 style="text-align:center; margin-bottom:4px;">Finance Team Analytics</h3>', unsafe_allow_html=True)
        st.markdown('<p style="text-align:center; color:#64748b; font-size:13px; margin-bottom:24px;">Enter password to continue</p>', unsafe_allow_html=True)
        pwd = st.text_input("Password", type="password", placeholder="Enter password...", label_visibility="collapsed")
        if st.button("Login", type="primary", use_container_width=True):
            if pwd == "Jahez@123":
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    return False

if not check_password():
    st.stop()

# ============ SESSION ============
if "df" not in st.session_state:
    st.session_state.df = None

# ============ HEADER ============
if _os.path.exists(_logo_path):
    with open(_logo_path, "rb") as _f:
        _logo_b64 = base64.b64encode(_f.read()).decode()
    st.markdown(
        f"""
    <div class="main-header">
        <img src="data:image/webp;base64,{_logo_b64}" style="height:40px; object-fit:contain;" />
        <h1 style="margin:0; font-size:24px;">Finance Team Analytics</h1>
    </div>
    """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        """
    <div class="main-header">
        <div class="brand-mark">J</div>
        <h1 style="margin:0; font-size:24px;">Finance Team Analytics</h1>
    </div>
    """,
        unsafe_allow_html=True,
    )

# ============ UPLOAD + DATABASE ============
total_in_db = get_total_order_count()

# Upload section — always visible at top
with st.expander("Upload Excel files", expanded=(total_in_db == 0)):
    st.caption("Upload one or more `.xlsx` files. Data is saved permanently in the database.")

    uploaded_files = st.file_uploader(
        "Drop your .xlsx files here",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploaded_files:
        if st.button("Save to database", type="primary", use_container_width=True):
            progress = st.progress(0, text="Processing files...")
            total_rows = 0
            for i, f in enumerate(uploaded_files):
                progress.progress((i) / len(uploaded_files), text=f"Parsing {f.name}...")
                try:
                    parsed = parse_excel(f)
                    if len(parsed) == 0:
                        st.warning(f"`{f.name}` — no orders found, skipped.")
                        continue
                    insert_orders(parsed, f.name)
                    total_rows += len(parsed)
                    st.success(f"`{f.name}` — {num(len(parsed))} orders saved")
                except Exception as e:
                    st.error(f"`{f.name}` — failed: {e}")
            progress.progress(1.0, text="Done!")
            if total_rows > 0:
                st.session_state.df = None  # force reload
                st.rerun()

    # Upload history
    uploads = get_uploads()
    if len(uploads) > 0:
        st.markdown("**Upload history**")
        for _, row in uploads.iterrows():
            col1, col2 = st.columns([5, 1])
            col1.caption(f"`{row['filename']}` — {num(row['rows_inserted'])} rows — {row['uploaded_at']}")
            if col2.button("🗑️", key=f"del_{row['id']}", help=f"Delete {row['filename']}"):
                delete_upload(row["id"])
                st.session_state.df = None
                st.rerun()

    with st.expander("Expected Excel column mapping"):
        st.markdown(
            """
| Col | Field | | Col | Field |
|---|---|---|---|---|
| **C** | Driver ID (empty/1/17/18 = not delivered) | | **V** | Commission BHD |
| **I** | Restaurant ID | | |
| **J** | Restaurant Name | | **Z** | Payment Method (blank = Benefits Pay) |
| **K** | Order ID | | **AB** | Restaurant Delivery Offer |
| **M** | User ID | | **AC** | Discount % |
| **N** | Order Date | | **AD** | Discount BHD |
| **O** | Order Time | | **AF** | KM Delivered (rounded up) |
| **P** | GMV (Customer Payment for Food) | | **AK** | 3PL Cost |
| **Q** | VAT | | | |
| **R** | Amount ex-VAT | | | |
| **S** | Wallet Paid | | | |
| **T** | Delivery Fee (×1.10 = revenue) | | | |
| **U** | Commission % | | | |

**Profit formula:** `Commission (V) + (Delivery Fee (T) × 1.10) + Rest Offer (AB) − 3PL Cost (AK)`
"""
        )

# Load data from database (cache with TTL so filters always work on fresh data)
@st.cache_data(ttl=60)
def _load():
    return load_all_orders()

df = _load()
if st.session_state.df is None:
    st.session_state.df = df

if len(df) == 0:
    st.info("No data in database yet. Upload Excel files above to get started.")
    st.stop()

# ============ DATA LOADED ============

# ---------- SIDEBAR FILTERS ----------
with st.sidebar:
    st.markdown("### Filters")

    # Date range — only consider rows with valid dates
    valid_dates = df["order_date"].dropna()
    if len(valid_dates) > 0:
        min_date = valid_dates.min()
        max_date = valid_dates.max()
        date_range = st.date_input(
            "Date range",
            value=(min_date.date(), max_date.date()),
            min_value=min_date.date(),
            max_value=max_date.date(),
        )
        # Streamlit returns a tuple of 2 when both dates are picked,
        # a tuple of 1 while user is picking the second date,
        # or a single date object. Only filter when we have both.
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            date_from, date_to = date_range
        else:
            # User is mid-selection — don't filter, show all
            date_from, date_to = min_date.date(), max_date.date()
    else:
        date_from = date_to = None

    # Payment methods
    payment_opts = sorted(df["payment_method_clean"].unique().tolist())
    payment_sel = st.multiselect("Payment methods", payment_opts, default=[])

    # Distance brackets
    bracket_opts = ["0-1km", "1-2km", "2-3km", "3-4km", "4-5km", "5km+"]
    bracket_sel = st.multiselect("Distance brackets", bracket_opts, default=[])

    # Restaurants
    rest_opts = sorted(df["restaurant_display"].unique().tolist())
    rest_sel = st.multiselect("Restaurants", rest_opts, default=[])

    # Order ID filter
    order_id_input = st.text_input("Filter by Order ID", "", placeholder="Enter order ID...")

    # User ID filter
    user_id_input = st.text_input("Filter by User ID", "", placeholder="Enter user ID...")

    # Restaurant ID filter
    rest_id_input = st.text_input("Filter by Restaurant ID", "", placeholder="Enter restaurant ID...")

    # Profitability
    prof_sel = st.radio(
        "Profitability",
        ["All orders", "Profitable only", "Loss-making only"],
        horizontal=False,
    )
    prof_filter = None if prof_sel == "All orders" else (prof_sel == "Profitable only")

filters = {
    "date_from": date_from,
    "date_to": date_to,
    "payment_methods": payment_sel,
    "distance_brackets": bracket_sel,
    "restaurants": rest_sel,
    "only_profitable": prof_filter,
    "order_id": order_id_input.strip() if order_id_input.strip() else None,
    "user_id": user_id_input.strip() if user_id_input.strip() else None,
    "restaurant_id": rest_id_input.strip() if rest_id_input.strip() else None,
}

filtered = apply_filters(df, filters)

if len(filtered) == 0:
    st.warning("No orders match your filters. Try clearing some.")
    st.stop()

# ============ TABS ============
tab_overview, tab_customers, tab_restaurants, tab_profit, tab_time, tab_pivot, tab_raw, tab_ratios = st.tabs(
    ["📊 Overview", "👥 Customers", "🏪 Restaurants", "💰 Profitability", "🕐 Time Analysis", "🔀 Pivot Builder", "📋 Raw Data", "📐 Ratios"]
)

# ============ OVERVIEW ============
with tab_overview:
    kpi = top_line(filtered)

    # ── RAW TOTALS ──
    st.markdown("##### Raw Totals")
    c = st.columns(4)
    c[0].metric("Total Orders", num(kpi["orders"]))
    c[1].metric("Delivered Orders", num(kpi["delivered_orders"]))
    c[2].metric("GMV", bhd(kpi["gmv"]))
    c[3].metric("Gross Revenue", bhd(kpi["gross_revenue"]))

    c = st.columns(4)
    c[0].metric("Commission", bhd(kpi["commission"]))
    c[1].metric("Delivery Rev x1.10", bhd(kpi["delivery_rev"]))
    c[2].metric("Rest Offer", bhd(kpi["rest_offer"]))
    c[3].metric("3PL Cost", bhd(kpi["cost_3pl"]))

    c = st.columns(4)
    c[0].metric("Total Discount", bhd(kpi["total_discount"]))
    c[1].metric("Total KM", num(kpi["total_km"]))
    c[2].metric("Discounted Order %", pct(kpi["discount_order_pct"]))
    c[3].metric("Take Rate", pct(kpi["take_rate_pct"]))

    st.markdown("---")

    # ── PROFITABILITY KPIs ──
    st.markdown("##### Profitability")
    c = st.columns(4)
    c[0].metric("Net Profit", bhd(kpi["profit"]))
    c[1].metric("Profit Margin", pct(kpi["profit_margin_pct"]))
    c[2].metric("Loss Rate", pct(kpi["loss_rate_pct"]))
    c[3].metric("Loss Amount", bhd(kpi["loss_amount"]))

    st.markdown("---")

    # ── UNIT ECONOMICS (per-order ratios) ──
    st.markdown("##### Unit Economics")
    c = st.columns(4)
    c[0].metric("AOV", bhd(kpi["aov"]))
    c[1].metric("AOV Profitable", bhd(kpi["aov_profitable"]))
    c[2].metric("AOV Loss", bhd(kpi["aov_loss"]))
    c[3].metric("Profit / Order", bhd(kpi["profit_per_order"]))

    st.markdown("---")

    # ── DELIVERY KPIs (delivered orders only) ──
    st.markdown("##### Delivery KPIs (delivered orders only)")
    c = st.columns(3)
    c[0].metric("CPO (3PL)", bhd(kpi["cpo"]))
    c[1].metric("RPO", bhd(kpi["rpo"]))
    c[2].metric("RPO - CPO Spread", bhd(kpi["rpo_cpo_spread"]))

    c = st.columns(2)
    c[0].metric("CPO Coverage", pct(kpi["cpo_coverage_pct"]))
    c[1].metric("Chargeable Delivery %", pct(kpi["chargeable_delivery_pct"]))

    st.markdown("---")

    col_l, col_r = st.columns(2)

    # Waterfall
    with col_l:
        st.markdown("#### Profitability waterfall")
        wf = go.Figure(
            go.Waterfall(
                x=["Commission", "Delivery rev ×1.10", "Rest offer", "3PL cost", "Net profit"],
                measure=["relative", "relative", "relative", "relative", "total"],
                y=[kpi["commission"], kpi["delivery_rev"], kpi["rest_offer"], -kpi["cost_3pl"], kpi["profit"]],
                text=[
                    f"{kpi['commission']:,.2f}",
                    f"{kpi['delivery_rev']:,.2f}",
                    f"{kpi['rest_offer']:,.2f}",
                    f"-{kpi['cost_3pl']:,.2f}",
                    f"{kpi['profit']:,.2f}",
                ],
                textposition="outside",
                connector={"line": {"color": "#cbd5e1"}},
                increasing={"marker": {"color": "#10b981"}},
                decreasing={"marker": {"color": "#ef4444"}},
                totals={"marker": {"color": "#C0232A"}},
            )
        )
        wf.update_layout(height=360, margin=dict(l=20, r=20, t=20, b=20), yaxis_title="BHD")
        st.plotly_chart(wf, use_container_width=True)

    # Bracket chart
    with col_r:
        st.markdown("#### Profit by distance bracket")
        br = bracket_analysis(filtered)
        fig = go.Figure()
        fig.add_trace(
            go.Bar(name="RPO", x=br["bracket"], y=br["rpo"], marker_color="#93c5fd", yaxis="y")
        )
        fig.add_trace(
            go.Bar(name="CPO", x=br["bracket"], y=br["cpo"], marker_color="#fca5a5", yaxis="y")
        )
        fig.add_trace(
            go.Bar(
                name="Avg profit",
                x=br["bracket"],
                y=br["avg_profit"],
                marker_color=["#10b981" if v >= 0 else "#ef4444" for v in br["avg_profit"]],
                yaxis="y",
            )
        )
        fig.add_trace(
            go.Scatter(
                name="Loss rate %",
                x=br["bracket"],
                y=br["loss_rate"],
                mode="lines+markers",
                line=dict(color="#C0232A", width=3),
                yaxis="y2",
            )
        )
        fig.update_layout(
            height=360,
            margin=dict(l=20, r=20, t=20, b=20),
            yaxis=dict(title="BHD"),
            yaxis2=dict(title="Loss %", overlaying="y", side="right", range=[0, 100]),
            legend=dict(orientation="h", y=1.1),
            barmode="group",
        )
        st.plotly_chart(fig, use_container_width=True)

    # Daily trend
    st.markdown("#### Daily trend")
    daily = daily_series(filtered)
    if len(daily) > 0:
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(name="GMV", x=daily["date"], y=daily["gmv"], marker_color="#93c5fd"))
        fig2.add_trace(
            go.Bar(
                name="Profit",
                x=daily["date"],
                y=daily["profit"],
                marker_color=["#10b981" if v >= 0 else "#ef4444" for v in daily["profit"]],
            )
        )
        fig2.add_trace(
            go.Scatter(
                name="Margin %",
                x=daily["date"],
                y=daily["margin"],
                mode="lines+markers",
                line=dict(color="#C0232A", width=2),
                yaxis="y2",
            )
        )
        fig2.update_layout(
            height=340,
            margin=dict(l=20, r=20, t=10, b=20),
            yaxis=dict(title="BHD"),
            yaxis2=dict(title="Margin %", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.1),
            barmode="group",
        )
        st.plotly_chart(fig2, use_container_width=True)

    # Bracket table
    st.markdown("#### Distance bracket detail")
    br_display = br.copy()
    br_display["Order mix %"] = br_display["order_mix_pct"].round(1).astype(str) + "%"
    br_display["GMV"] = br_display["gmv"].round(3)
    br_display["RPO"] = br_display["rpo"].round(3)
    br_display["CPO"] = br_display["cpo"].round(3)
    br_display["Avg profit"] = br_display["avg_profit"].round(3)
    br_display["Total profit"] = br_display["total_profit"].round(3)
    br_display["Loss rate %"] = br_display["loss_rate"].round(1).astype(str) + "%"
    st.dataframe(
        br_display[["bracket", "orders", "Order mix %", "GMV", "RPO", "CPO", "Avg profit", "Total profit", "Loss rate %"]],
        use_container_width=True,
        hide_index=True,
    )

# ============ CUSTOMERS ============
with tab_customers:
    # Search by User ID
    user_search = st.text_input("Search by User ID", "", placeholder="Enter user ID...", key="user_search")
    if user_search.strip():
        q = user_search.strip().lower()
        cust_df = filtered[filtered["user_id"].astype(str).str.lower().str.contains(q, na=False)]
        if len(cust_df) == 0:
            st.warning(f"No customers match '{user_search}'.")
            st.stop()
    else:
        cust_df = filtered

    k = customer_kpis(cust_df)

    c = st.columns(4)
    c[0].metric("Total customers", num(k["total_customers"]))
    c[1].metric("Repeat customers", num(k["repeat_customers"]), f"{pct(k['repeat_rate_pct'])} of base")
    c[2].metric("One-time customers", num(k["one_time_customers"]))
    c[3].metric("Orders / customer", f"{k['opc']:.2f}")

    c = st.columns(4)
    c[0].metric("AOV", bhd(k["aov"]))
    c[1].metric("AOV Profitable", bhd(k["aov_profitable"]))
    c[2].metric("AOV Loss", bhd(k["aov_loss"]))
    c[3].metric("Profitable customers", pct(k["profitable_customer_pct"]))

    c = st.columns(1)
    c[0].metric("Discounted Order %", pct(k["discount_penetration_pct"]))

    # --- Payment Method Usage ---
    pm_mix = k.get("payment_method_mix", {})
    if pm_mix:
        pm_sorted = sorted(pm_mix.items(), key=lambda x: x[1], reverse=True)
        cols_per_row = 4
        for i in range(0, len(pm_sorted), cols_per_row):
            batch = pm_sorted[i:i + cols_per_row]
            c = st.columns(cols_per_row)
            for j, (method, pct_val) in enumerate(batch):
                c[j].metric(method, pct(pct_val))

    st.markdown("---")

    st.markdown("#### Customer Levels")
    rfm = rfm_segmentation(cust_df)
    if len(rfm) > 0:
        col_l, col_r = st.columns(2)
        level_order = [
            "Level 1 — VIP", "Level 2 — Loyal", "Level 3 — New",
            "Level 4 — At Risk", "Level 5 — Potential", "Level 6 — Inactive",
        ]
        seg_counts = rfm["segment"].value_counts().reset_index()
        seg_counts.columns = ["level", "count"]
        seg_counts["level"] = pd.Categorical(seg_counts["level"], categories=level_order, ordered=True)
        seg_counts = seg_counts.sort_values("level").reset_index(drop=True)
        seg_colors = {
            "Level 1 — VIP": "#10b981",
            "Level 2 — Loyal": "#3b82f6",
            "Level 3 — New": "#8b5cf6",
            "Level 4 — At Risk": "#f59e0b",
            "Level 5 — Potential": "#ec4899",
            "Level 6 — Inactive": "#6b7280",
        }
        with col_l:
            fig = px.pie(
                seg_counts, names="level", values="count",
                color="level", color_discrete_map=seg_colors, hole=0.45,
                category_orders={"level": level_order},
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(height=360, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            seg_detail = seg_counts.copy()
            total_cust = seg_detail["count"].sum()
            seg_detail["% of Customers"] = (seg_detail["count"] / total_cust * 100).round(1).astype(str) + "%"
            seg_detail.columns = ["Level", "Customers", "% of Customers"]
            st.dataframe(seg_detail, use_container_width=True, hide_index=True)

    # Build user → level lookup for the tables below
    user_level = rfm.set_index("user_id")["segment"].to_dict() if len(rfm) > 0 else {}

    # Top / bottom customers
    st.markdown("---")
    col_l, col_r = st.columns(2)

    lt_all = k["lifetimes"]
    with col_l:
        st.markdown("#### Top 20 by lifetime profit")
        top = lt_all.nlargest(20, "profit")[["user_id", "orders", "revenue", "profit", "aov"]].copy()
        top["Level"] = top["user_id"].map(user_level).fillna("—")
        top["revenue"] = top["revenue"].round(3)
        top["profit"] = top["profit"].round(3)
        top["aov"] = top["aov"].round(3)
        st.dataframe(top[["user_id", "Level", "orders", "revenue", "profit", "aov"]], use_container_width=True, hide_index=True)

    with col_r:
        st.markdown("#### Top 10 loss-making customers")
        bot = lt_all.nsmallest(10, "profit")[["user_id", "orders", "avg_km", "profit"]].copy()
        bot["Level"] = bot["user_id"].map(user_level).fillna("—")
        bot["avg_km"] = bot["avg_km"].round(1)
        bot["profit"] = bot["profit"].round(3)
        st.dataframe(bot[["user_id", "Level", "orders", "avg_km", "profit"]], use_container_width=True, hide_index=True)

    # --- Full customer list ---
    st.markdown("---")
    st.markdown(f"#### All Customers ({num(len(lt_all))})")
    st.caption("Full customer list with lifetime metrics. Download as CSV for Excel.")

    all_cust = lt_all.copy()
    all_cust["Level"] = all_cust["user_id"].map(user_level).fillna("—")
    all_cust["first_order"] = all_cust["first_order"].dt.strftime("%Y-%m-%d").fillna("")
    all_cust["last_order"] = all_cust["last_order"].dt.strftime("%Y-%m-%d").fillna("")
    today = pd.Timestamp.today().normalize()
    all_cust["days_since_last"] = (today - pd.to_datetime(all_cust["last_order"], errors="coerce")).dt.days.fillna(0).astype(int)
    all_cust["revenue"] = all_cust["revenue"].round(3)
    all_cust["profit"] = all_cust["profit"].round(3)
    all_cust["aov"] = all_cust["aov"].round(3)
    all_cust["commission"] = all_cust["commission"].round(3)
    all_cust["total_discount"] = all_cust["total_discount"].round(3)
    all_cust["avg_km"] = all_cust["avg_km"].round(1)
    _wallet_pct = np.where(all_cust["orders"] > 0, (all_cust["wallet_orders"] / all_cust["orders"] * 100).round(1), 0)
    all_cust["wallet_pct"] = pd.Series(_wallet_pct, index=all_cust.index).round(1).astype(str) + "%"
    _discount_pct = np.where(all_cust["orders"] > 0, (all_cust["discounted_orders"] / all_cust["orders"] * 100).round(1), 0)
    all_cust["discount_pct"] = pd.Series(_discount_pct, index=all_cust.index).round(1).astype(str) + "%"
    all_cust["profit_per_order"] = np.where(all_cust["orders"] > 0, (all_cust["profit"] / all_cust["orders"]).round(3), 0)
    all_cust["is_profitable"] = np.where(all_cust["profit"] > 0, "Yes", "No")

    show_cols = [
        "user_id", "Level", "orders", "revenue", "profit", "profit_per_order",
        "aov", "commission", "avg_km", "first_order", "last_order",
        "days_since_last", "wallet_orders", "wallet_pct",
        "discounted_orders", "discount_pct", "total_discount", "is_profitable",
    ]
    col_labels = {
        "user_id": "User ID", "Level": "Level", "orders": "Orders",
        "revenue": "GMV", "profit": "Profit", "profit_per_order": "Profit/Order",
        "aov": "AOV", "commission": "Commission", "avg_km": "Avg KM",
        "first_order": "First Order", "last_order": "Last Order",
        "days_since_last": "Days Since Last", "wallet_orders": "Wallet Orders",
        "wallet_pct": "Wallet %", "discounted_orders": "Discount Orders",
        "discount_pct": "Discount %", "total_discount": "Total Discount",
        "is_profitable": "Profitable",
    }

    st.dataframe(
        all_cust[show_cols].rename(columns=col_labels).sort_values("Profit", ascending=False),
        use_container_width=True, hide_index=True,
    )

    csv_cust = all_cust[show_cols].rename(columns=col_labels).sort_values("Profit", ascending=False).to_csv(index=False).encode("utf-8")
    st.download_button("Download all customers as CSV", csv_cust, "all_customers.csv", "text/csv")

# ============ RESTAURANTS ============
with tab_restaurants:
    rests = restaurant_kpis(filtered)
    if len(rests) == 0:
        st.info("No restaurant data after filters.")
    else:
        # Search by name or ID
        rest_search = st.text_input("Search restaurant by name or ID", "", placeholder="Type name or ID...")
        if rest_search.strip():
            q = rest_search.strip().lower()
            rests = rests[
                rests["restaurant"].str.lower().str.contains(q, na=False)
                | rests["restaurant_id"].astype(str).str.lower().str.contains(q, na=False)
            ].reset_index(drop=True)
            if len(rests) == 0:
                st.warning(f"No restaurants match '{rest_search}'.")
                st.stop()

        # --- Restaurant-level KPI summary (aggregated from filtered restaurants) ---
        total_orders = rests["orders"].sum()
        total_delivered = rests["delivered_orders"].sum()
        total_gmv = rests["gmv"].sum()
        total_profit = rests["profit"].sum()
        total_commission = rests["commission_bhd"].sum()
        total_cost_3pl = rests["cost_3pl"].sum()
        total_net_food = rests["net_food"].sum()
        total_rest_subsidy = rests["rest_subsidy"].sum()
        total_loss_orders = rests["loss_orders"].sum()

        st.markdown("##### Summary")
        c = st.columns(5)
        c[0].metric("Total restaurants", num(len(rests)))
        c[1].metric("Total orders", num(total_orders))
        c[2].metric("Delivered orders", num(total_delivered))
        c[3].metric("Total GMV", bhd(total_gmv))
        c[4].metric("Total profit", bhd(total_profit))

        c = st.columns(4)
        c[0].metric("AOV", bhd(total_net_food / total_orders if total_orders else 0))
        c[1].metric("AOV Profitable", bhd(rests["aov_profitable"].mean()))
        c[2].metric("AOV Loss", bhd(rests["aov_loss"].mean()))
        c[3].metric("AOV Break-even", bhd(rests["aov_breakeven"].mean()))

        c = st.columns(4)
        c[0].metric("Take rate", pct(total_commission / total_gmv * 100 if total_gmv else 0))
        c[1].metric("CPO (3PL)", bhd(total_cost_3pl / total_delivered if total_delivered else 0))
        c[2].metric("RPO", bhd((rests["delivery_rev"].sum() + total_rest_subsidy) / total_delivered if total_delivered else 0))
        c[3].metric("Profit / order", bhd(total_profit / total_orders if total_orders else 0))

        c = st.columns(4)
        c[0].metric("Profit margin", pct(total_profit / total_gmv * 100 if total_gmv else 0))
        c[1].metric("Loss rate", pct(total_loss_orders / total_orders * 100 if total_orders else 0))
        c[2].metric("Rest offer total", bhd(total_rest_subsidy))
        c[3].metric("", "")

        c = st.columns(4)
        c[0].metric("Total customers", num(rests["total_customers"].sum()))
        c[1].metric("Avg repeat rate", pct(rests["repeat_rate_pct"].mean()))
        c[2].metric("Avg KM", f"{rests['avg_km'].mean():.1f}")
        c[3].metric("Delivery cost ratio", pct(total_cost_3pl / total_gmv * 100 if total_gmv else 0))

        st.markdown("---")

        top15 = rests.head(15).copy()

        col_l, col_r = st.columns(2)

        with col_l:
            st.markdown("#### Top 15 — GMV vs profit")
            fig = go.Figure()
            fig.add_trace(go.Bar(
                y=top15["restaurant"][::-1], x=top15["gmv"][::-1],
                orientation="h", name="GMV", marker_color="#3b82f6",
            ))
            fig.add_trace(go.Bar(
                y=top15["restaurant"][::-1], x=top15["profit"][::-1],
                orientation="h", name="Profit",
                marker_color=["#10b981" if v >= 0 else "#ef4444" for v in top15["profit"][::-1]],
            ))
            fig.update_layout(
                height=500, margin=dict(l=20, r=20, t=20, b=20),
                barmode="group", xaxis_title="BHD",
                legend=dict(orientation="h", y=1.05),
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            st.markdown("#### BCG matrix: orders vs margin %")
            fig = px.scatter(
                rests, x="orders", y="profit_margin_pct",
                size=rests["profit"].abs() + 1,
                color=rests["profit_margin_pct"] >= 0,
                color_discrete_map={True: "#10b981", False: "#ef4444"},
                hover_name="restaurant",
                hover_data={"orders": True, "gmv": ":.2f", "profit": ":.2f"},
                labels={"orders": "Orders", "profit_margin_pct": "Margin %"},
            )
            fig.update_layout(
                height=500, margin=dict(l=20, r=20, t=20, b=20),
                showlegend=False,
            )
            fig.add_hline(y=0, line_dash="dash", line_color="#9ca3af")
            st.plotly_chart(fig, use_container_width=True)

        # Full table
        st.markdown(f"#### All restaurants ({len(rests)})")
        show = rests.copy()
        show["GMV"] = show["gmv"].round(3)
        show["AOV"] = show["aov"].round(3)
        show["AOV Profitable"] = show["aov_profitable"].round(3)
        show["AOV Loss"] = show["aov_loss"].round(3)
        show["AOV Break-even"] = show["aov_breakeven"].round(3)
        show["Commission %"] = show["avg_commission_pct"].round(1).astype(str) + "%"
        show["Commission BHD"] = show["commission_bhd"].round(3)
        show["Rest Offer"] = show["rest_subsidy"].round(3)
        show["Profit"] = show["profit"].round(3)
        show["Margin %"] = show["profit_margin_pct"].round(1).astype(str) + "%"
        show["Loss %"] = show["loss_order_pct"].round(1).astype(str) + "%"
        show["Avg KM"] = show["avg_km"].round(1)
        show["CPO"] = show["cpo_restaurant"].round(3)
        show["BHD/KM"] = show["bhd_per_km"].round(3)
        show["Customers"] = show["total_customers"]
        show["Repeat %"] = show["repeat_rate_pct"].round(1).astype(str) + "%"

        st.dataframe(
            show[[
                "restaurant_id", "restaurant", "orders", "Customers", "Repeat %", "GMV",
                "AOV", "AOV Profitable", "AOV Loss", "AOV Break-even",
                "Commission %", "Commission BHD", "Rest Offer",
                "Profit", "Margin %", "Loss %", "Avg KM", "CPO", "BHD/KM",
            ]].rename(columns={"restaurant_id": "ID"}),
            use_container_width=True, hide_index=True,
        )

# ============ PROFITABILITY ============
with tab_profit:
    kpi = top_line(filtered)
    br = bracket_analysis(filtered)

    c = st.columns(4)
    c[0].metric("Net profit", bhd(kpi["profit"]))
    c[1].metric("Profit margin", pct(kpi["profit_margin_pct"]))
    c[2].metric("Loss rate", pct(kpi["loss_rate_pct"]))
    c[3].metric("Profit / order", bhd(kpi["profit_per_order"]))

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("#### Profit components")
        comp = pd.DataFrame({
            "Component": ["Commission", "Delivery rev ×1.10", "Rest offer", "3PL cost"],
            "Value": [kpi["commission"], kpi["delivery_rev"], kpi["rest_offer"], -kpi["cost_3pl"]],
        })
        fig = px.bar(
            comp, x="Component", y="Value",
            color="Value", color_continuous_scale=["#ef4444", "#fef2f2", "#10b981"],
        )
        fig.update_layout(height=340, margin=dict(l=20, r=20, t=20, b=20), showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown("#### Loss rate by bracket")
        fig = px.bar(
            br, x="bracket", y="loss_rate",
            color="loss_rate", color_continuous_scale=["#10b981", "#f59e0b", "#ef4444"],
            text=br["loss_rate"].apply(lambda x: f"{x:.1f}%"),
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(height=340, margin=dict(l=20, r=20, t=20, b=20), yaxis_title="Loss rate %", coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    # Distribution of profit per order
    st.markdown("#### Distribution of profit per order")
    fig = px.histogram(
        filtered, x="order_profit", nbins=50,
        color_discrete_sequence=["#C0232A"],
    )
    fig.add_vline(x=0, line_dash="dash", line_color="#1f2937", annotation_text="Breakeven")
    fig.update_layout(height=320, margin=dict(l=20, r=20, t=20, b=20), xaxis_title="Profit per order (BHD)", yaxis_title="Count")
    st.plotly_chart(fig, use_container_width=True)

    # Scenario sensitivity
    st.markdown("---")
    st.markdown("#### 🎯 Scenario sensitivity")
    st.caption("Simulate profit impact of changes to delivery fee or 3PL cost.")

    s1, s2 = st.columns(2)
    delivery_bump = s1.slider("Increase delivery fee by %", -50, 100, 0, 5)
    cost_change = s2.slider("Change 3PL cost by %", -50, 100, 0, 5)

    scen_delivery_rev = filtered["delivery_fee_charged"] * (1 + delivery_bump / 100) * 1.10
    scen_3pl = filtered["cost_3pl"] * (1 + cost_change / 100)
    scen_profit = (
        filtered["commission_bhd"]
        + scen_delivery_rev
        + filtered["restaurant_delivery_offer"]
        - scen_3pl
    )
    scen_total = scen_profit.sum()
    scen_loss = (scen_profit <= 0).sum() / len(filtered) * 100

    sc = st.columns(3)
    sc[0].metric("Baseline profit", bhd(kpi["profit"]))
    sc[1].metric(
        "Scenario profit",
        bhd(scen_total),
        delta=bhd(scen_total - kpi["profit"]),
    )
    sc[2].metric("Scenario loss rate", pct(scen_loss), delta=f"{scen_loss - kpi['loss_rate_pct']:+.1f}pp")

# ============ TIME ANALYSIS ============
with tab_time:
    tk = time_based_kpis(filtered)

    # KPI row
    c = st.columns(4)
    c[0].metric("Peak hour share", pct(tk["peak_hour_share_pct"]))
    c[1].metric("Peak profit/order", bhd(tk["peak_profit_per_order"]))
    c[2].metric("Off-peak profit/order", bhd(tk["offpeak_profit_per_order"]))
    c[3].metric("Peak vs off-peak ratio", f"{tk['peak_vs_offpeak_ratio']:.2f}x")

    st.caption("Peak hours: 12-14 (lunch) & 19-22 (dinner)")

    st.markdown("---")
    col_l, col_r = st.columns(2)

    # Hourly distribution
    with col_l:
        st.markdown("#### Hourly order distribution")
        hourly = tk["hourly_mix"]
        if len(hourly) > 0:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=hourly["hour"], y=hourly["orders"],
                name="Orders", marker_color="#93c5fd",
            ))
            fig.add_trace(go.Scatter(
                x=hourly["hour"], y=hourly["avg_profit"],
                name="Avg profit/order", mode="lines+markers",
                line=dict(color="#C0232A", width=2), yaxis="y2",
            ))
            fig.update_layout(
                height=360, margin=dict(l=20, r=20, t=20, b=20),
                xaxis=dict(title="Hour of day", dtick=1),
                yaxis=dict(title="Orders"),
                yaxis2=dict(title="Avg profit (BHD)", overlaying="y", side="right"),
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig, use_container_width=True)

    # Day of week
    with col_r:
        st.markdown("#### Day-of-week order mix")
        dow = tk["dow_mix"]
        if len(dow) > 0:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=dow["day_of_week"].astype(str), y=dow["orders"],
                name="Orders", marker_color="#93c5fd",
                text=dow["mix_pct"].apply(lambda x: f"{x:.1f}%"),
                textposition="outside",
            ))
            fig.add_trace(go.Scatter(
                x=dow["day_of_week"].astype(str), y=dow["avg_profit"],
                name="Avg profit/order", mode="lines+markers",
                line=dict(color="#C0232A", width=2), yaxis="y2",
            ))
            fig.update_layout(
                height=360, margin=dict(l=20, r=20, t=20, b=20),
                xaxis=dict(title="Day"),
                yaxis=dict(title="Orders"),
                yaxis2=dict(title="Avg profit (BHD)", overlaying="y", side="right"),
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig, use_container_width=True)

    # Weekly active customers
    st.markdown("#### Weekly Active Customers (WAC)")
    wac = tk["wac"]
    if len(wac) > 0:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=wac["year_week"], y=wac["orders"],
            name="Orders", marker_color="#93c5fd",
        ))
        fig.add_trace(go.Scatter(
            x=wac["year_week"], y=wac["active_customers"],
            name="Active customers", mode="lines+markers",
            line=dict(color="#C0232A", width=2), yaxis="y2",
        ))
        fig.update_layout(
            height=360, margin=dict(l=20, r=20, t=20, b=20),
            xaxis=dict(title="Week"),
            yaxis=dict(title="Orders"),
            yaxis2=dict(title="Active customers", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Not enough date data for weekly analysis.")

    # Day-of-week detail table
    if len(dow) > 0:
        st.markdown("#### Day-of-week detail")
        dow_show = dow.copy()
        dow_show["Mix %"] = dow_show["mix_pct"].round(1).astype(str) + "%"
        dow_show["GMV"] = dow_show["gmv"].round(3)
        dow_show["Total profit"] = dow_show["profit"].round(3)
        dow_show["Avg profit/order"] = dow_show["avg_profit"].round(3)
        st.dataframe(
            dow_show[["day_of_week", "orders", "Mix %", "GMV", "Total profit", "Avg profit/order"]],
            use_container_width=True, hide_index=True,
        )

# ============ PIVOT ============
with tab_pivot:
    st.markdown("#### Pivot builder")
    st.caption("Pick rows, columns, values and an aggregation. Acts like a Tableau pivot.")

    # Available dimensions and measures
    dims = [
        "restaurant_display", "user_id", "date_str", "month", "day_of_week",
        "hour", "daypart", "distance_bracket", "payment_method_clean",
        "is_wallet", "is_discounted", "is_profitable", "is_delivered",
    ]
    measures = {
        "order_profit": "Order profit",
        "total_with_vat_delivery": "GMV",
        "amount_ex_vat": "Amount ex-VAT",
        "commission_bhd": "Commission BHD",
        "commission_pct": "Commission %",
        "delivery_revenue": "Delivery revenue ×1.10",
        "delivery_fee_charged": "Delivery fee charged",
        "restaurant_delivery_offer": "Rest offer",
        "cost_3pl": "3PL cost",
        "discount_amount": "Discount BHD",
        "km_billable": "KM",
        "profit_margin_pct": "Profit margin %",
        "order_id": "Order count",
    }
    aggs = {
        "Sum": "sum", "Average": "mean", "Median": "median",
        "Min": "min", "Max": "max", "Count": "count",
        "Count distinct": "nunique", "Std dev": "std",
    }

    c = st.columns(4)
    row_sel = c[0].multiselect("Rows", dims, default=["distance_bracket"])
    col_sel = c[1].multiselect("Columns", dims, default=["daypart"])
    val_sel = c[2].selectbox("Value", list(measures.keys()), format_func=lambda x: measures[x], index=0)
    agg_sel = c[3].selectbox("Aggregation", list(aggs.keys()), index=0)

    show_total = st.checkbox("Show totals", value=True)
    show_heatmap = st.checkbox("Heatmap coloring", value=True)

    if row_sel:
        try:
            pivot_kwargs = dict(
                data=filtered, index=row_sel, values=val_sel, aggfunc=aggs[agg_sel],
            )
            if col_sel:
                pivot_kwargs["columns"] = col_sel
            if show_total:
                pivot_kwargs["margins"] = True
                pivot_kwargs["margins_name"] = "Total"
            pv = pd.pivot_table(**pivot_kwargs).round(3)

            st.markdown(f"**{aggs[agg_sel].title()} of `{measures[val_sel]}`** by **{' × '.join(row_sel)}**"
                        + (f" across **{' × '.join(col_sel)}**" if col_sel else ""))

            if show_heatmap and val_sel != "order_id":
                styled = pv.style.background_gradient(cmap="RdYlGn", axis=None).format("{:,.3f}")
                st.dataframe(styled, use_container_width=True)
            else:
                st.dataframe(pv.style.format("{:,.3f}" if val_sel != "order_id" else "{:,.0f}"),
                             use_container_width=True)

            # Download
            csv = pv.to_csv().encode("utf-8")
            st.download_button("📥 Download pivot as CSV", csv, "pivot.csv", "text/csv")

        except Exception as e:
            st.error(f"Could not build pivot: {e}")
    else:
        st.info("Pick at least one field for Rows.")

    st.markdown("---")
    st.markdown("#### Available fields")
    fc = st.columns(3)
    with fc[0]:
        st.markdown("**Dimensions**")
        st.markdown("\n".join(f"- `{d}`" for d in dims))
    with fc[1]:
        st.markdown("**Measures**")
        st.markdown("\n".join(f"- `{k}` — {v}" for k, v in measures.items()))
    with fc[2]:
        st.markdown("**Aggregations**")
        st.markdown("\n".join(f"- {k}" for k in aggs.keys()))

# ============ RAW DATA ============
with tab_raw:
    st.markdown(f"#### Raw enriched data ({num(len(filtered))} rows)")
    st.caption("This is the enriched view with all derived fields. Use the search on any column.")

    # Let user pick columns
    all_cols = filtered.columns.tolist()
    default_cols = [
        "order_id", "user_id", "restaurant_display", "date_str", "order_time",
        "total_with_vat_delivery", "commission_bhd", "delivery_revenue",
        "restaurant_delivery_offer", "cost_3pl", "order_profit",
        "distance_bracket", "payment_method_clean", "driver_id", "is_delivered",
    ]
    cols = st.multiselect(
        "Columns to show", all_cols,
        default=[c for c in default_cols if c in all_cols],
    )

    if cols:
        st.dataframe(filtered[cols], use_container_width=True, hide_index=True)

        csv = filtered[cols].to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download filtered data as CSV", csv, "filtered_orders.csv", "text/csv")

# ============ RATIOS ============
with tab_ratios:
    st.markdown("#### Ratio Definitions & Formulas")
    st.caption("How each metric is calculated. D.Orders = Delivered Orders only (excludes virtual drivers 1, 17, 18 and orders with no driver).")

    st.markdown("---")

    # --- RAW TOTALS ---
    st.markdown("##### Raw Totals")
    st.markdown("""
| Metric | Formula | Notes |
|---|---|---|
| **Total Orders** | `COUNT(all orders)` | Every row in the dataset |
| **Delivered Orders** | `COUNT(orders WHERE driver NOT IN [empty, 1, 17, 18])` | Real driver assigned |
| **GMV** | `SUM(Column P)` | Customer payment for food incl. VAT & delivery |
| **Commission** | `SUM(Column V)` | Commission in BHD |
| **Delivery Rev x1.10** | `SUM(Column T × 1.10)` — D.Orders only | Delivery fee charged × 1.10, delivered orders only |
| **Rest Offer** | `SUM(Column AB)` | Restaurant delivery offer subsidy |
| **3PL Cost** | `SUM(Column AK)` — D.Orders only | Third-party logistics cost, delivered orders only |
| **Gross Revenue** | `Commission + Delivery Rev + Rest Offer` | Total revenue before 3PL cost |
| **Total Discount** | `SUM(Column AD)` | All discounts given |
| **Total KM** | `SUM(CEIL(Column AF))` — D.Orders only | Each order's KM rounded up to whole number, delivered only |
""")

    st.markdown("---")

    # --- PROFITABILITY ---
    st.markdown("##### Profitability")
    st.markdown("""
| Metric | Formula | Notes |
|---|---|---|
| **Net Profit** | `Commission + Delivery Rev x1.10 + Rest Offer − 3PL Cost` | Core profit formula |
| **Profit Margin %** | `(Net Profit ÷ GMV) × 100` | How much profit per BHD of GMV |
| **Loss Rate %** | `(Orders WHERE profit ≤ 0 ÷ Total Orders) × 100` | % of orders that lose money |
| **Loss Amount** | `SUM(profit) WHERE profit ≤ 0` | Total BHD lost on unprofitable orders |
""")

    st.markdown("---")

    # --- UNIT ECONOMICS ---
    st.markdown("##### Unit Economics")
    st.markdown("""
| Metric | Formula | Notes |
|---|---|---|
| **AOV** | `GMV ÷ Total Orders` | Average order value |
| **Profit / Order** | `Net Profit ÷ Total Orders` | Average profit per order (all orders) |
| **Break-even Order Value** | `(Avg 3PL per D.Order) ÷ (Take Rate% + Avg Delivery Fee Ratio)` | Minimum order value to break even |
| **Discounted Order %** | `(Orders with discount > 0 ÷ Total Orders) × 100` | % of orders where a discount was applied |
""")

    st.markdown("---")

    # --- DELIVERY KPIs ---
    st.markdown("##### Delivery KPIs (delivered orders only)")
    st.markdown("""
| Metric | Formula | Notes |
|---|---|---|
| **CPO (3PL)** | `3PL Cost ÷ Delivered Orders` | Cost per delivered order |
| **RPO** | `(Delivery Rev x1.10 + Rest Offer) ÷ Delivered Orders` | Delivery revenue per delivered order |
| **RPO − CPO Spread** | `RPO − CPO` | Margin per delivered order |
| **CPO Coverage** | `(RPO ÷ CPO) × 100` | How much delivery revenue covers 3PL cost |
| **Chargeable Delivery %** | `(D.Orders with delivery fee > 0 ÷ Delivered Orders) × 100` | % of delivered orders that charge delivery |
| **Take Rate %** | `(Commission ÷ GMV) × 100` | Commission as % of GMV |
""")

    st.markdown("---")

    # --- ORDER-LEVEL PROFIT ---
    st.markdown("##### Order-Level Profit (per row)")
    st.markdown("""
| Field | Formula |
|---|---|
| **Order Profit** | `Commission(V) + (Delivery Fee(T) × 1.10) + Rest Offer(AB) − 3PL Cost(AK)` |
| **Profit Margin %** | `(Order Profit ÷ GMV(P)) × 100` |
| **Is Profitable** | `1 if Order Profit > 0, else 0` |
| **KM Billable** | `CEIL(Column AF)` — rounded up to whole number |
| **Distance Bracket** | `0-1km, 1-2km, 2-3km, 3-4km, 4-5km, 5km+` based on KM Billable |
| **Is Delivered** | `1 if driver exists AND driver NOT IN [1, 17], else 0 (driver 18 removed entirely)` |
""")

    st.markdown("---")

    # --- CUSTOMER KPIs ---
    st.markdown("##### Customer KPIs")
    st.markdown("""
| Metric | Formula |
|---|---|
| **Total Customers** | `COUNT(DISTINCT user_id)` |
| **Repeat Customers** | `Customers with ≥ 2 orders` |
| **Repeat Rate %** | `(Repeat Customers ÷ Total Customers) × 100` |
| **Orders / Customer** | `Total Orders ÷ Total Customers` |
| **AOV** | `GMV ÷ Total Orders` |
| **AOV Profitable** | `AVG(GMV) of profitable orders` |
| **AOV Loss** | `AVG(GMV) of loss-making orders` |
| **Profitable Customer %** | `(Customers with total profit > 0 ÷ Total Customers) × 100` |
| **Discounted Order %** | `(Orders with discount > 0 ÷ Total Orders) × 100` |
| **Payment Method %** | `(Orders with payment method X ÷ Total Orders) × 100` |
""")

    st.markdown("---")

    # --- CUSTOMER LEVELS ---
    st.markdown("##### Customer Levels (RFM Segmentation)")
    st.markdown("""
Each customer is scored on 3 dimensions using **quintiles** (1–5 scale):

| Dimension | What it measures | How it's scored |
|---|---|---|
| **R — Recency** | Days since last order | Fewer days = higher score (5 = most recent) |
| **F — Frequency** | Total number of orders | More orders = higher score (5 = most frequent) |
| **M — Monetary** | Total revenue (GMV) | Higher revenue = higher score (5 = highest spender) |

Customers are split into 5 equal groups (quintiles) for each dimension. A customer in the top 20% for frequency gets F=5, bottom 20% gets F=1.

**Level assignment** is based on Recency (R) and Frequency (F) scores:

| Level | Name | Rule | Who they are |
|---|---|---|---|
| **Level 1** | VIP | R ≥ 4 AND F ≥ 4 | Ordered recently AND order often — best customers |
| **Level 2** | Loyal | R ≥ 3 AND F ≥ 3 | Fairly recent AND fairly frequent — solid base |
| **Level 3** | New | R ≥ 4 AND F ≤ 2 | Ordered recently BUT only 1-2 times — just joined |
| **Level 4** | At Risk | R ≤ 2 AND F ≥ 3 | Used to order often BUT haven't ordered recently — slipping away |
| **Level 5** | Potential | R ≥ 3 AND F ≤ 2 | Somewhat recent, low frequency — could grow |
| **Level 6** | Inactive | R ≤ 2 AND F ≤ 2 | Haven't ordered recently AND rarely ordered — disengaged |
""")

    st.markdown("---")

    # --- RESTAURANT KPIs ---
    st.markdown("##### Restaurant KPIs")
    st.markdown("""
| Metric | Formula |
|---|---|
| **Rest Offer** | `SUM(Column AB)` per restaurant |
| **Delivery Cost Ratio %** | `(3PL Cost ÷ GMV) × 100` |
| **Profit Margin %** | `(Profit ÷ GMV) × 100` |
| **Loss Order %** | `(Loss-making orders ÷ Total Orders) × 100` |
| **CPO (Restaurant)** | `3PL Cost ÷ Delivered Orders` per restaurant |
| **BHD / KM** | `GMV ÷ Total KM` per restaurant |
| **Repeat Rate %** | `(Customers with ≥ 2 orders at restaurant ÷ Total Customers) × 100` |
| **AOV Break-even** | `(Avg CPO − Avg Delivery Rev − Avg Rest Offer) ÷ (Avg Commission Rate ÷ 100)` |
""")

    st.markdown("---")

    # --- EXCEL COLUMN REFERENCE ---
    st.markdown("##### Excel Column Reference")
    st.markdown("""
| Column | Field |
|---|---|
| **C** | Driver ID (empty / 1 / 17 / 18 = not delivered) |
| **I** | Restaurant ID |
| **J** | Restaurant Name |
| **K** | Order ID |
| **M** | User ID |
| **N** | Order Date |
| **O** | Order Time |
| **P** | GMV (Customer Payment for Food) |
| **Q** | VAT |
| **R** | Amount ex-VAT |
| **S** | Wallet Paid |
| **T** | Delivery Fee |
| **U** | Commission % |
| **V** | Commission BHD |
| **Z** | Payment Method (blank = Benefits Pay) |
| **AB** | Restaurant Delivery Offer |
| **AC** | Discount % |
| **AD** | Discount BHD |
| **AF** | KM Delivered |
| **AK** | 3PL Cost |
""")

st.markdown("---")
st.caption("Finance Team Analytics")
