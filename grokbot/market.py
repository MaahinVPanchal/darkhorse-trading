"""Hyperliquid public market data. No API keys required for reads."""

import time

import requests

INFO_URL = "https://api.hyperliquid.xyz/info"


def _info(payload):
    r = requests.post(INFO_URL, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()


def all_mids():
    """Live mark prices for every perp symbol, e.g. {'BTC': 68000.0, ...}."""
    data = _info({"type": "allMids"})
    return {k: float(v) for k, v in data.items()}


def candles(coin, interval="15m", lookback_bars=200):
    """Recent OHLCV candles, oldest first."""
    now_ms = int(time.time() * 1000)
    start = now_ms - lookback_bars * _interval_ms(interval)
    rows = _info({"type": "candleSnapshot", "req": {
        "coin": coin, "interval": interval,
        "startTime": start, "endTime": now_ms,
    }})
    out = [{
        "t": int(r["t"]),
        "open": float(r["o"]),
        "high": float(r["h"]),
        "low": float(r["l"]),
        "close": float(r["c"]),
        "volume": float(r["v"]),
    } for r in rows]
    out.sort(key=lambda c: c["t"])
    return out


def _interval_ms(interval):
    mult = {"m": 60, "h": 3600, "d": 86400}
    return int(interval[:-1]) * mult[interval[-1]] * 1000
