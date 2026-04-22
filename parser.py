"""
Excel parser & enrichment.
Maps columns: I, J, K, M, N, O, P, Q, R, S, T, U, Y, Z, AB, AC, AD, AF, AK
Computes: delivery_revenue (T*1.10), km_billable (ceil), order_profit, bracket, daypart.
"""
import numpy as np
import pandas as pd

# Excel column letter -> 0-based index
COL = {
    "I": 8, "J": 9,
    "K": 10, "M": 12, "N": 13, "O": 14,
    "P": 15, "Q": 16, "R": 17, "S": 18, "T": 19, "U": 20,
    "V": 21, "Z": 25, "AB": 27, "AC": 28, "AD": 29, "AF": 31, "AK": 36,
}

FIELD_MAP = {
    "I": "restaurant_id",
    "J": "restaurant_name",
    "K": "order_id",
    "M": "user_id",
    "N": "order_date",
    "O": "order_time",
    "P": "total_with_vat_delivery",
    "Q": "vat_amount",
    "R": "amount_ex_vat",
    "S": "wallet_paid",
    "T": "delivery_fee_charged",
    "U": "commission_pct",
    "V": "commission_bhd",
    "Z": "payment_method",
    "AB": "restaurant_delivery_offer",
    "AC": "discount_pct",
    "AD": "discount_amount",
    "AF": "km_delivered",
    "AK": "cost_3pl",
}

NUMERIC_FIELDS = [
    "amount_ex_vat", "vat_amount", "total_with_vat_delivery",
    "wallet_paid", "delivery_fee_charged", "commission_pct",
    "commission_bhd", "restaurant_delivery_offer", "discount_pct",
    "discount_amount", "km_delivered", "cost_3pl",
]

STRING_FIELDS = [
    "restaurant_id", "restaurant_name", "order_id", "user_id",
    "order_time", "payment_method",
]


def _bracket(km: float) -> str:
    if km <= 1:
        return "0-1km"
    if km <= 2:
        return "1-2km"
    if km <= 3:
        return "2-3km"
    if km <= 4:
        return "3-4km"
    if km <= 5:
        return "4-5km"
    return "5km+"


def _daypart(h: int) -> str:
    if h < 11:
        return "Breakfast"
    if h < 16:
        return "Lunch"
    if h < 22:
        return "Dinner"
    return "Late Night"


def _extract_hour(t) -> int:
    """Handle time as string 'HH:MM', datetime.time, float fraction (Excel), or NaN."""
    if pd.isna(t):
        return 0
    if isinstance(t, str):
        if ":" in t:
            try:
                return int(t.split(":")[0])
            except ValueError:
                return 0
        return 0
    if hasattr(t, "hour"):
        return int(t.hour)
    if isinstance(t, (int, float)):
        if 0 <= t < 1:  # Excel time fraction
            return int(t * 24)
        return int(t) % 24
    return 0


def parse_excel(file) -> pd.DataFrame:
    """
    Read an uploaded xlsx file into a flat DataFrame.
    Accepts either a file path or a file-like object (Streamlit uploader).
    """
    raw = pd.read_excel(file, sheet_name=0, header=None, engine="openpyxl")

    # Decide if first row is a header: if column K (index 10) first cell is a
    # non-numeric string, treat row 0 as a header and skip it.
    skip_first = False
    try:
        first = raw.iloc[0, COL["K"]]
        if isinstance(first, str) and not first.strip().replace(".", "", 1).lstrip("-").isdigit():
            skip_first = True
    except Exception:
        pass

    if skip_first:
        raw = raw.iloc[1:].reset_index(drop=True)

    # Pick only the columns we care about
    df = pd.DataFrame()
    for letter, field in FIELD_MAP.items():
        idx = COL[letter]
        df[field] = raw.iloc[:, idx] if idx < raw.shape[1] else np.nan

    # Drop rows where both order_id and user_id are empty
    df = df.dropna(subset=["order_id", "user_id"], how="all").reset_index(drop=True)

    # Coerce types
    for f in NUMERIC_FIELDS:
        df[f] = pd.to_numeric(df[f], errors="coerce").fillna(0)

    for f in STRING_FIELDS:
        df[f] = df[f].astype(str).str.strip().replace({"nan": "", "NaT": ""})

    # Parse date
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")

    # ==== ENRICHMENT ====
    df["total_paid"] = df["amount_ex_vat"] + df["vat_amount"]
    df["delivery_revenue"] = df["delivery_fee_charged"] * 1.10
    df["km_billable"] = np.ceil(df["km_delivered"]).astype(int).clip(lower=0)
    df["payment_method_clean"] = df["payment_method"].replace("", "Benefits Pay").fillna("Benefits Pay")
    df["is_wallet"] = (df["wallet_paid"] > 0).astype(int)
    df["is_discounted"] = (df["discount_amount"] > 0).astype(int)

    # THE PROFITABILITY FORMULA
    df["order_profit"] = (
        df["commission_bhd"]
        + df["delivery_revenue"]
        + df["restaurant_delivery_offer"]
        - df["cost_3pl"]
    )

    df["profit_margin_pct"] = np.where(
        df["total_with_vat_delivery"] > 0,
        (df["order_profit"] / df["total_with_vat_delivery"]) * 100,
        0,
    )
    df["is_profitable"] = (df["order_profit"] > 0).astype(int)
    df["distance_bracket"] = df["km_billable"].apply(_bracket)
    df["hour"] = df["order_time"].apply(_extract_hour)
    df["daypart"] = df["hour"].apply(_daypart)
    df["day_of_week"] = df["order_date"].dt.day_name().fillna("Unknown")
    df["month"] = df["order_date"].dt.strftime("%Y-%m").fillna("")
    df["date_str"] = df["order_date"].dt.strftime("%Y-%m-%d").fillna("")

    # Restaurant display name (prefer name, fall back to id)
    df["restaurant_display"] = np.where(
        df["restaurant_name"].str.len() > 0,
        df["restaurant_name"],
        np.where(df["restaurant_id"].str.len() > 0, df["restaurant_id"], "Unassigned"),
    )

    return df
