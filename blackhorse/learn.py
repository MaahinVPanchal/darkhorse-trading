"""Learning loop: replay recent history, search strategy parameters, and write
PROPOSALS -- it never edits config.json itself.

This is what "learns from the market" honestly means: a closed feedback loop of
log -> measure -> re-optimize -> (human approves) -> apply. The train/validate
split exists because a parameter set that only fits the past is curve fitting,
not learning.

Indicators are precomputed once per (coin, parameter) pair and the replay is a
single O(bars) pass, so the whole grid search runs in seconds.
"""

import json
from statistics import mean

from . import market


def _ema_series(values, period):
    """Standard seeded EMA over the full series, single O(n) pass."""
    out = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    e = mean(values[:period])
    out[period - 1] = e
    for i in range(period, len(values)):
        e = values[i] * k + e * (1 - k)
        out[i] = e
    return out


def _precompute(candles, ema_fast, ema_slow, rsi_max, vol_ratio_min):
    closes = [c["close"] for c in candles]
    vols = [c["volume"] for c in candles]
    ef = _ema_series(closes, ema_fast)
    es = _ema_series(closes, ema_slow)
    # incremental RSI (Wilder), single pass
    r = [None] * len(closes)
    period = 14
    if len(closes) > period:
        gains, losses = [], []
        for i in range(1, period + 1):
            d = closes[i] - closes[i - 1]
            gains.append(max(d, 0.0))
            losses.append(max(-d, 0.0))
        avg_g, avg_l = mean(gains), mean(losses)
        r[period] = 100.0 - 100.0 / (1.0 + avg_g / avg_l) if avg_l else 100.0
        for i in range(period + 1, len(closes)):
            d = closes[i] - closes[i - 1]
            avg_g = (avg_g * (period - 1) + max(d, 0.0)) / period
            avg_l = (avg_l * (period - 1) + max(-d, 0.0)) / period
            r[i] = 100.0 - 100.0 / (1.0 + avg_g / avg_l) if avg_l else 100.0
    vr = [1.0] * len(closes)
    for i in range(21, len(closes)):
        vr[i] = vols[i] / max(mean(vols[i - 20:i]), 1e-9)
    return {"closes": closes, "ef": ef, "es": es, "r": r, "vr": vr,
            "rsi_max": rsi_max, "vol_ratio_min": vol_ratio_min}


def _backtest(candles, ind, tp_pct, sl_pct, fee_bps, slip_bps):
    closes, ef, es, r, vr = (ind[k] for k in
                             ("closes", "ef", "es", "r", "vr"))
    rsi_max, vol_ratio_min = ind["rsi_max"], ind["vol_ratio_min"]
    trades = []
    pos = None
    for i in range(1, len(candles)):
        if pos is not None:
            _, stop, target = pos
            exit_price = None
            if candles[i]["low"] <= stop:        # pessimistic: stop first
                exit_price = stop
            elif candles[i]["high"] >= target:
                exit_price = target
            elif ef[i] is not None and es[i] is not None and ef[i] <= es[i]:
                exit_price = closes[i]
            if exit_price is not None:
                entry_eff = pos[2] * (1 + slip_bps / 1e4)
                exit_eff = exit_price * (1 - slip_bps / 1e4)
                gross = (exit_eff / entry_eff - 1) * 100
                trades.append(gross - (fee_bps * 2) / 1e4 * 100)
                pos = None
        elif (ef[i] is not None and es[i] is not None
              and ef[i - 1] is not None and es[i - 1] is not None
              and ef[i] > es[i] and ef[i - 1] <= es[i - 1]
              and r[i] is not None and r[i] < rsi_max
              and vr[i] >= vol_ratio_min):
            pos = (i, closes[i] * (1 - sl_pct / 100),
                   closes[i] * (1 + tp_pct / 100))
    return trades


def _stats(trades):
    n = len(trades)
    if not n:
        return {"trades": 0, "win_rate": 0.0, "total": 0.0, "expectancy": 0.0}
    return {
        "trades": n,
        "win_rate": sum(1 for t in trades if t > 0) / n * 100,
        "total": sum(trades),
        "expectancy": sum(trades) / n,
    }


def run(cfg, out_path="learned_proposals.json"):
    fee_bps = cfg["fees"]["taker_bps"]
    slip_bps = cfg["fees"]["slippage_bps"]
    learn = cfg["learn"]
    st = cfg["strategy"]
    proposals = []
    for coin in cfg["symbols"]:
        candles = market.candles(coin, cfg["timeframe"], learn["lookback_bars"])
        if len(candles) < 300:
            print(f"  {coin}: only {len(candles)} candles, skipping")
            continue
        cut = int(len(candles) * 0.7)
        results = []
        for f in learn["ema_fast_options"]:
            for s in learn["ema_slow_options"]:
                if f >= s:
                    continue
                ind = _precompute(candles, f, s, st["rsi_max"], st["vol_ratio_min"])
                for tp in learn["tp_options"]:
                    for sl in learn["sl_options"]:
                        train = _stats(_backtest(
                            candles[:cut], ind, tp, sl, fee_bps, slip_bps))
                        valid = _stats(_backtest(
                            candles[cut:], ind, tp, sl, fee_bps, slip_bps))
                        if valid["trades"] < learn["min_trades_validate"]:
                            continue
                        results.append({
                            "coin": coin, "ema_fast": f, "ema_slow": s,
                            "take_profit_pct": tp, "stop_loss_pct": sl,
                            "train": train, "validate": valid,
                            "score": valid["expectancy"] * valid["trades"],
                        })
        results.sort(key=lambda x: x["score"], reverse=True)
        top = results[:3]
        proposals.extend(top)
        if top:
            b = top[0]
            print(f"  {coin}: best validation expectancy "
                  f"{b['validate']['expectancy']:+.3f}%/trade over "
                  f"{b['validate']['trades']} trades "
                  f"(train {b['train']['expectancy']:+.3f}% over "
                  f"{b['train']['trades']}) -> "
                  f"EMA {b['ema_fast']}/{b['ema_slow']} "
                  f"TP {b['take_profit_pct']}% SL {b['stop_loss_pct']}%")
        else:
            print(f"  {coin}: no parameter set produced enough validation trades")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(proposals, fh, indent=2)
    print(f"\nProposals written to {out_path} -- review them, then edit "
          f"config.json yourself if you accept one.")
    return proposals
