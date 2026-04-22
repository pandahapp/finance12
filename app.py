"""
Finance Team Analytics Dashboard
Streamlit + Plotly + Pandas, fully in-memory.
Run: streamlit run app.py
"""
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

# ============ SESSION ============
if "df" not in st.session_state:
    st.session_state.df = None

# ============ HEADER ============
import base64, os as _os
_logo_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "Jahez-Logo-Red-1-scaled.webp")
if _os.path.exists(_logo_path):
    with open(_logo_path, "rb") as _f:
        _logo_b64 = base64.b64encode(_f.read()).decode()
    st.markdown(
        f"""
    <div class="main-header">
        <img src="data:image/webp;base64,{_logo_b64}" style="height:40px; object-fit:contain;" />
        <div>
            <h1 style="margin:0; font-size:24px;">Finance Team Analytics</h1>
            <p style="margin:0; color:#64748b; font-size:13px;">Delivery operations & customer analytics · SQLite database · data persists across sessions</p>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        """
    <div class="main-header">
        <div class="brand-mark">J</div>
        <div>
            <h1 style="margin:0; font-size:24px;">Finance Team Analytics</h1>
            <p style="margin:0; color:#64748b; font-size:13px;">Delivery operations & customer analytics · SQLite database · data persists across sessions</p>
        </div>
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
| **I** | Restaurant ID | | **V** | Commission BHD |
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
    st.markdown(f"**Database:** `{num(len(df))}` orders")
    st.caption(f"{num(df['user_id'].nunique())} customers · {num(df['restaurant_display'].nunique())} restaurants")

    if st.button("🗑️ Clear all data", use_container_width=True):
        clear_all()
        st.session_state.df = None
        st.rerun()

    st.markdown("---")
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
}

filtered = apply_filters(df, filters)

if len(filtered) == 0:
    st.warning("No orders match your filters. Try clearing some.")
    st.stop()

# ============ TABS ============
tab_overview, tab_customers, tab_restaurants, tab_profit, tab_time, tab_pivot, tab_raw = st.tabs(
    ["📊 Overview", "👥 Customers", "🏪 Restaurants", "💰 Profitability", "🕐 Time Analysis", "🔀 Pivot Builder", "📋 Raw Data"]
)

# ============ OVERVIEW ============
with tab_overview:
    kpi = top_line(filtered)

    # Row 1: Core profitability
    st.markdown("##### Core Profitability")
    c = st.columns(4)
    c[0].metric("Total orders", num(kpi["orders"]))
    c[1].metric("GMV", bhd(kpi["gmv"]))
    c[2].metric(
        "Net profit",
        bhd(kpi["profit"]),
        delta=f"{pct(kpi['profit_margin_pct'])} margin",
    )
    c[3].metric("Loss rate", pct(kpi["loss_rate_pct"]))

    c = st.columns(4)
    c[0].metric("Gross revenue", bhd(kpi["gross_revenue"]))
    c[1].metric("Take rate", pct(kpi["take_rate_pct"]))
    c[2].metric("Loss amount", bhd(kpi["loss_amount"]))
    c[3].metric("Break-even order value", bhd(kpi["breakeven_order_value"]))

    # Row 2: Unit economics
    st.markdown("##### Unit Economics")
    c = st.columns(4)
    c[0].metric("AOV", bhd(kpi["aov"]))
    c[1].metric("CPO (3PL)", bhd(kpi["cpo"]))
    c[2].metric("RPO", bhd(kpi["rpo"]))
    c[3].metric("RPO - CPO spread", bhd(kpi["rpo_cpo_spread"]))

    c = st.columns(4)
    c[0].metric("Profit / order", bhd(kpi["profit_per_order"]))
    c[1].metric("Profit / KM", bhd(kpi["profit_per_km"]))
    c[2].metric("Delivery fee coverage", pct(kpi["delivery_fee_coverage_pct"]))
    c[3].metric("Chargeable delivery %", pct(kpi["chargeable_delivery_pct"]))

    # Row 3: Revenue streams
    st.markdown("##### Revenue Streams")
    c = st.columns(4)
    c[0].metric("Commission", bhd(kpi["commission"]))
    c[1].metric("Delivery rev x1.10", bhd(kpi["delivery_rev"]))
    c[2].metric("Rest offer", bhd(kpi["rest_offer"]))
    c[3].metric("3PL cost", bhd(kpi["cost_3pl"]))

    c = st.columns(4)
    c[0].metric("Total VAT", bhd(kpi["total_vat"]))
    c[1].metric("Total discount", bhd(kpi["total_discount"]))
    c[2].metric("Total KM", num(kpi["total_km"]))
    c[3].metric("Organic order %", pct(kpi["organic_order_pct"]))

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
    br_display["Order mix"] = br_display["order_mix_pct"].apply(pct)
    br_display["GMV"] = br_display["gmv"].apply(bhd)
    br_display["RPO"] = br_display["rpo"].apply(bhd)
    br_display["CPO"] = br_display["cpo"].apply(bhd)
    br_display["Avg profit"] = br_display["avg_profit"].apply(bhd)
    br_display["Total profit"] = br_display["total_profit"].apply(bhd)
    br_display["Loss rate"] = br_display["loss_rate"].apply(pct)
    st.dataframe(
        br_display[["bracket", "orders", "Order mix", "GMV", "RPO", "CPO", "Avg profit", "Total profit", "Loss rate"]],
        use_container_width=True,
        hide_index=True,
    )

# ============ CUSTOMERS ============
with tab_customers:
    k = customer_kpis(filtered)

    c = st.columns(4)
    c[0].metric("Total customers", num(k["total_customers"]))
    c[1].metric("New customers", num(k["new_customers"]))
    c[2].metric("Repeat customers", num(k["repeat_customers"]), f"{pct(k['repeat_rate_pct'])} of base")
    c[3].metric("One-time customers", num(k["one_time_customers"]))

    c = st.columns(4)
    c[0].metric("Orders / customer", f"{k['opc']:.2f}")
    c[1].metric("AOV", bhd(k["aov"]))
    c[2].metric("Avg lifetime revenue", bhd(k["avg_lt_rev"]))
    c[3].metric("Avg lifetime profit", bhd(k["avg_lt_profit"]))

    c = st.columns(4)
    c[0].metric("Profitable customers", pct(k["profitable_customer_pct"]))
    c[1].metric("Top 20% rev share", pct(k["top20_rev_concentration_pct"]))
    c[2].metric("Wallet penetration", pct(k["wallet_penetration_pct"]))
    c[3].metric("Benefits pay %", pct(k["benefits_pay_pct"]))

    c = st.columns(4)
    c[0].metric("Discount penetration", pct(k["discount_penetration_pct"]))
    c[1].metric("Avg discount / order", bhd(k["avg_discount_bhd"]))
    c[2].metric("Organic order %", pct(k["organic_order_pct"]))
    c[3].metric("", "")

    c = st.columns(4)
    c[0].metric("Dormant 30d+", pct(k["dormant_30_pct"]))
    c[1].metric("Dormant 60d+", pct(k["dormant_60_pct"]))
    c[2].metric("Dormant 90d+", pct(k["dormant_90_pct"]))
    c[3].metric("", "")

    st.markdown("---")

    col_l, col_r = st.columns(2)

    # RFM pie
    with col_l:
        st.markdown("#### Customer segments (RFM)")
        rfm = rfm_segmentation(filtered)
        if len(rfm) > 0:
            seg_counts = rfm["segment"].value_counts().reset_index()
            seg_counts.columns = ["segment", "count"]
            seg_colors = {
                "Champions": "#10b981", "Loyal": "#3b82f6", "At Risk": "#f59e0b",
                "New": "#8b5cf6", "Lost": "#6b7280", "Potential": "#ec4899",
            }
            fig = px.pie(
                seg_counts, names="segment", values="count",
                color="segment", color_discrete_map=seg_colors, hole=0.45,
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(height=360, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)

    # Pareto
    with col_r:
        st.markdown("#### Pareto: revenue concentration")
        lt = k["lifetimes"].sort_values("revenue", ascending=False).reset_index(drop=True)
        if len(lt) > 0:
            total = lt["revenue"].sum()
            lt["cum_rev_pct"] = lt["revenue"].cumsum() / total * 100 if total else 0
            lt["cust_pct"] = (lt.index + 1) / len(lt) * 100

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=lt["cust_pct"], y=lt["revenue"],
                marker_color="#C0232A", name="Revenue per customer",
            ))
            fig.add_trace(go.Scatter(
                x=lt["cust_pct"], y=lt["cum_rev_pct"],
                mode="lines", line=dict(color="#3b82f6", width=2),
                name="Cumulative %", yaxis="y2",
            ))
            fig.update_layout(
                height=360, margin=dict(l=20, r=20, t=20, b=20),
                xaxis=dict(title="% of customers"),
                yaxis=dict(title="Revenue (BHD)"),
                yaxis2=dict(title="Cumulative %", overlaying="y", side="right", range=[0, 105]),
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig, use_container_width=True)

    # Top / bottom customers
    st.markdown("---")
    col_l, col_r = st.columns(2)

    lt_all = k["lifetimes"]
    with col_l:
        st.markdown("#### 🟢 Top 20 by lifetime profit")
        top = lt_all.nlargest(20, "profit")[["user_id", "orders", "revenue", "profit", "aov"]].copy()
        top["revenue"] = top["revenue"].apply(bhd)
        top["profit"] = top["profit"].apply(bhd)
        top["aov"] = top["aov"].apply(bhd)
        st.dataframe(top, use_container_width=True, hide_index=True)

    with col_r:
        st.markdown("#### 🔴 Top 10 loss-making customers")
        bot = lt_all.nsmallest(10, "profit")[["user_id", "orders", "avg_km", "profit"]].copy()
        bot["avg_km"] = bot["avg_km"].round(1)
        bot["profit"] = bot["profit"].apply(bhd)
        st.dataframe(bot, use_container_width=True, hide_index=True)

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
        total_gmv = rests["gmv"].sum()
        total_profit = rests["profit"].sum()
        total_commission = rests["commission_bhd"].sum()
        total_cost_3pl = rests["cost_3pl"].sum()
        total_net_food = rests["net_food"].sum()
        total_rest_subsidy = rests["rest_subsidy"].sum()
        total_loss_orders = rests["loss_orders"].sum()

        st.markdown("##### Summary")
        c = st.columns(4)
        c[0].metric("Total restaurants", num(len(rests)))
        c[1].metric("Total orders", num(total_orders))
        c[2].metric("Total GMV", bhd(total_gmv))
        c[3].metric("Total profit", bhd(total_profit))

        c = st.columns(4)
        c[0].metric("AOV", bhd(total_net_food / total_orders if total_orders else 0))
        c[1].metric("AOV Profitable", bhd(rests["aov_profitable"].mean()))
        c[2].metric("AOV Loss", bhd(rests["aov_loss"].mean()))
        c[3].metric("AOV Break-even", bhd(rests["aov_breakeven"].mean()))

        c = st.columns(4)
        c[0].metric("Take rate", pct(total_commission / total_gmv * 100 if total_gmv else 0))
        c[1].metric("CPO (3PL)", bhd(total_cost_3pl / total_orders if total_orders else 0))
        c[2].metric("RPO", bhd((total_commission + rests["delivery_rev"].sum() + total_rest_subsidy) / total_orders if total_orders else 0))
        c[3].metric("Profit / order", bhd(total_profit / total_orders if total_orders else 0))

        c = st.columns(4)
        c[0].metric("Profit margin", pct(total_profit / total_gmv * 100 if total_gmv else 0))
        c[1].metric("Loss rate", pct(total_loss_orders / total_orders * 100 if total_orders else 0))
        c[2].metric("Commission yield", pct(total_commission / total_net_food * 100 if total_net_food else 0))
        c[3].metric("Rest subsidy total", bhd(total_rest_subsidy))

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

        # Commission yield chart
        st.markdown("#### Commission yield vs delivery cost ratio (top 15)")
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=top15["restaurant"][::-1], x=top15["commission_yield_pct"][::-1],
            orientation="h", name="Commission yield %", marker_color="#10b981",
        ))
        fig.add_trace(go.Bar(
            y=top15["restaurant"][::-1], x=top15["delivery_cost_ratio_pct"][::-1],
            orientation="h", name="Delivery cost ratio %", marker_color="#ef4444",
        ))
        fig.update_layout(
            height=450, margin=dict(l=20, r=20, t=20, b=20),
            barmode="group", xaxis_title="%",
            legend=dict(orientation="h", y=1.05),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Full table
        st.markdown(f"#### All restaurants ({len(rests)})")
        show = rests.copy()
        show["GMV"] = show["gmv"].apply(bhd)
        show["AOV"] = show["aov"].apply(bhd)
        show["AOV Profitable"] = show["aov_profitable"].apply(bhd)
        show["AOV Loss"] = show["aov_loss"].apply(bhd)
        show["AOV Break-even"] = show["aov_breakeven"].apply(bhd)
        show["Commission %"] = show["avg_commission_pct"].apply(pct)
        show["Commission BHD"] = show["commission_bhd"].apply(bhd)
        show["Yield %"] = show["commission_yield_pct"].apply(pct)
        show["Rest subsidy"] = show["rest_subsidy"].apply(bhd)
        show["Profit"] = show["profit"].apply(bhd)
        show["Margin"] = show["profit_margin_pct"].apply(pct)
        show["Loss %"] = show["loss_order_pct"].apply(pct)
        show["Avg KM"] = show["avg_km"].round(1)
        show["CPO"] = show["cpo_restaurant"].apply(bhd)
        show["BHD/KM"] = show["bhd_per_km"].apply(bhd)
        show["Customers"] = show["total_customers"]
        show["Repeat %"] = show["repeat_rate_pct"].apply(pct)

        st.dataframe(
            show[[
                "restaurant_id", "restaurant", "orders", "Customers", "Repeat %", "GMV",
                "AOV", "AOV Profitable", "AOV Loss", "AOV Break-even",
                "Commission %", "Commission BHD", "Yield %", "Rest subsidy",
                "Profit", "Margin", "Loss %", "Avg KM", "CPO", "BHD/KM",
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
        dow_show["Mix %"] = dow_show["mix_pct"].apply(pct)
        dow_show["GMV"] = dow_show["gmv"].apply(bhd)
        dow_show["Total profit"] = dow_show["profit"].apply(bhd)
        dow_show["Avg profit/order"] = dow_show["avg_profit"].apply(bhd)
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
        "is_wallet", "is_discounted", "is_profitable",
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
        "distance_bracket", "payment_method_clean",
    ]
    cols = st.multiselect(
        "Columns to show", all_cols,
        default=[c for c in default_cols if c in all_cols],
    )

    if cols:
        st.dataframe(filtered[cols], use_container_width=True, hide_index=True)

        csv = filtered[cols].to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download filtered data as CSV", csv, "filtered_orders.csv", "text/csv")

st.markdown("---")
st.caption("Finance Team Analytics · SQLite database · data persists across sessions")
