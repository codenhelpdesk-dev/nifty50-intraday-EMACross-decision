
from __future__ import annotations

# NIFTY 50 constituent snapshot based on the August 2026 constituent list.
# Update this file when the official NIFTY 50 basket changes.
NIFTY50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BEL", "BHARTIARTL",
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
    "HINDUNILVR", "ICICIBANK", "INDIGO", "INFY", "ITC",
    "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT", "M&M",
    "MARUTI", "MAXHEALTH", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
    "SUNPHARMA", "TATACONSUM", "TMPV", "TATASTEEL", "TCS",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]

ACCOUNT_CAPITAL = 230_000.0
MAX_RISK_PCT = 0.01
MAX_RISK_RUPEES = ACCOUNT_CAPITAL * MAX_RISK_PCT

REFRESH_SECONDS = 300
# Treat only completed 5-minute candles as actionable/official crossover candles.
BAR_MINUTES = 5
INTERVAL = "5m"
YF_PERIOD = "5d"

# Scoring thresholds
HIGH_QUALITY = 90
TRADE_CANDIDATE = 80
WATCH = 70
WEAK = 60

IST_TZ = "Asia/Kolkata"
MARKET_OPEN = (9, 15)
MARKET_CLOSE = (15, 30)
