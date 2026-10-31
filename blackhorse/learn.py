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


def _precompute(candles, engine, p1, p2, rsi_max, vol_ratio_min):
    """Engine-aware indicator precompute, single O(n) pass per parameter.
    trend: p1=ema_fast, p2=ema_slow. meanrev: p1=rsi_buy, p2=rsi_exit."""
    closes = [c["close"] for c in candles]
    vols = [c["volume"] for c in candles]
    ef = es = None
    if engine == "trend":
        ef = _ema_series(closes, p1)
        es = _ema_series(closes, p2)
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
            "engine": engine, "p1": p1, "p2": p2,
            "rsi_max": rsi_max, "vol_ratio_min": vol_ratio_min}


def _backtest(candles, ind, tp_pct, sl_pct, fee_bps, slip_bps):
    closes, ef, es, r, vr = (ind[k] for k in
                             ("closes", "ef", "es", "r", "vr"))
    rsi_max, vol_ratio_min = ind["rsi_max"], ind["vol_ratio_min"]
    engine, p1, p2 = ind["engine"], ind["p1"], ind["p2"]
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
            elif engine == "trend" and ef[i] is not None and es[i] is not None \
                    and ef[i] <= es[i]:
                exit_price = closes[i]
            elif engine == "meanrev" and r[i] is not None and r[i] >= p2:
                exit_price = closes[i]
            if exit_price is not None:
                entry_eff = pos[2] * (1 + slip_bps / 1e4)
                exit_eff = exit_price * (1 - slip_bps / 1e4)
                gross = (exit_eff / entry_eff - 1) * 100
                trades.append(gross - (fee_bps * 2) / 1e4 * 100)
                pos = None
        elif engine == "trend" and (
                ef[i] is not None and es[i] is not None
                and ef[i - 1] is not None and es[i - 1] is not None
                and ef[i] > es[i] and ef[i - 1] <= es[i - 1]
                and r[i] is not None and r[i] < rsi_max
                and vr[i] >= vol_ratio_min):
            pos = (i, closes[i] * (1 - sl_pct / 100),
                   closes[i] * (1 + tp_pct / 100))
        elif engine == "meanrev" and (
                r[i] is not None and r[i - 1] is not None
                and r[i - 1] >= p1 and r[i] < p1
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
    engines = learn.get("engines", ["trend"])
    proposals = []
    for coin in cfg["symbols"]:
        candles = market.candles(coin, cfg["timeframe"], learn["lookback_bars"])
        if len(candles) < 300:
            print(f"  {coin}: only {len(candles)} candles, skipping")
            continue
        cut = int(len(candles) * 0.7)
        # NexusTrade-style embargo: skip bars between train and validation so
        # indicator warm-up (EMA seeds, RSI window) can't leak across the split
        embargo = learn.get("embargo_bars", 20)
        results = []
        param_grids = {
            "trend": [(f, s) for f in learn["ema_fast_options"]
                      for s in learn["ema_slow_options"] if f < s],
            "meanrev": [(b, x) for b in learn.get("rsi_buy_options", [30])
                        for x in learn.get("rsi_exit_options", [55]) if b < x],
        }
        for engine in engines:
            for p1, p2 in param_grids.get(engine, []):
                ind = _precompute(candles, engine, p1, p2,
                                  st["rsi_max"], st["vol_ratio_min"])
                for tp in learn["tp_options"]:
                    for sl in learn["sl_options"]:
                        train = _stats(_backtest(
                            candles[:cut], ind, tp, sl, fee_bps, slip_bps))
                        valid = _stats(_backtest(
                            candles[cut + embargo:], ind, tp, sl, fee_bps, slip_bps))
                        if valid["trades"] < learn["min_trades_validate"]:
                            continue
                        row = {
                            "coin": coin, "engine": engine,
                            "take_profit_pct": tp, "stop_loss_pct": sl,
                            "train": train, "validate": valid,
                            "score": valid["expectancy"] * valid["trades"],
                        }
                        if engine == "trend":
                            row.update({"ema_fast": p1, "ema_slow": p2})
                        else:
                            row.update({"rsi_buy": p1, "rsi_exit": p2})
                        results.append(row)
        results.sort(key=lambda x: x["score"], reverse=True)
        top = results[:3]
        proposals.extend(top)
        if top:
            b = top[0]
            if b["engine"] == "trend":
                ptxt = f"EMA {b['ema_fast']}/{b['ema_slow']}"
            else:
                ptxt = f"RSI buy<{b['rsi_buy']} exit>={b['rsi_exit']}"
            print(f"  {coin}: best [{b['engine']}] validation expectancy "
                  f"{b['validate']['expectancy']:+.3f}%/trade over "
                  f"{b['validate']['trades']} trades "
                  f"(train {b['train']['expectancy']:+.3f}% over "
                  f"{b['train']['trades']}) -> {ptxt} "
                  f"TP {b['take_profit_pct']}% SL {b['stop_loss_pct']}%")
        else:
            print(f"  {coin}: no parameter set produced enough validation trades")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(proposals, fh, indent=2)
    print(f"\nProposals written to {out_path} -- review them, then edit "
          f"config.json yourself if you accept one.")
    return proposals
