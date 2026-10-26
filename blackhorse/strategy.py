"""Deterministic signal engine: EMA trend cross + RSI + volume filter.

Every input is a plain number, every output is logged, so any trade can be
replayed and explained later. The LLM layer (analyst.py) is advisory on top of
this -- it never replaces it.
"""

from statistics import mean


def ema(values, period):
    if values is None or len(values) < period:
        return None
    k = 2.0 / (period + 1)
    e = mean(values[:period])
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g, avg_l = mean(gains), mean(losses)
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0.0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0.0)) / period
    if avg_l == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_g / avg_l)


def evaluate(candles, params):
    """Return {action: enter|exit|wait, reason, indicators...} for the latest bar."""
    closes = [c["close"] for c in candles]
    vols = [c["volume"] for c in candles]

    fast = ema(closes, params["ema_fast"])
    slow = ema(closes, params["ema_slow"])
    if fast is None or slow is None:
        return {"action": "wait", "reason": "not enough history"}

    prev_fast = ema(closes[:-1], params["ema_fast"])
    prev_slow = ema(closes[:-1], params["ema_slow"])
    fresh_cross = (prev_fast is not None and prev_slow is not None
                   and prev_fast <= prev_slow and fast > slow)

    r = rsi(closes) or 50.0
    vol_ratio = 1.0
    if len(vols) >= 22:
        vol_ratio = vols[-1] / max(mean(vols[-21:-1]), 1e-9)

    filters_ok = r < params["rsi_max"] and vol_ratio >= params["vol_ratio_min"]

    if fast > slow and fresh_cross and filters_ok:
        action = "enter"
        reason = (f"fresh EMA cross up (fast {fast:.1f} > slow {slow:.1f}), "
                  f"RSI {r:.0f}, vol x{vol_ratio:.1f}")
    elif fast <= slow:
        action = "exit"
        reason = f"EMA fast below slow (fast {fast:.1f}, slow {slow:.1f}, RSI {r:.0f})"
    else:
        action = "wait"
        reason = (f"trend up but entry filters unmet "
                  f"(cross={fresh_cross}, RSI {r:.0f}, vol x{vol_ratio:.1f})")

    return {
        "action": action,
        "reason": reason,
        "ema_fast": fast,
        "ema_slow": slow,
        "rsi": r,
        "vol_ratio": vol_ratio,
    }
