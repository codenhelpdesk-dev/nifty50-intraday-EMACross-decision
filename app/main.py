from __future__ import annotations

import asyncio
import threading
import pandas as pd
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import NIFTY50, REFRESH_SECONDS, IST_TZ, MARKET_OPEN, MARKET_CLOSE, BAR_MINUTES
from engine import score_setup
from yahoo_provider import fetch_market

APP_VERSION = "v3"
app = FastAPI(title="NIFTY 50 Intraday EMACross Decision Portal")
app.mount("/static", StaticFiles(directory="static"), name="static")

IST = ZoneInfo(IST_TZ)
lock = threading.Lock()
STATE = {
    "stocks": {},
    "nifty": None,
    "fetched_at": None,
    "last_attempt": None,
    "last_error": None,
    "source": "Yahoo Finance via yfinance",
    "elapsed": None,
    "fetch_status": "WAITING",
}


def market_open_now():
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return dtime(*MARKET_OPEN) <= t <= dtime(*MARKET_CLOSE)


def regime_from_nifty(df):
    if df is None or len(df) < 40:
        return {"name": "INSUFFICIENT DATA", "direction": "NONE", "score": 0}
    try:
        r = score_setup(df)
    except Exception:
        return {"name": "INSUFFICIENT DATA", "direction": "NONE", "score": 0}
    if not r.get("valid"):
        return {"name": "INSUFFICIENT DATA", "direction": "NONE", "score": 0}
    if r["score"] >= 80:
        return {"name": f"{r['direction']} TREND", "direction": r["direction"], "score": r["score"]}
    return {"name": "RANGE / NO EDGE", "direction": "NONE", "score": r["score"]}



def format_ist_timestamp(value):
    if value is None:
        return None
    try:
        ts = value
        if not hasattr(ts, "tzinfo"):
            return str(ts)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=IST)
        else:
            ts = ts.astimezone(IST)
        return ts.strftime("%d-%b-%Y %H:%M IST")
    except Exception:
        return str(value)


def latest_completed_index(df):
    """Return the latest bar that is definitely complete in IST."""
    if df is None or df.empty:
        return None
    try:
        idx = pd.DatetimeIndex(df.index)
        if idx.tz is None:
            idx = idx.tz_localize(IST)
        else:
            idx = idx.tz_convert(IST)
        now = datetime.now(IST)
        cutoff = now.replace(second=0, microsecond=0)
        # Yahoo timestamps represent the start of the 5m bar. A bar is complete
        # only after its 5-minute interval has elapsed.
        eligible = idx + pd.Timedelta(minutes=BAR_MINUTES) <= cutoff
        if not eligible.any():
            return None
        return df.index[eligible][-1]
    except Exception:
        return df.index[-1]

def build_payload():
    now = datetime.now(IST)
    market_open = market_open_now()
    result = []

    for symbol in NIFTY50:
        key = f"{symbol}.NS"
        df = STATE["stocks"].get(key)
        if df is None:
            result.append({
                "symbol": symbol, "valid": False, "score": 0,
                "classification": "REJECT", "direction": "NONE",
                "entry_status": "NO DATA", "price": None,
            })
            continue
        try:
            # Never score or report a crossover from an unfinished 5-minute candle.
            completed_idx = latest_completed_index(df)
            if completed_idx is not None:
                df_for_score = df.loc[:completed_idx].copy()
            else:
                df_for_score = df.copy()
            s = score_setup(df_for_score)
            s["symbol"] = symbol
            if not s.get("valid"):
                s.setdefault("score", 0)
                s.setdefault("classification", "REJECT")
                s.setdefault("direction", "NONE")
                s.setdefault("entry_status", "NO DATA")
                s.setdefault("actionable", False)

            if not market_open:
                s["actionable"] = False
                s["entry_status"] = "MARKET CLOSED"
                s["entry"] = s["stop_loss"] = s["target1"] = s["target2"] = None
                s["quantity"] = 0
            result.append(s)
        except Exception as e:
            result.append({
                "symbol": symbol, "valid": False, "score": 0,
                "classification": "REJECT", "direction": "NONE",
                "entry_status": "CALCULATION ERROR", "error": str(e),
            })

    candle = None
    if STATE["nifty"] is not None and len(STATE["nifty"]):
        ci = latest_completed_index(STATE["nifty"])
        candle = format_ist_timestamp(ci if ci is not None else STATE["nifty"].index[-1])

    # Find the newest confirmed EMA 7/21 cross across all NIFTY 50 stocks.
    latest_cross = None
    for item in result:
        cross = item.get("ema_cross") if isinstance(item, dict) else None
        if not cross or not cross.get("occurred"):
            continue
        raw = cross.get("time")
        try:
            ts = pd.Timestamp(raw)
            if ts.tzinfo is None:
                ts = ts.tz_localize(IST)
            else:
                ts = ts.tz_convert(IST)
            if latest_cross is None or ts > latest_cross["_ts"]:
                latest_cross = {
                    "_ts": ts,
                    "symbol": item.get("symbol"),
                    "direction": cross.get("direction"),
                    "time": format_ist_timestamp(ts),
                    "bars_since": cross.get("bars_since"),
                    "is_today": ts.date() == datetime.now(IST).date(),
                }
        except Exception:
            continue
    if latest_cross:
        latest_cross.pop("_ts", None)

    return {
        "app_version": APP_VERSION,
        "market_open": market_open,
        "market_regime": regime_from_nifty(STATE["nifty"]),
        "stocks": result,
        "fetched_at": STATE["fetched_at"].isoformat() if STATE["fetched_at"] else None,
        "last_attempt": STATE["last_attempt"].isoformat() if STATE["last_attempt"] else None,
        "last_error": STATE["last_error"],
        "fetch_status": STATE["fetch_status"],
        "source": STATE["source"],
        "elapsed": STATE["elapsed"],
        "nifty_candle": candle,
        "latest_ema_cross": latest_cross,
        "server_time": now.isoformat(),
        "refresh_seconds": REFRESH_SECONDS,
    }


def refresh_data():
    with lock:
        STATE["last_attempt"] = datetime.now(IST)
        STATE["fetch_status"] = "REFRESHING"
        try:
            m = fetch_market()
            stocks = m.get("stocks") or {}
            nifty = m.get("nifty")
            if not stocks and nifty is None:
                raise RuntimeError(m.get("error") or "Yahoo Finance returned no market data")

            # Replace the snapshot only after a successful fetch. This prevents a
            # temporary Yahoo failure from wiping a previously good dashboard.
            STATE["stocks"] = stocks
            STATE["nifty"] = nifty
            STATE["fetched_at"] = m.get("fetched_at") or datetime.now(IST)
            STATE["elapsed"] = m.get("elapsed")
            STATE["last_error"] = m.get("error")
            STATE["fetch_status"] = "OK" if not STATE["last_error"] else "PARTIAL"
        except Exception as e:
            STATE["last_error"] = f"{type(e).__name__}: {e}"
            STATE["fetch_status"] = "ERROR"


def safe_payload():
    # jsonable_encoder converts datetime/numpy scalar-like values before they
    # reach JSONResponse. The browser therefore always receives valid JSON,
    # even when Yahoo or an indicator calculation fails.
    return jsonable_encoder(build_payload())


@app.on_event("startup")
async def startup():
    asyncio.create_task(asyncio.to_thread(refresh_data))


@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.get("/api/market")
def market():
    return JSONResponse(content=safe_payload())


@app.post("/api/refresh")
async def manual_refresh():
    await asyncio.to_thread(refresh_data)
    return JSONResponse(content=safe_payload())


@app.get("/health")
def health():
    return jsonable_encoder({
        "status": "ok",
        "version": APP_VERSION,
        "fetch_status": STATE["fetch_status"],
        "data_fetched_at": STATE["fetched_at"].isoformat() if STATE["fetched_at"] else None,
        "last_attempt": STATE["last_attempt"].isoformat() if STATE["last_attempt"] else None,
        "last_error": STATE["last_error"],
    })
