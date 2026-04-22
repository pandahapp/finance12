# Finance Team Analytics Dashboard (Python)

A Tableau-style, in-memory analytics dashboard for delivery and restaurant operations. Built with **Streamlit + Plotly + Pandas**. Upload your orders Excel and get instant customer, restaurant, and profitability analysis with full pivot capability.

## Quick start

### 1. Install Python 3.10+ (if you don't already have it)
Check with `python --version` or `python3 --version`

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the app

```bash
streamlit run app.py
```

The app opens automatically at **http://localhost:8501**

## Using the dashboard

1. Drop your `.xlsx` file on the upload page
2. Use the sidebar to filter by date, payment method, distance bracket, restaurant, or profitability
3. Explore the 6 tabs:
   - **📊 Overview** — top-line KPIs + waterfall + bracket + daily trend
   - **👥 Customers** — 16 KPIs + RFM segmentation + Pareto + top/bottom customers
   - **🏪 Restaurants** — GMV vs profit + BCG matrix + commission yield + full performance table
   - **💰 Profitability** — profit distribution + scenario sensitivity (delivery fee / 3PL cost sliders)
   - **🔀 Pivot Builder** — pick rows/columns/value/aggregation + heatmap coloring + CSV download
   - **📋 Raw Data** — enriched rows with column picker + CSV download

## The profitability formula

```
Order Profit = Commission (Y) + (Delivery Fee (T) × 1.10) + Rest Offer (AB) − 3PL Cost (AK)
```

## Excel column mapping

| Col | Field |
|-----|-------|
| I   | Restaurant ID |
| J   | Restaurant Name |
| K   | Order ID |
| M   | User ID |
| N   | Order Date |
| O   | Order Time |
| P   | Amount ex-VAT |
| Q   | VAT Amount |
| R   | Total with VAT + Delivery |
| S   | Wallet Paid |
| T   | Delivery Fee (×1.10 = revenue) |
| U   | Commission % |
| Y   | Commission in BHD |
| Z   | Payment Method (blank = Benefits Pay) |
| AB  | Restaurant Delivery Offer |
| AC  | Discount % |
| AD  | Discount BHD |
| AF  | KM Delivered (rounded up) |
| AK  | 3PL Cost |

## File structure

```
finance-team-analytics-py/
├── app.py              # Streamlit app (UI + layout)
├── parser.py           # Excel → enriched DataFrame
├── metrics.py          # All 40+ KPI formulas
├── requirements.txt    # pip dependencies
└── README.md
```

## Adding payment gateway fees (optional)

Edit `parser.py` in the enrichment section:

```python
gateway_fee = df["total_with_vat_delivery"] * 0.025
df["order_profit"] = (
    df["commission_bhd"]
    + df["delivery_revenue"]
    + df["restaurant_delivery_offer"]
    - df["cost_3pl"]
    - gateway_fee
)
```

## Running on a different port

```bash
streamlit run app.py --server.port 8080
```

## Deploying

- **Streamlit Community Cloud** — push this folder to a GitHub repo, connect it at share.streamlit.io, free hosting
- **Internal server** — `streamlit run app.py --server.address 0.0.0.0 --server.port 8501` then reverse-proxy through nginx/caddy
- **Docker** — create a `Dockerfile` with `CMD ["streamlit", "run", "app.py"]`
