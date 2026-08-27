
from __future__ import annotations
import math
from typing import Any
import numpy as np
import pandas as pd

from config import (
    ACCOUNT_CAPITAL, MAX_RISK_RUPEES, HIGH_QUALITY, TRADE_CANDIDATE,
    WATCH, WEAK
)

def _num(x):
    try:
        if x is None or pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None

def _safe_round(x, n=2):
    return None if x is None else round(float(x), n)

def classify(score: int) -> str:
    if score >= HIGH_QUALITY:
        return "HIGH-QUALITY"
    if score >= TRADE_CANDIDATE:
        return "TRADE CANDIDATE"
    if score >= WATCH:
        return "WATCH"
    if score >= WEAK:
        return "WEAK"
    return "REJECT"

def calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    for c in ["Open","High","Low","Close","Volume"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")

    d["ema7"] = d["Close"].ewm(span=7, adjust=False).mean()
    d["ema21"] = d["Close"].ewm(span=21, adjust=False).mean()

    d["bb_mid"] = d["Close"].rolling(20).mean()
    d["bb_std"] = d["Close"].rolling(20).std(ddof=0)
    d["bb_upper"] = d["bb_mid"] + 2 * d["bb_std"]
    d["bb_lower"] = d["bb_mid"] - 2 * d["bb_std"]

    ema12 = d["Close"].ewm(span=12, adjust=False).mean()
    ema26 = d["Close"].ewm(span=26, adjust=False).mean()
    d["macd"] = ema12 - ema26
    d["macd_signal"] = d["macd"].ewm(span=9, adjust=False).mean()
    d["macd_hist"] = d["macd"] - d["macd_signal"]

    # Vortex Indicator 14
    prev_close = d["Close"].shift(1)
    vm_plus = (d["High"] - d["Low"].shift(1)).abs()
    vm_minus = (d["Low"] - d["High"].shift(1)).abs()
    tr = pd.concat([
        d["High"] - d["Low"],
        (d["High"] - prev_close).abs(),
        (d["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    d["vi_plus"] = vm_plus.rolling(14).sum() / tr.rolling(14).sum()
    d["vi_minus"] = vm_minus.rolling(14).sum() / tr.rolling(14).sum()

    # ATR is used only for risk/stop calculation, not the strategy score.
    d["atr14"] = tr.rolling(14).mean()
    d["rvol"] = d["Volume"] / d["Volume"].rolling(20).mean()

    d["candle_bull"] = d["Close"] > d["Open"]
    d["candle_bear"] = d["Close"] < d["Open"]
    return d.dropna()


def detect_latest_ema_cross(df: pd.DataFrame) -> dict[str, Any]:
    """Return the most recent completed EMA 7/21 crossover in the supplied 5m data."""
    d = calc_indicators(df)
    if len(d) < 3:
        return {
            "occurred": False,
            "direction": "NONE",
            "time": None,
            "date": None,
            "bars_since": None,
            "ema7": None,
            "ema21": None,
            "prev_ema7": None,
            "prev_ema21": None,
        }

    # A crossover is confirmed only when the completed candle changes the EMA ordering.
    bull = (d["ema7"].shift(1) <= d["ema21"].shift(1)) & (d["ema7"] > d["ema21"])
    bear = (d["ema7"].shift(1) >= d["ema21"].shift(1)) & (d["ema7"] < d["ema21"])
    events = d.index[bull | bear]
    if len(events) == 0:
        return {
            "occurred": False,
            "direction": "NONE",
            "time": None,
            "date": None,
            "bars_since": None,
            "ema7": None,
            "ema21": None,
            "prev_ema7": None,
            "prev_ema21": None,
        }

    ts = events[-1]
    pos = d.index.get_loc(ts)
    row = d.iloc[pos]
    prev = d.iloc[pos-1]
    direction = "BULLISH" if bool(bull.loc[ts]) else "BEARISH"
    bars_since = max(0, len(d) - 1 - pos)
    return {
        "occurred": True,
        "direction": direction,
        "time": str(ts),
        "date": str(ts.date()),
        "bars_since": int(bars_since),
        "ema7": _safe_round(_num(row.ema7)),
        "ema21": _safe_round(_num(row.ema21)),
        "prev_ema7": _safe_round(_num(prev.ema7)),
        "prev_ema21": _safe_round(_num(prev.ema21)),
    }

def score_setup(df: pd.DataFrame) -> dict[str, Any]:
    d = calc_indicators(df)
    if len(d) < 30:
        return {"valid": False, "reason": "Not enough 5m bars"}

    x = d.iloc[-1]
    p = d.iloc[-2]
    close = _num(x.Close)
    ema7, ema21 = _num(x.ema7), _num(x.ema21)
    bb_mid, bb_up, bb_low = _num(x.bb_mid), _num(x.bb_upper), _num(x.bb_lower)
    macd, sig, hist = _num(x.macd), _num(x.macd_signal), _num(x.macd_hist)
    vi_p, vi_m = _num(x.vi_plus), _num(x.vi_minus)
    rvol, atr = _num(x.rvol), _num(x.atr14)

    long_pts = 0
    short_pts = 0
    long_factors = []
    short_factors = []

    # 1. EMA 7/21 structure — 20 points
    if ema7 > ema21:
        long_pts += 20
        long_factors.append(("EMA 7 > EMA 21", "BULLISH", 20))
    elif ema7 < ema21:
        short_pts += 20
        short_factors.append(("EMA 7 < EMA 21", "BEARISH", 20))

    # 2. Price vs EMA structure — 15 points
    if close > ema7 > ema21:
        long_pts += 15
        long_factors.append(("Close > EMA 7 > EMA 21", "CONFIRMED", 15))
    elif close < ema7 < ema21:
        short_pts += 15
        short_factors.append(("Close < EMA 7 < EMA 21", "CONFIRMED", 15))

    # 3. Bollinger position — 15 points
    if bb_mid < close < bb_up:
        long_pts += 15
        long_factors.append(("Price above BB middle, below upper", "BULLISH ZONE", 15))
    elif bb_low < close < bb_mid:
        short_pts += 15
        short_factors.append(("Price below BB middle, above lower", "BEARISH ZONE", 15))

    # 4. MACD — 20 points
    if macd > sig:
        long_pts += 12
        long_factors.append(("MACD > Signal", "BULLISH", 12))
        if hist > 0:
            long_pts += 5
            long_factors.append(("MACD histogram > 0", "POSITIVE", 5))
        if hist > _num(p.macd_hist):
            long_pts += 3
            long_factors.append(("Histogram rising", "ACCELERATING", 3))
    elif macd < sig:
        short_pts += 12
        short_factors.append(("MACD < Signal", "BEARISH", 12))
        if hist < 0:
            short_pts += 5
            short_factors.append(("MACD histogram < 0", "NEGATIVE", 5))
        if hist < _num(p.macd_hist):
            short_pts += 3
            short_factors.append(("Histogram falling", "ACCELERATING", 3))

    # 5. Vortex — 15 points
    if vi_p > vi_m:
        long_pts += 15
        long_factors.append(("VI+ > VI-", "BULLISH", 15))
    elif vi_m > vi_p:
        short_pts += 15
        short_factors.append(("VI- > VI+", "BEARISH", 15))

    # 6. Relative volume — 5 points
    if rvol is not None and rvol >= 1.20:
        if close >= ema7:
            long_pts += 5
            long_factors.append(("RVOL >= 1.20", f"{rvol:.2f}x", 5))
        if close <= ema7:
            short_pts += 5
            short_factors.append(("RVOL >= 1.20", f"{rvol:.2f}x", 5))

    # 7. Candle confirmation — 5 points
    prev_high, prev_low = _num(p.High), _num(p.Low)
    if bool(x.candle_bull) and close > prev_high:
        long_pts += 5
        long_factors.append(("Bull candle breaks prior high", "CONFIRMED", 5))
    if bool(x.candle_bear) and close < prev_low:
        short_pts += 5
        short_factors.append(("Bear candle breaks prior low", "CONFIRMED", 5))

    # 8. Extension / chasing — 5 points (reward non-extended entries)
    bb_width = max(bb_up - bb_low, 0.0)
    if bb_width > 0:
        long_extension = (close - ema7) / bb_width
        short_extension = (ema7 - close) / bb_width
        if 0 <= long_extension <= 0.35:
            long_pts += 5
            long_factors.append(("Not overextended from EMA 7", "GOOD ENTRY DISTANCE", 5))
        if 0 <= short_extension <= 0.35:
            short_pts += 5
            short_factors.append(("Not overextended from EMA 7", "GOOD ENTRY DISTANCE", 5))

    direction = "LONG" if long_pts >= short_pts else "SHORT"
    score = max(long_pts, short_pts)
    factors = long_factors if direction == "LONG" else short_factors

    # Trade status is deliberately stricter than direction.
    if score >= TRADE_CANDIDATE:
        entry_status = "BUY SETUP" if direction == "LONG" else "SELL SETUP"
    elif score >= WATCH:
        entry_status = "WAIT FOR CONFIRMATION"
    else:
        entry_status = "NO TRADE"

    # Entry / stop / target. ATR is risk-management only.
    if direction == "LONG":
        entry = close
        structural_sl = min(bb_low, ema21) if bb_low is not None else ema21
        sl = min(structural_sl, close - 0.8 * atr) if atr else structural_sl
        if sl >= entry:
            sl = entry - (atr if atr else max(entry * 0.005, 1))
        risk_per_share = max(entry - sl, 0.01)
        target1 = entry + 1.5 * risk_per_share
        target2 = entry + 2.0 * risk_per_share
    else:
        entry = close
        structural_sl = max(bb_up, ema21) if bb_up is not None else ema21
        sl = max(structural_sl, close + 0.8 * atr) if atr else structural_sl
        if sl <= entry:
            sl = entry + (atr if atr else max(entry * 0.005, 1))
        risk_per_share = max(sl - entry, 0.01)
        target1 = entry - 1.5 * risk_per_share
        target2 = entry - 2.0 * risk_per_share

    qty = math.floor(MAX_RISK_RUPEES / risk_per_share) if risk_per_share > 0 else 0
    qty = max(0, qty)

    # Don't expose a trade instruction unless score is at least 80.
    actionable = score >= TRADE_CANDIDATE
    if not actionable:
        entry_for_ui = sl_for_ui = t1_for_ui = t2_for_ui = None
        qty_for_ui = 0
    else:
        entry_for_ui, sl_for_ui, t1_for_ui, t2_for_ui = entry, sl, target1, target2
        qty_for_ui = qty

    return {
        "valid": True,
        "score": int(score),
        "classification": classify(int(score)),
        "direction": direction,
        "entry_status": entry_status,
        "actionable": actionable,
        "price": _safe_round(close),
        "entry": _safe_round(entry_for_ui),
        "stop_loss": _safe_round(sl_for_ui),
        "target1": _safe_round(t1_for_ui),
        "target2": _safe_round(t2_for_ui),
        "risk_per_share": _safe_round(risk_per_share) if actionable else None,
        "quantity": qty_for_ui,
        "account_capital": ACCOUNT_CAPITAL,
        "max_risk": MAX_RISK_RUPEES,
        "rr_target1": 1.5 if actionable else None,
        "rr_target2": 2.0 if actionable else None,
        "metrics": {
            "ema7": _safe_round(ema7),
            "ema21": _safe_round(ema21),
            "bb_upper": _safe_round(bb_up),
            "bb_mid": _safe_round(bb_mid),
            "bb_lower": _safe_round(bb_low),
            "macd": _safe_round(macd, 4),
            "macd_signal": _safe_round(sig, 4),
            "macd_hist": _safe_round(hist, 4),
            "vi_plus": _safe_round(vi_p, 4),
            "vi_minus": _safe_round(vi_m, 4),
            "rvol": _safe_round(rvol, 2),
            "atr14": _safe_round(atr),
        },
        "factors": factors,
        "all_factors": {
            "long": long_factors,
            "short": short_factors,
        },
        "candle_time": str(d.index[-1]),
        "ema_cross": detect_latest_ema_cross(df),
    }
