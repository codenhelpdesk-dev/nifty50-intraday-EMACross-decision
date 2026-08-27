from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from config import NIFTY50, INTERVAL, YF_PERIOD, IST_TZ

IST = ZoneInfo(IST_TZ)


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = [c[0] if isinstance(c, tuple) else c for c in d.columns]
    return d


def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    idx = pd.DatetimeIndex(d.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    idx = idx.tz_convert(IST_TZ)
    d.index = idx
    return d


def _clean_frame(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    d = _flatten_columns(df)
    d = _normalize_index(d)
    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(d.columns):
        return None
    for c in required:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["Open", "High", "Low", "Close"])
    return d if len(d) >= 30 else None


def fetch_market():
    symbols = [f"{s}.NS" for s in NIFTY50]
    all_symbols = symbols + ["^NSEI"]
    started = time.time()
    errors = []
    stocks = {}

    # One batch request is substantially faster than 51 individual requests.
    # auto_adjust=False preserves the raw OHLC values used by the intraday rules.
    try:
        data = yf.download(
            tickers=all_symbols,
            period=YF_PERIOD,
            interval=INTERVAL,
            auto_adjust=False,
            group_by="ticker",
            threads=False,
            progress=False,
            prepost=False,
            timeout=25,
        )

        if data is not None and not data.empty:
            if isinstance(data.columns, pd.MultiIndex):
                level0 = set(data.columns.get_level_values(0))
                for symbol in all_symbols:
                    if symbol not in level0:
                        continue
                    frame = _clean_frame(data[symbol])
                    if frame is not None:
                        stocks[symbol] = frame
            else:
                # This branch is useful when Yahoo returns a single-ticker frame.
                frame = _clean_frame(data)
                if frame is not None:
                    stocks[all_symbols[0]] = frame
    except Exception as exc:
        errors.append(f"batch: {type(exc).__name__}: {exc}")

    # If Yahoo drops symbols from the batch (which can happen transiently),
    # retry only the missing symbols individually. This also avoids turning one
    # bad ticker into a total dashboard failure.
    missing = [s for s in all_symbols if s not in stocks]
    for symbol in missing:
        try:
            frame = yf.Ticker(symbol).history(
                period=YF_PERIOD,
                interval=INTERVAL,
                auto_adjust=False,
                prepost=False,
                timeout=20,
            )
            frame = _clean_frame(frame)
            if frame is not None:
                stocks[symbol] = frame
        except Exception as exc:
            errors.append(f"{symbol}: {type(exc).__name__}: {exc}")

    nifty_df = stocks.pop("^NSEI", None)
    fetched_at = datetime.now(IST)

    # Do not treat a partial Yahoo response as a hard application failure.
    # The UI will show PARTIAL and retain whatever valid symbols were returned.
    error = None
    if not stocks and nifty_df is None:
        error = "; ".join(errors[-3:]) or "Yahoo Finance returned no usable data"
    elif errors:
        error = "; ".join(errors[-3:])

    return {
        "stocks": stocks,
        "nifty": nifty_df,
        "fetched_at": fetched_at,
        "elapsed": round(time.time() - started, 2),
        "source": "Yahoo Finance via yfinance",
        "error": error,
    }
