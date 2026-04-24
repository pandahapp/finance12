"""
SQLite database layer for persistent storage of parsed orders.
Stores enriched order data so it survives app restarts.
"""
import os
import sqlite3
from datetime import datetime

import pandas as pd

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "orders.db")


def _ensure_dir():
    os.makedirs(DB_DIR, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrency for large inserts
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    """Create the orders table and uploads log if they don't exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            rows_inserted INTEGER NOT NULL,
            uploaded_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id INTEGER NOT NULL,
            driver_id TEXT,
            restaurant_id TEXT,
            restaurant_name TEXT,
            order_id TEXT,
            user_id TEXT,
            order_date TEXT,
            order_time TEXT,
            amount_ex_vat REAL,
            vat_amount REAL,
            total_with_vat_delivery REAL,
            wallet_paid REAL,
            delivery_fee_charged REAL,
            commission_pct REAL,
            commission_bhd REAL,
            payment_method TEXT,
            restaurant_delivery_offer REAL,
            discount_pct REAL,
            discount_amount REAL,
            km_delivered REAL,
            cost_3pl REAL,
            -- enriched fields
            is_delivered INTEGER,
            is_3pl INTEGER,
            total_paid REAL,
            delivery_revenue REAL,
            km_billable INTEGER,
            payment_method_clean TEXT,
            is_wallet INTEGER,
            is_discounted INTEGER,
            order_profit REAL,
            profit_margin_pct REAL,
            is_profitable INTEGER,
            distance_bracket TEXT,
            hour INTEGER,
            daypart TEXT,
            day_of_week TEXT,
            month TEXT,
            date_str TEXT,
            restaurant_display TEXT,
            FOREIGN KEY (upload_id) REFERENCES uploads(id)
        )
    """)
    # Migrate: add new columns if upgrading from older schema
    try:
        conn.execute("ALTER TABLE orders ADD COLUMN driver_id TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        conn.execute("ALTER TABLE orders ADD COLUMN is_delivered INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE orders ADD COLUMN is_3pl INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_restaurant ON orders(restaurant_display)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_upload ON orders(upload_id)")
    conn.commit()
    conn.close()


# Columns to store (must match the enriched DataFrame from parser.py)
STORE_COLS = [
    "driver_id", "restaurant_id", "restaurant_name", "order_id", "user_id",
    "order_date", "order_time",
    "amount_ex_vat", "vat_amount", "total_with_vat_delivery",
    "wallet_paid", "delivery_fee_charged", "commission_pct",
    "commission_bhd", "payment_method", "restaurant_delivery_offer",
    "discount_pct", "discount_amount", "km_delivered", "cost_3pl",
    # enriched
    "is_delivered", "total_paid", "delivery_revenue", "km_billable",
    "payment_method_clean", "is_wallet", "is_discounted",
    "order_profit", "profit_margin_pct", "is_profitable",
    "distance_bracket", "hour", "daypart", "day_of_week",
    "month", "date_str", "restaurant_display",
]


def insert_orders(df: pd.DataFrame, filename: str) -> int:
    """Insert a parsed & enriched DataFrame into the database. Returns upload_id."""
    conn = get_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor = conn.execute(
        "INSERT INTO uploads (filename, rows_inserted, uploaded_at) VALUES (?, ?, ?)",
        (filename, len(df), now),
    )
    upload_id = cursor.lastrowid

    # Prepare data for bulk insert
    store = df[STORE_COLS].copy()
    # Convert dates to ISO string for SQLite (handle NaT → None)
    if "order_date" in store.columns:
        store["order_date"] = store["order_date"].apply(
            lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else None
        )

    store.insert(0, "upload_id", upload_id)

    placeholders = ", ".join(["?"] * (len(STORE_COLS) + 1))
    col_names = "upload_id, " + ", ".join(STORE_COLS)
    sql = f"INSERT INTO orders ({col_names}) VALUES ({placeholders})"

    # Insert in batches of 5000 for performance
    rows = store.values.tolist()
    batch_size = 5000
    for i in range(0, len(rows), batch_size):
        conn.executemany(sql, rows[i : i + batch_size])
    conn.commit()
    conn.close()
    return upload_id


def load_all_orders() -> pd.DataFrame:
    """Load all orders from the database into a DataFrame."""
    conn = get_connection()
    df = pd.read_sql_query(
        f"SELECT {', '.join(STORE_COLS)} FROM orders", conn
    )
    conn.close()

    if len(df) == 0:
        return df

    # Restore types — parse any date format, then normalize to midnight
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    df["order_date"] = df["order_date"].dt.normalize()
    for col in ["amount_ex_vat", "vat_amount", "total_with_vat_delivery",
                "wallet_paid", "delivery_fee_charged", "commission_pct",
                "commission_bhd", "restaurant_delivery_offer", "discount_pct",
                "discount_amount", "km_delivered", "cost_3pl",
                "total_paid", "delivery_revenue", "order_profit", "profit_margin_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    for col in ["km_billable", "is_wallet", "is_discounted", "is_profitable", "is_delivered", "hour"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # Re-apply vertical mapping (derived from restaurant_id, CSV-driven)
    from parser import apply_verticals
    df = apply_verticals(df)

    return df


def get_uploads() -> pd.DataFrame:
    """Return the upload history."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM uploads ORDER BY uploaded_at DESC", conn)
    conn.close()
    return df


def delete_upload(upload_id: int):
    """Remove an upload and all its orders."""
    conn = get_connection()
    conn.execute("DELETE FROM orders WHERE upload_id = ?", (upload_id,))
    conn.execute("DELETE FROM uploads WHERE id = ?", (upload_id,))
    conn.commit()
    conn.close()


def get_total_order_count() -> int:
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    conn.close()
    return count


def clear_all():
    """Delete all data."""
    conn = get_connection()
    conn.execute("DELETE FROM orders")
    conn.execute("DELETE FROM uploads")
    conn.execute("VACUUM")
    conn.commit()
    conn.close()
