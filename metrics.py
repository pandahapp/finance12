"""
All KPI calculations and segmentations.
Every function takes an enriched DataFrame and returns either a scalar dict,
a Series, or a DataFrame.
"""
from datetime import datetime

import numpy as np
import pandas as pd


# ---------- formatting helpers ----------
def bhd(n):
    return f"{(n or 0):,.3f} BHD"


def pct(n):
    return f"{(n or 0):.1f}%"


def num(n):
    return f"{int(n or 0):,}"


# ---------- filters ----------
def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    out = df.copy()
    # Drop rows with no valid date before filtering
    out = out[out["order_date"].notna()]

    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    if date_from is not None:
        out = out[out["order_date"] >= pd.Timestamp(date_from).normalize()]
    if date_to is not None:
        # Include the entire end date (up to 23:59:59)
        out = out[out["order_date"] <= pd.Timestamp(date_to).normalize()]
    if filters.get("payment_methods"):
        out = out[out["payment_method_clean"].isin(filters["payment_methods"])]
    if filters.get("distance_brackets"):
        out = out[out["distance_bracket"].isin(filters["distance_brackets"])]
    if filters.get("restaurants"):
        out = out[out["restaurant_display"].isin(filters["restaurants"])]
    if filters.get("order_id"):
        out = out[out["order_id"].astype(str).str.contains(filters["order_id"], case=False, na=False)]
    if filters.get("user_id"):
        out = out[out["user_id"].astype(str).str.contains(filters["user_id"], case=False, na=False)]
    if filters.get("restaurant_id"):
        out = out[out["restaurant_id"].astype(str).str.contains(filters["restaurant_id"], case=False, na=False)]
    only_prof = filters.get("only_profitable")
    if only_prof is True:
        out = out[out["is_profitable"] == 1]
    elif only_prof is False:
        out = out[out["is_profitable"] == 0]
    return out.reset_index(drop=True)


# ---------- top line ----------
def top_line(df: pd.DataFrame) -> dict:
    _zero_keys = [
        "orders", "delivered_orders", "gmv", "net_food", "commission", "delivery_rev",
        "rest_offer", "cost_3pl", "profit", "profit_margin_pct",
        "loss_rate_pct", "loss_amount", "aov", "aov_profitable", "aov_loss", "cpo", "rpo",
        "rpo_cpo_spread", "profit_per_order", "profit_per_km",
        "total_vat", "total_discount", "total_km", "bhd_per_km",
        "take_rate_pct", "gross_revenue",
        "cpo_coverage_pct", "chargeable_delivery_pct",
        "breakeven_order_value", "discount_order_pct",
    ]
    if len(df) == 0:
        return {k: 0 for k in _zero_keys}

    n = len(df)
    # Delivered orders — used for delivery-related ratios (3PL, KM, CPO, RPO)
    delivered = df[df["is_delivered"] == 1] if "is_delivered" in df.columns else df
    nd = len(delivered)

    gmv = df["total_with_vat_delivery"].sum()
    net_food = df["amount_ex_vat"].sum()
    commission = df["commission_bhd"].sum()
    delivery_rev = delivered["delivery_revenue"].sum()
    rest_offer = df["restaurant_delivery_offer"].sum()
    cost_3pl = delivered["cost_3pl"].sum()
    profit = commission + delivery_rev + rest_offer - cost_3pl
    gross_revenue = commission + delivery_rev + rest_offer
    loss_mask = df["is_profitable"] == 0
    loss_orders = loss_mask.sum()
    loss_amount = df.loc[loss_mask, "order_profit"].sum()
    total_km = delivered["km_billable"].sum()

    take_rate_pct = (commission / gmv * 100) if gmv else 0
    chargeable = (delivered["delivery_fee_charged"] > 0).sum()
    chargeable_delivery_pct = (chargeable / nd * 100) if nd else 0

    # Break-even uses delivered orders for cost average
    avg_3pl = cost_3pl / nd if nd else 0
    del_subset = delivered[delivered["total_with_vat_delivery"] > 0]
    avg_del_ratio = (del_subset["delivery_fee_charged"] / del_subset["total_with_vat_delivery"]).mean() if len(del_subset) else 0
    avg_del_ratio = avg_del_ratio if pd.notna(avg_del_ratio) else 0
    take_rate_dec = take_rate_pct / 100
    denom = take_rate_dec + avg_del_ratio
    breakeven_ov = (avg_3pl / denom) if denom > 0 else 0

    discounted_orders = (df["is_discounted"] == 1).sum()
    discount_order_pct = (discounted_orders / n * 100) if n else 0

    # CPO and RPO based on delivered orders only
    cpo = cost_3pl / nd if nd else 0
    rpo = (delivery_rev + rest_offer) / nd if nd else 0
    cpo_coverage_pct = (rpo / cpo * 100) if cpo else 0

    return {
        "orders": n,
        "delivered_orders": nd,
        "gmv": gmv,
        "net_food": net_food,
        "commission": commission,
        "delivery_rev": delivery_rev,
        "rest_offer": rest_offer,
        "cost_3pl": cost_3pl,
        "gross_revenue": gross_revenue,
        "profit": profit,
        "profit_margin_pct": (profit / gmv * 100) if gmv else 0,
        "loss_rate_pct": (loss_orders / n * 100) if n else 0,
        "loss_amount": loss_amount,
        "aov": gmv / n if n else 0,
        "aov_profitable": df.loc[df["is_profitable"] == 1, "total_with_vat_delivery"].mean() if (df["is_profitable"] == 1).any() else 0,
        "aov_loss": df.loc[df["is_profitable"] == 0, "total_with_vat_delivery"].mean() if (df["is_profitable"] == 0).any() else 0,
        "cpo": cpo,
        "rpo": rpo,
        "rpo_cpo_spread": rpo - cpo,
        "profit_per_order": profit / n if n else 0,
        "profit_per_km": profit / total_km if total_km else 0,
        "total_vat": df["vat_amount"].sum(),
        "total_discount": df["discount_amount"].sum(),
        "total_km": total_km,
        "bhd_per_km": gmv / total_km if total_km else 0,
        "take_rate_pct": take_rate_pct,
        "cpo_coverage_pct": cpo_coverage_pct,
        "chargeable_delivery_pct": chargeable_delivery_pct,
        "breakeven_order_value": breakeven_ov,
        "discount_order_pct": discount_order_pct,
    }


# ---------- customer lifetimes ----------
def customer_lifetimes(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) == 0:
        return pd.DataFrame()
    grp = df.groupby("user_id")
    lt = grp.agg(
        orders=("order_id", "count"),
        revenue=("total_with_vat_delivery", "sum"),
        profit=("order_profit", "sum"),
        net_food=("amount_ex_vat", "sum"),
        commission=("commission_bhd", "sum"),
        first_order=("order_date", "min"),
        last_order=("order_date", "max"),
        wallet_orders=("is_wallet", "sum"),
        discounted_orders=("is_discounted", "sum"),
        total_discount=("discount_amount", "sum"),
        avg_km=("km_billable", "mean"),
    ).reset_index()
    lt["aov"] = lt["revenue"] / lt["orders"]
    return lt


def customer_kpis(df: pd.DataFrame) -> dict:
    lt = customer_lifetimes(df)
    n = len(df)
    users = len(lt)

    if users == 0:
        return {k: 0 for k in [
            "total_customers", "new_customers", "repeat_customers", "one_time_customers",
            "repeat_rate_pct", "opc", "aov", "avg_lt_rev", "avg_lt_profit",
            "profitable_customer_pct", "wallet_penetration_pct",
            "benefits_pay_pct", "discount_penetration_pct", "avg_discount_bhd",
            "top20_rev_concentration_pct", "dormant_30_pct", "dormant_60_pct",
            "dormant_90_pct",
        ]} | {"lifetimes": lt}

    repeat = int((lt["orders"] >= 2).sum())
    profitable = int((lt["profit"] > 0).sum())
    total_rev = lt["revenue"].sum()
    top20_n = max(1, int(np.ceil(users * 0.2)))
    top20_rev = lt.nlargest(top20_n, "revenue")["revenue"].sum()

    today = pd.Timestamp.today().normalize()
    days_since = (today - lt["last_order"]).dt.days.fillna(999)

    discounted = df[df["is_discounted"] == 1]
    avg_disc = discounted["discount_amount"].mean() if len(discounted) else 0

    # New customers: first order in the filtered period
    min_date = df["order_date"].min()
    # Use all data to find global first orders, then count those whose first order >= period start
    new_customers = int((lt["first_order"] >= min_date).sum()) if pd.notna(min_date) else 0

    return {
        "total_customers": users,
        "new_customers": new_customers,
        "repeat_customers": repeat,
        "one_time_customers": users - repeat,
        "repeat_rate_pct": repeat / users * 100,
        "opc": n / users,
        "aov": df["total_with_vat_delivery"].sum() / n if n else 0,
        "aov_profitable": df.loc[df["is_profitable"] == 1, "total_with_vat_delivery"].mean() if (df["is_profitable"] == 1).any() else 0,
        "aov_loss": df.loc[df["is_profitable"] == 0, "total_with_vat_delivery"].mean() if (df["is_profitable"] == 0).any() else 0,
        "profitable_customer_pct": profitable / users * 100,
        "wallet_penetration_pct": df["is_wallet"].sum() / n * 100 if n else 0,
        "benefits_pay_pct": (df["payment_method_clean"] == "Benefits Pay").sum() / n * 100 if n else 0,
        "discount_penetration_pct": df["is_discounted"].sum() / n * 100 if n else 0,
        "avg_discount_bhd": avg_disc,
        "top20_rev_concentration_pct": top20_rev / total_rev * 100 if total_rev else 0,
        "dormant_30_pct": (days_since > 30).sum() / users * 100,
        "dormant_60_pct": (days_since > 60).sum() / users * 100,
        "dormant_90_pct": (days_since > 90).sum() / users * 100,
        "lifetimes": lt,
        "payment_method_mix": df["payment_method_clean"].value_counts(normalize=True).mul(100).round(1).to_dict() if n else {},
    }


# ---------- RFM ----------
def rfm_segmentation(df: pd.DataFrame) -> pd.DataFrame:
    lt = customer_lifetimes(df)
    if len(lt) == 0:
        return pd.DataFrame(columns=["user_id", "recency", "frequency", "monetary", "r", "f", "m", "rfm", "segment"])

    today = pd.Timestamp.today().normalize()
    lt["recency"] = (today - lt["last_order"]).dt.days.fillna(999)
    lt["frequency"] = lt["orders"]
    lt["monetary"] = lt["revenue"]

    # Quintile scores. Recency is inverted: lower days = higher score.
    def score(s, invert=False):
        try:
            q = pd.qcut(s.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
        except ValueError:
            # Not enough unique values -> everyone gets mid-tier
            q = pd.Series([3] * len(s), index=s.index)
        return 6 - q if invert else q

    lt["r"] = score(lt["recency"], invert=True)
    lt["f"] = score(lt["frequency"])
    lt["m"] = score(lt["monetary"])
    lt["rfm"] = lt["r"].astype(str) + lt["f"].astype(str) + lt["m"].astype(str)

    def label(row):
        r, f = row["r"], row["f"]
        if r >= 4 and f >= 4:
            return "Level 1 — VIP"
        if r >= 3 and f >= 3:
            return "Level 2 — Loyal"
        if r >= 4 and f <= 2:
            return "Level 3 — New"
        if r <= 2 and f >= 3:
            return "Level 4 — At Risk"
        if r >= 3 and f <= 2:
            return "Level 5 — Potential"
        return "Level 6 — Inactive"

    lt["segment"] = lt.apply(label, axis=1)
    return lt[["user_id", "recency", "frequency", "monetary", "r", "f", "m", "rfm", "segment"]]


# ---------- restaurants ----------
def restaurant_kpis(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) == 0:
        return pd.DataFrame()
    grp = df.groupby("restaurant_display")
    agg_dict = {
        "restaurant_id": ("restaurant_id", "first"),
        "orders": ("order_id", "count"),
        "gmv": ("total_with_vat_delivery", "sum"),
        "net_food": ("amount_ex_vat", "sum"),
        "commission_bhd": ("commission_bhd", "sum"),
        "avg_commission_pct": ("commission_pct", "mean"),
        "delivery_rev": ("delivery_revenue", "sum"),
        "rest_subsidy": ("restaurant_delivery_offer", "sum"),
        "cost_3pl": ("cost_3pl", "sum"),
        "profit": ("order_profit", "sum"),
        "loss_orders": ("is_profitable", lambda s: (s == 0).sum()),
        "subsidy_orders": ("restaurant_delivery_offer", lambda s: (s > 0).sum()),
        "avg_km": ("km_billable", "mean"),
        "total_km": ("km_billable", "sum"),
    }
    if "is_delivered" in df.columns:
        agg_dict["delivered_orders"] = ("is_delivered", "sum")
    r = grp.agg(**agg_dict).reset_index().rename(columns={"restaurant_display": "restaurant"})
    if "delivered_orders" not in r.columns:
        r["delivered_orders"] = r["orders"]

    r["aov"] = r["gmv"] / r["orders"]

    # AOV for profitable / loss-making orders + break-even AOV per restaurant
    profitable_aov = df[df["is_profitable"] == 1].groupby("restaurant_display")["amount_ex_vat"].mean()
    loss_aov = df[df["is_profitable"] == 0].groupby("restaurant_display")["amount_ex_vat"].mean()

    # Break-even AOV: minimum order value where profit >= 0
    # At break-even: commission_rate * AOV + delivery_rev_per_order + rest_offer_per_order = cpo
    # So: AOV_be = (CPO - avg_delivery_rev - avg_rest_offer) / avg_commission_rate
    rest_avg = df.groupby("restaurant_display").agg(
        avg_comm_rate=("commission_pct", "mean"),
        avg_del_rev=("delivery_revenue", "mean"),
        avg_rest_offer=("restaurant_delivery_offer", "mean"),
        avg_cpo=("cost_3pl", "mean"),
    )
    breakeven_num = rest_avg["avg_cpo"] - rest_avg["avg_del_rev"] - rest_avg["avg_rest_offer"]
    breakeven_denom = rest_avg["avg_comm_rate"].replace(0, np.nan) / 100
    breakeven_aov = (breakeven_num / breakeven_denom).clip(lower=0)

    r = r.set_index("restaurant")
    r["aov_profitable"] = profitable_aov.reindex(r.index).fillna(0)
    r["aov_loss"] = loss_aov.reindex(r.index).fillna(0)
    r["aov_breakeven"] = breakeven_aov.reindex(r.index).fillna(0)
    r = r.reset_index()

    r["commission_yield_pct"] = np.where(r["net_food"] > 0, r["commission_bhd"] / r["net_food"] * 100, 0)
    r["delivery_subsidy_pct"] = r["subsidy_orders"] / r["orders"] * 100
    r["profit_margin_pct"] = np.where(r["gmv"] > 0, r["profit"] / r["gmv"] * 100, 0)
    r["loss_order_pct"] = r["loss_orders"] / r["orders"] * 100
    r["cpo_restaurant"] = np.where(r["delivered_orders"] > 0, r["cost_3pl"] / r["delivered_orders"], 0)
    r["delivery_cost_ratio_pct"] = np.where(r["gmv"] > 0, r["cost_3pl"] / r["gmv"] * 100, 0)
    r["bhd_per_km"] = np.where(r["total_km"] > 0, r["gmv"] / r["total_km"], 0)

    # Restaurant repeat rate: customers with >=2 orders at this restaurant / total customers
    rest_repeat = df.groupby(["restaurant_display", "user_id"]).agg(
        order_count=("order_id", "count")
    ).reset_index()
    repeat_stats = rest_repeat.groupby("restaurant_display").agg(
        total_customers=("user_id", "count"),
        repeat_customers=("order_count", lambda s: (s >= 2).sum()),
    ).reset_index().rename(columns={"restaurant_display": "restaurant"})
    repeat_stats["repeat_rate_pct"] = np.where(
        repeat_stats["total_customers"] > 0,
        repeat_stats["repeat_customers"] / repeat_stats["total_customers"] * 100, 0,
    )

    r = r.merge(
        repeat_stats[["restaurant", "total_customers", "repeat_customers", "repeat_rate_pct"]],
        on="restaurant", how="left",
    )
    r["repeat_rate_pct"] = r["repeat_rate_pct"].fillna(0)
    r["total_customers"] = r["total_customers"].fillna(0).astype(int)
    r["repeat_customers"] = r["repeat_customers"].fillna(0).astype(int)

    return r.sort_values("gmv", ascending=False).reset_index(drop=True)


# ---------- distance bracket ----------
def bracket_analysis(df: pd.DataFrame) -> pd.DataFrame:
    brackets = ["0-1km", "1-2km", "2-3km", "3-4km", "4-5km", "5km+"]
    total_orders = len(df)
    rows = []
    for b in brackets:
        sub = df[df["distance_bracket"] == b]
        n = len(sub)
        if n == 0:
            rows.append({"bracket": b, "orders": 0, "delivered": 0, "gmv": 0, "rpo": 0, "cpo": 0,
                         "avg_profit": 0, "total_profit": 0, "loss_rate": 0, "order_mix_pct": 0})
            continue
        delivered = sub[sub["is_delivered"] == 1] if "is_delivered" in sub.columns else sub
        nd = len(delivered)
        commission = sub["commission_bhd"].sum()
        delivery_rev = delivered["delivery_revenue"].sum()
        rest_offer = sub["restaurant_delivery_offer"].sum()
        cost_3pl = delivered["cost_3pl"].sum()
        profit = commission + delivery_rev + rest_offer - cost_3pl
        rows.append({
            "bracket": b,
            "orders": n,
            "delivered": nd,
            "gmv": sub["total_with_vat_delivery"].sum(),
            "rpo": (delivery_rev + rest_offer) / nd if nd else 0,
            "cpo": cost_3pl / nd if nd else 0,
            "avg_profit": profit / n,
            "total_profit": profit,
            "loss_rate": (sub["is_profitable"] == 0).sum() / n * 100,
            "order_mix_pct": n / total_orders * 100 if total_orders else 0,
        })
    return pd.DataFrame(rows)


# ---------- daily series ----------
def daily_series(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) == 0:
        return pd.DataFrame(columns=["date", "orders", "gmv", "profit", "margin"])
    d = df.groupby("date_str").agg(
        orders=("order_id", "count"),
        gmv=("total_with_vat_delivery", "sum"),
        profit=("order_profit", "sum"),
    ).reset_index().rename(columns={"date_str": "date"})
    d = d[d["date"] != ""]
    d["margin"] = np.where(d["gmv"] > 0, d["profit"] / d["gmv"] * 100, 0)
    return d.sort_values("date").reset_index(drop=True)


# ---------- time-based KPIs ----------
def time_based_kpis(df: pd.DataFrame) -> dict:
    """Peak hour, day-of-week, and weekly active customer metrics."""
    n = len(df)
    if n == 0:
        return {
            "peak_hour_share_pct": 0,
            "peak_profit_per_order": 0,
            "offpeak_profit_per_order": 0,
            "peak_vs_offpeak_ratio": 0,
            "dow_mix": pd.DataFrame(),
            "hourly_mix": pd.DataFrame(),
            "wac": pd.DataFrame(),
        }

    # Peak hours: lunch 12-14, dinner 19-22
    peak_mask = df["hour"].isin([12, 13, 14, 19, 20, 21, 22])
    peak_orders = peak_mask.sum()
    offpeak_orders = n - peak_orders
    peak_hour_share = peak_orders / n * 100

    peak_profit_po = df.loc[peak_mask, "order_profit"].mean() if peak_orders > 0 else 0
    offpeak_profit_po = df.loc[~peak_mask, "order_profit"].mean() if offpeak_orders > 0 else 0
    ratio = (peak_profit_po / offpeak_profit_po) if offpeak_profit_po != 0 else 0

    # Day-of-week mix
    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    dow = df.groupby("day_of_week").agg(
        orders=("order_id", "count"),
        profit=("order_profit", "sum"),
        gmv=("total_with_vat_delivery", "sum"),
    ).reset_index()
    dow["mix_pct"] = dow["orders"] / n * 100
    dow["avg_profit"] = dow["profit"] / dow["orders"]
    # Sort by day order
    dow["day_of_week"] = pd.Categorical(dow["day_of_week"], categories=dow_order, ordered=True)
    dow = dow.sort_values("day_of_week").reset_index(drop=True)

    # Hourly distribution
    hourly = df.groupby("hour").agg(
        orders=("order_id", "count"),
        profit=("order_profit", "sum"),
    ).reset_index()
    hourly["mix_pct"] = hourly["orders"] / n * 100
    hourly["avg_profit"] = hourly["profit"] / hourly["orders"]
    hourly = hourly.sort_values("hour").reset_index(drop=True)

    # Weekly active customers
    wac = pd.DataFrame()
    if "order_date" in df.columns:
        weekly = df.copy()
        weekly["week"] = weekly["order_date"].dt.isocalendar().week.astype(int)
        weekly["year"] = weekly["order_date"].dt.year
        weekly["year_week"] = weekly["year"].astype(str) + "-W" + weekly["week"].astype(str).str.zfill(2)
        wac = weekly.groupby("year_week").agg(
            active_customers=("user_id", "nunique"),
            orders=("order_id", "count"),
        ).reset_index().sort_values("year_week").reset_index(drop=True)

    return {
        "peak_hour_share_pct": peak_hour_share,
        "peak_profit_per_order": peak_profit_po,
        "offpeak_profit_per_order": offpeak_profit_po,
        "peak_vs_offpeak_ratio": ratio,
        "dow_mix": dow,
        "hourly_mix": hourly,
        "wac": wac,
    }
