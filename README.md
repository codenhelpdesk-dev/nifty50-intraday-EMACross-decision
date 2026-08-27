# NIFTY 50 Intraday EMACross Decision Portal v3

Read-only NIFTY 50 intraday suggestion portal using 5-minute Yahoo Finance data.

## v3 changes
- Detects the latest confirmed EMA 7/21 crossover for every NIFTY 50 stock from historical 5-minute bars.
- Uses only completed 5-minute candles for crossover detection and scoring.
- Displays the latest cross symbol, direction and exact IST timestamp at the top right.
- Displays each stock's latest EMA cross timestamp in its tile.
- Clicking a stock shows the cross timestamp, bars since cross, and EMA values immediately before/after the cross.
- Converts Yahoo timestamps to Asia/Kolkata (IST).
- Uses 5 days of 5-minute history so the latest cross can be located reliably.
- Browser refresh is aligned to the next 5-minute clock boundary instead of 5 minutes from page-load.

## v2 fixes
- `/api/market` and `/api/refresh` always return valid JSON through FastAPI's JSON encoder.
- Yahoo Finance batch failures are isolated; missing symbols are retried individually.
- A temporary Yahoo failure no longer wipes the last good market snapshot.
- The browser's 5-minute timer now calls **`POST /api/refresh`**, so it actually fetches fresh Yahoo data. The old v1 timer only called `/api/market`, which returned cached server data.
- Manual Refresh uses the same refresh path and shows the actual backend error.
- Status now distinguishes `OK`, `PARTIAL`, `REFRESHING`, and `ERROR`.

## Strategy
- EMA 7 / EMA 21
- Bollinger Bands 20 / 2
- MACD 12 / 26 / 9
- Vortex Indicator 14
- Relative volume
- Candle confirmation
- Extension/chasing filter
- ATR(14) for risk/stop calculation only

## Risk
- Account capital: Rs 230,000
- Maximum account risk: 1% = Rs 2,300 per trade
- No order execution.

## Local Windows run
```text
run_portal.bat
```
Open `http://127.0.0.1:8050`.

Or:
```text
pip install -r requirements.txt
cd app
python -m uvicorn main:app --host 127.0.0.1 --port 8050
```

## Render
Build command:
```text
pip install -r requirements.txt
```
Start command:
```text
cd app && uvicorn main:app --host 0.0.0.0 --port $PORT
```
