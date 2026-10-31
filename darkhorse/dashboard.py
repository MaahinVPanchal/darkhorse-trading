"""Localhost dashboard: what is happening right now, in one page.

Stdlib only (no npm, no CDN). Serves:
  /          -> dark terminal-style HTML with equity curve (server-side SVG),
                agent status, open positions, decision feed, fills
  /api/data  -> the same data as JSON (for scripts or a future UI)

Point a browser at http://127.0.0.1:<port> -- `python run.py dashboard`
opens it automatically. The page refreshes itself every N seconds.
"""

import bisect
import json
import os
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import analyst, guards, market
from .journal import Journal

VERSION = "0.3.0"

MASK_KEYS = ["TYPESAFE_API_KEY", "TYPESAFE_AI_API_KEY", "NEBIUS_API_KEY",
             "XAI_API_KEY", "OPENROUTER_API_KEY", "ZAI_API_KEY"]


def _mask(value):
    if not value:
        return None
    return value[:4] + "..." + value[-4:] if len(value) > 12 else "set"


def _candles_map(cfg):
    out = {}
    for coin in cfg["symbols"]:
        try:
            out[coin] = market.candles(coin, cfg["timeframe"], 150)
        except Exception:
            pass
    return out


def _coin_pnl_series(journal):
    from collections import defaultdict
    rows = journal.conn.execute(
        "SELECT coin, pnl FROM fills WHERE side='sell' AND pnl IS NOT NULL "
        "ORDER BY id ASC").fetchall()
    cum, series = defaultdict(float), defaultdict(list)
    for r in rows:
        cum[r["coin"]] += r["pnl"]
        series[r["coin"]].append(cum[r["coin"]])
    return dict(series)


def _svg_curve(history, floor):
    """Server-side SVG equity curve: no JS, no CDN, works offline."""
    w, h, pad = 860, 240, 24
    pts = [x["total"] for x in history[-500:]]
    if len(pts) < 2:
        return ("<svg width='100%' height='{h}'><text x='20' y='60' fill='#8b949e'>"
                "collecting equity marks... run the bot a while longer</text></svg>"
                ).format(h=h)
    lo, hi = min(min(pts), floor if floor else min(pts)), max(pts)
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    span = hi - lo

    def xy(i, v):
        x = pad + i / (len(pts) - 1) * (w - 2 * pad)
        y = h - pad - (v - lo) / span * (h - 2 * pad)
        return x, y

    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in
                    (xy(i, v) for i, v in enumerate(pts)))
    parts = [f"<svg viewBox='0 0 {w} {h}' width='100%' height='{h}' "
             f"preserveAspectRatio='none'>"]
    if floor and lo <= floor <= hi:
        fx, fy = 0, xy(0, floor)[1]
        parts.append(f"<line x1='{pad}' y1='{fy:.1f}' x2='{w - pad}' "
                     f"y2='{fy:.1f}' stroke='#f85149' stroke-dasharray='6 4' "
                     f"stroke-width='1.5'/>")
        parts.append(f"<text x='{pad + 4}' y='{fy - 6:.1f}' fill='#f85149' "
                     f"font-size='12'>equity floor ${floor:.2f}</text>")
    color = "#3fb950" if pts[-1] >= pts[0] else "#f85149"
    parts.append(f"<polyline points='{path}' fill='none' stroke='{color}' "
                 f"stroke-width='2'/>")
    lx, ly = xy(len(pts) - 1, pts[-1])
    parts.append(f"<circle cx='{lx:.1f}' cy='{ly:.1f}' r='4' fill='{color}'/>")
    parts.append(f"<text x='{lx - 70:.1f}' y='{ly - 10:.1f}' fill='{color}' "
                 f"font-size='13'>${pts[-1]:.4f}</text>")
    parts.append("</svg>")
    return "".join(parts)


def _svg_multicurve(series_dict):
    """Per-coin cumulative realized PnL, one polyline per coin."""
    w, h, pad = 860, 200, 24
    colors = ["#3fb950", "#58a6ff", "#d29922", "#bc8cff"]
    all_pts = [v for pts in series_dict.values() for v in pts]
    if not all_pts:
        return ("<svg width='100%' height='" + str(h) + "'><text x='20' y='60' "
                "fill='#8b949e'>no closed trades yet</text></svg>")
    lo, hi = min(min(all_pts), 0), max(max(all_pts), 1e-9)
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    span = hi - lo
    nmax = max(len(pts) for pts in series_dict.values())
    parts = [f"<svg viewBox='0 0 {w} {h}' width='100%' height='{h}' "
             f"preserveAspectRatio='none'>",
             f"<line x1='{pad}' y1='{h - pad - (0 - lo) / span * (h - 2 * pad):.1f}' "
             f"x2='{w - pad}' y2='{h - pad - (0 - lo) / span * (h - 2 * pad):.1f}' "
             f"stroke='#30363d' stroke-width='1'/>"]
    for i, (coin, pts) in enumerate(series_dict.items()):
        color = colors[i % len(colors)]
        path = " ".join(
            f"{pad + j / max(nmax - 1, 1) * (w - 2 * pad):.1f},"
            f"{h - pad - (v - lo) / span * (h - 2 * pad):.1f}"
            for j, v in enumerate(pts))
        parts.append(f"<polyline points='{path}' fill='none' "
                     f"stroke='{color}' stroke-width='2'/>")
        parts.append(f"<text x='{pad + i * 130 + 4}' y='16' fill='{color}' "
                     f"font-size='12'>{coin} ${pts[-1]:+.4f}</text>")
    parts.append("</svg>")
    return "".join(parts)


def _round_trips(journal):
    """Pair buys/sells into closed round trips, oldest first."""
    rows = journal.conn.execute(
        "SELECT * FROM fills ORDER BY id ASC").fetchall()
    open_map, trips = {}, []
    for r in rows:
        r = dict(r)
        if r["side"] == "buy":
            open_map.setdefault(r["coin"], []).append(r)
        elif r["side"] == "sell":
            queue = open_map.get(r["coin"])
            if queue:
                b = queue.pop(0)
                trips.append({"coin": r["coin"], "entry_ts": b["ts"],
                              "entry_px": b["price"], "exit_ts": r["ts"],
                              "exit_px": r["price"], "pnl": r["pnl"],
                              "kind": r["kind"]})
    return trips


def _iso_to_ms(ts):
    try:
        return datetime.fromisoformat(ts).timestamp() * 1000
    except Exception:
        return None


def _svg_trade_chart(coin, candles, trips, position):
    """Candlestick chart with entry/exit markers for every transaction."""
    w, h, pad = 860, 240, 34
    N = 120
    candles = candles[-N:]
    n = len(candles)
    if n < 5:
        return (f"<svg width='100%' height='{h}'><text x='20' y='60' "
                f"fill='#8b949e'>{coin}: collecting candles...</text></svg>")
    lo = min(c["low"] for c in candles)
    hi = max(c["high"] for c in candles)
    if position:
        lo = min(lo, position["stop"], position["avg_price"])
        hi = max(hi, position["target"], position["avg_price"])
    span = (hi - lo) or 1.0

    def y(price):
        return h - pad - (price - lo) / span * (h - 2 * pad)

    times = [c["t"] for c in candles]
    step = (w - 2 * pad) / n
    body_w = max(step * 0.62, 1.4)

    parts = [f"<svg viewBox='0 0 {w} {h}' width='100%' height='{h}' "
             f"preserveAspectRatio='none'>"]
    if position:  # open position: entry line + stop/target zones
        ey = y(position["avg_price"])
        parts.append(f"<line x1='{pad}' y1='{ey:.1f}' x2='{w - pad}' "
                     f"y2='{ey:.1f}' stroke='#58a6ff' stroke-dasharray='4 3' "
                     f"stroke-width='1'/>")
        parts.append(f"<text x='{pad + 4}' y='{ey - 4:.1f}' fill='#58a6ff' "
                     f"font-size='11'>entry {position['avg_price']:.2f}</text>")
        for lvl, col, name in ((position["target"], "#3fb950", "TP"),
                               (position["stop"], "#f85149", "SL")):
            ly = y(lvl)
            parts.append(f"<line x1='{pad}' y1='{ly:.1f}' x2='{w - pad}' "
                         f"y2='{ly:.1f}' stroke='{col}' "
                         f"stroke-dasharray='2 4' stroke-width='1'/>")
            parts.append(f"<text x='{w - pad - 70}' y='{ly - 4:.1f}' "
                         f"fill='{col}' font-size='11'>{name} {lvl:.2f}</text>")

    for i, c in enumerate(candles):
        x = pad + i * step + step / 2
        col = "#3fb950" if c["close"] >= c["open"] else "#f85149"
        parts.append(f"<line x1='{x:.1f}' y1='{y(c['low']):.1f}' "
                     f"x2='{x:.1f}' y2='{y(c['high']):.1f}' "
                     f"stroke='{col}' stroke-width='1'/>")
        yo, yc = y(c["open"]), y(c["close"])
        top, hgt = min(yo, yc), max(abs(yo - yc), 1.0)
        parts.append(f"<rect x='{x - body_w / 2:.1f}' y='{top:.1f}' "
                     f"width='{body_w:.1f}' height='{hgt:.1f}' fill='{col}'/>")

    def marker(ts_ms, price, kind, pnl):
        i = bisect.bisect_left(times, ts_ms)
        i = min(max(i - 1, 0), n - 1)
        x = pad + i * step + step / 2
        yp = y(price)
        if kind == "entry":
            parts.append(f"<polygon points='{x:.1f},{yp + 7:.1f} "
                         f"{x - 5:.1f},{yp + 14:.1f} {x + 5:.1f},{yp + 14:.1f}' "
                         f"fill='#58a6ff'/>")
        else:
            col = "#3fb950" if (pnl or 0) >= 0 else "#f85149"
            parts.append(f"<circle cx='{x:.1f}' cy='{yp - 9:.1f}' r='4.5' "
                         f"fill='{col}'/>")

    for t in trips:
        if t["coin"] != coin:
            continue
        ems, xms = _iso_to_ms(t["entry_ts"]), _iso_to_ms(t["exit_ts"])
        if ems and times[0] - 3600e3 <= ems <= times[-1] + 3600e3:
            marker(ems, t["entry_px"], "entry", None)
        if xms and times[0] - 3600e3 <= xms <= times[-1] + 3600e3:
            marker(xms, t["exit_px"], "exit", t["pnl"])

    last = candles[-1]["close"]
    parts.append(f"<text x='{w - pad - 90}' y='16' fill='#c9d1d9' "
                 f"font-size='12'>{coin} last {last:.2f}</text>")
    parts.append("</svg>")
    return "".join(parts)


def build_data(cfg, journal):
    prices = {}
    try:
        prices = market.all_mids()
    except Exception:
        pass
    stats = journal.trade_stats()
    eq = journal.latest_equity()
    hist = journal.equity_history()
    floor, floor_desc = guards.effective_floor(cfg)
    positions = []
    for p in journal.all_positions():
        mark = prices.get(p["coin"], p["avg_price"])
        positions.append({**p, "mark": mark,
                          "upnl": p["qty"] * (mark - p["avg_price"])})
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    budget = cfg["analyst"].get("budget", {})
    provider = analyst.available(cfg)
    keys = [{"name": k, "status": _mask(os.environ.get(k))}
            for k in MASK_KEYS]
    fills = []
    for f in journal.fills(25):
        fills.append({**f, "pnl": f["pnl"]})
    decisions = []
    for d in journal.conn.execute(
            "SELECT * FROM decisions ORDER BY id DESC LIMIT 120"):
        decisions.append(dict(d))
    return {
        "version": VERSION,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "equity": eq, "history": hist[-500:],
        "floor": floor, "floor_desc": floor_desc,
        "halted": guards.is_halted(journal),
        "halt_reason": journal.get_state("halt_reason"),
        "start_balance": cfg["paper"]["start_balance_usd"],
        "stats": stats, "positions": positions,
        "fees_paid": journal.total_fees(),
        "coin_pnl_series": _coin_pnl_series(journal),
        "round_trips": _round_trips(journal),
        "candles_map": _candles_map(cfg),
        "all_fills": journal.fills(500),
        "fills": fills, "decisions": decisions,
        "analyst": {"enabled": cfg["analyst"].get("enabled", False),
                    "mode": cfg["analyst"].get("mode"), "provider": provider,
                    "model": cfg["analyst"].get("model"),
                    "calls_today": int(journal.get_state(
                        f"analyst_calls_{day}", "0")),
                    "tokens_today": int(journal.get_state(
                        f"analyst_tokens_{day}", "0")),
                    "call_cap": budget.get("daily_call_cap"),
                    "token_cap": budget.get("daily_input_token_cap")},
        "keys": keys,
    }


PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<title>Darkhorse - live paper desk</title>
<meta http-equiv="refresh" content="{refresh}">
<style>
  body{{background:#0d1117;color:#c9d1d9;font-family:Consolas,'Courier New',monospace;
       margin:0;padding:18px;}}
  h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:14px;color:#58a6ff;margin:22px 0 8px;
     border-bottom:1px solid #21262d;padding-bottom:4px}}
  .row{{display:flex;gap:14px;flex-wrap:wrap}}
  .card{{background:#161b22;border:1px solid #21262d;border-radius:8px;
        padding:10px 14px;min-width:130px}}
  .card .k{{font-size:11px;color:#8b949e}} .card .v{{font-size:18px;margin-top:2px}}
  .up{{color:#3fb950}} .down{{color:#f85149}} .warn{{color:#d29922}}
  table{{border-collapse:collapse;width:100%;font-size:12px}}
  td,th{{border-bottom:1px solid #21262d;padding:4px 8px;text-align:left;white-space:normal}}
  th{{color:#8b949e;font-weight:normal}}
  .feed td{{white-space:normal}} .tag{{font-size:10px;padding:1px 6px;border-radius:8px}}
  .tag.code{{background:#1f6feb33;color:#58a6ff}} .tag.llm{{background:#8957e533;color:#d2a8ff}}
  .muted{{color:#8b949e}} .banner{{padding:10px 14px;border-radius:8px;margin:10px 0}}
  .scroll{{max-height:360px;overflow-y:auto;border:1px solid #21262d;
          border-radius:6px}}
  .halt{{background:#f8514922;border:1px solid #f85149;color:#f85149}}
</style></head><body>
<h1>DARKHORSE <span class="muted">live paper desk</span></h1>
<div class="muted">updated {ts} &middot; refreshes every {refresh}s &middot; v{version}</div>
{halt_banner}
<div class="row">
  <div class="card"><div class="k">EQUITY</div><div class="v">{eq_html}</div></div>
  <div class="card"><div class="k">RETURN / START ${start}</div><div class="v">{ret_html}</div></div>
  <div class="card"><div class="k">MAX DRAWDOWN</div><div class="v">{dd}</div></div>
  <div class="card"><div class="k">WIN RATE / TRADES</div><div class="v">{wr}</div></div>
  <div class="card"><div class="k">EXPECTANCY / TRADE</div><div class="v">{exp_html}</div></div>
  <div class="card"><div class="k">PROFIT FACTOR</div><div class="v">{pf}</div></div>
  <div class="card"><div class="k">FEES PAID</div><div class="v">{fees}</div></div>
  <div class="card"><div class="k">EQUITY FLOOR</div><div class="v warn">{floor}</div></div>
</div>

<h2>equity curve</h2>
{curve}

<div class="row">
<div style="flex:1;min-width:340px">
{coin_section}

<h2>trade map -- every transaction on the price chart</h2>
{trade_map}

<div class="row">
<div style="flex:1;min-width:340px">
<h2>closed trades ({n_trips})</h2>
{trips_html}

<h2>all transactions ({n_fills})</h2>
{all_fills_html}
</div>

<div style="flex:1.2;min-width:380px">
<h2>agent hive &mdash; who is connected, with what</h2>
<table>
  <tr><th>agent</th><th>key / connection</th><th>power</th></tr>
  <tr><td>Signal (strategy.py)</td><td class="muted">local code, no key</td>
      <td>proposes enter/exit</td></tr>
  <tr><td>Risk Officer (risk.py)</td><td class="muted">local code, no key</td>
      <td>veto: caps, cooldown, loss limit</td></tr>
  <tr><td>Execution (paper.py)</td><td class="muted">local code, no key</td>
      <td>paper fills + TP/SL (live later: trade-only API wallet)</td></tr>
  <tr><td>Account Guard (guards.py)</td><td class="muted">local code, no key</td>
      <td>equity floor ${floor} &rarr; flatten + halt</td></tr>
  <tr><td>Analyst ({a_provider})</td>
      <td>{a_key_line}</td>
      <td>{a_power}</td></tr>
  <tr><td>Coach (learn.py)</td><td class="muted">local code, no key</td>
      <td>proposals only; human applies</td></tr>
</table>
<p class="muted" style="font-size:11px">analyst budget today: {a_calls}/{a_call_cap} calls,
{a_toks}/{a_tok_cap} input tokens. keys on this machine:
{key_list}</p>

<h2>open positions</h2>
{positions_html}

<h2>recent fills</h2>
{fills_html}
</div>

<div style="flex:1.2;min-width:380px">
<h2>decision feed &mdash; what the agents are saying</h2>
<table class="feed">
  <tr><th>time (UTC)</th><th>who</th><th>coin</th><th>decision</th></tr>
  {feed_rows}
</table>
</div>
</div>
</body></html>"""


def _fmt_pnl(v):
    """Signed dollar value with color, e.g. '+$0.0123'."""
    if v is None:
        return "&mdash;"
    cls = "up" if v > 0 else ("down" if v < 0 else "")
    return f"<span class='{cls}'>{'+' if v > 0 else '-'}${abs(v):.4f}</span>"


def render(data, cfg):
    hist = data["history"]
    if len(hist) >= 2:
        dd = max((max(x["total"] for x in hist[:i + 1]) - hist[i]["total"])
                 / max(x["total"] for x in hist[:i + 1]) * 100
                 for i in range(1, len(hist)))
    else:
        dd = 0.0
    s = data["stats"]
    eq = data["equity"]["total"] if data["equity"] else data["start_balance"]
    ret = (eq / data["start_balance"] - 1) * 100 if data["start_balance"] else 0
    a = data["analyst"]
    key_line = "no API key on this machine &rarr; rules-only fallback"
    if a["provider"] == "budget":
        key_line = "<span class='warn'>daily budget spent &rarr; rules-only</span>"
    elif a["provider"]:
        key_line = f"provider <b>{a['provider']}</b>, model {a['model'] or 'default'}"
    a_power = "disabled" if not a["enabled"] else (
        "veto gate on entries" if a["mode"] == "gate" else "log-only opinions")
    feed_rows = []
    for d in data["decisions"]:
        who = "<span class='tag code'>CODE</span>"
        if d["analyst_note"]:
            who = "<span class='tag llm'>CODE+LLM</span>"
        note = f"<div class='muted'>{d['analyst_note']}</div>" if d["analyst_note"] else ""
        act = d["action"]
        cls = "up" if act == "enter" else ("down" if act in ("exit", "halt") else "muted")
        feed_rows.append(
            f"<tr><td>{(d['ts'] or '')[11:19]}</td><td>{who}</td>"
            f"<td>{d['coin']}</td><td><span class='{cls}'>{act.upper()}</span> "
            f"{d['reason'] or ''}{note}</td></tr>")
    fills_html = ""
    if data["fills"]:
        rows = []
        for f in data["fills"]:
            pnl = (f"<span class='{'up' if f['pnl'] > 0 else 'down'}'>"
                   f"{f['pnl']:+.4f}</span>") if f["pnl"] is not None else ""
            rows.append(f"<tr><td>{f['ts'][11:19]}</td><td>{f['coin']}</td>"
                        f"<td>{f['side']}</td><td>{f['qty']:.6f} @ {f['price']:.2f}</td>"
                        f"<td>{f['kind']}</td><td>{pnl}</td></tr>")
        fills_html = ("<table><tr><th>time</th><th>coin</th><th>side</th>"
                      "<th>fill</th><th>kind</th><th>pnl</th></tr>"
                      + "".join(rows) + "</table>")
    else:
        fills_html = "<p class='muted'>no closed trades yet -- the signal engine is waiting for a fresh EMA cross with volume.</p>"
    pos_html = ""
    if data["positions"]:
        rows = []
        for p in data["positions"]:
            cls = "up" if p["upnl"] >= 0 else "down"
            rows.append(f"<tr><td>{p['coin']}</td>"
                        f"<td>{p['qty']:.6f} @ {p['avg_price']:.2f}</td>"
                        f"<td>mark {p['mark']:.2f}</td>"
                        f"<td class='{cls}'>{p['upnl']:+.4f}</td>"
                        f"<td class='muted'>stop {p['stop']:.2f} / target {p['target']:.2f}</td></tr>")
        pos_html = ("<table><tr><th>coin</th><th>entry</th><th>mark</th>"
                    "<th>unrealized</th><th>exits</th></tr>" + "".join(rows) + "</table>")
    else:
        pos_html = "<p class='muted'>flat -- no open positions.</p>"
    key_list = ", ".join(
        f"{k['name']}={k['status']}" if k["status"]
        else f"<span class='muted'>{k['name']}=not set</span>"
        for k in data["keys"])
    coin_curve = _svg_multicurve(data["coin_pnl_series"])
    coin_section = ("<h2>realized pnl by coin (cumulative, per closed trade)</h2>"
                    + coin_curve)

    pos_by_coin = {p["coin"]: p for p in data["positions"]}
    charts = []
    for coin in cfg["symbols"]:
        charts.append(f"<h3 style='margin:14px 0 2px;font-size:12px;color:#8b949e'>"
                      f"{coin} -- {cfg['timeframe']} candles, markers = your "
                      f"transactions</h3>")
        charts.append(_svg_trade_chart(
            coin, data["candles_map"].get(coin, []),
            data["round_trips"], pos_by_coin.get(coin)))
    trade_map = "".join(charts)

    if data["all_fills"]:
        frows = []
        for f in data["all_fills"]:
            pnl = (f"<span class='{'up' if f['pnl'] > 0 else 'down'}'>"
                   f"{f['pnl']:+.4f}</span>") if f["pnl"] is not None else ""
            frows.append(f"<tr><td>{f['ts'][:19]}</td><td>{f['coin']}</td>"
                         f"<td>{f['side']}</td><td>{f['qty']:.6f} @ "
                         f"{f['price']:.2f}</td><td>{f['notional']:.2f}</td>"
                         f"<td>{f['fee']:.4f}</td><td>{f['kind']}</td>"
                         f"<td>{pnl}</td></tr>")
        all_fills_html = (
            f"<div class='scroll'><table><tr><th>time (UTC)</th><th>coin</th>"
            f"<th>side</th><th>fill</th><th>notional $</th><th>fee</th>"
            f"<th>kind</th><th>pnl</th></tr>" + "".join(frows) +
            f"</table></div><div class='muted'>{len(data['all_fills'])} "
            f"transactions total -- every one journaled</div>")
    else:
        all_fills_html = "<p class='muted'>no transactions yet</p>"

    trips = data["round_trips"]
    if trips:
        trows = []
        for t in trips:
            cls = "up" if t["pnl"] >= 0 else "down"
            trows.append(
                f"<tr><td>{t['entry_ts'][:16].replace('T', ' ')}</td>"
                f"<td>{t['coin']}</td>"
                f"<td>in ${t['entry_px']:.2f}</td>"
                f"<td>{t['exit_ts'][:16].replace('T', ' ')}</td>"
                f"<td>out ${t['exit_px']:.2f}</td>"
                f"<td>{t['kind']}</td>"
                f"<td class='{cls}'>{t['pnl']:+.4f}</td></tr>")
        trips_html = ("<div class='scroll'><table><tr><th>entry</th><th>coin</th>"
                      "<th>entry px</th><th>exit</th><th>exit px</th>"
                      "<th>kind</th><th>pnl</th></tr>" + "".join(trows) +
                      "</table></div>")
    else:
        trips_html = "<p class='muted'>no closed round trips yet</p>"
    halt_banner = ""
    if data["halted"]:
        halt_banner = f"<div class='banner halt'>HALTED: {data['halt_reason']} -- run resume.bat to re-enable</div>"
    pf = f"{s['profit_factor']:.2f}" if s["profit_factor"] else "&mdash;"
    return PAGE.format(
        refresh=cfg.get("dashboard", {}).get("refresh_seconds", 15),
        ts=data["ts"], version=data["version"], halt_banner=halt_banner,
        eq_html=f"${eq:.4f}", start=data["start_balance"],
        ret_html=f"<span class='{'up' if ret >= 0 else 'down'}'>{ret:+.2f}%</span>",
        dd=f"{dd:.2f}%", wr=f"{s['win_rate']:.1f}% / {s['trades']}",
        exp_html=_fmt_pnl(s["expectancy"]), pf=pf,
        fees=f"${data['fees_paid']:.4f}",
        floor=f"${data['floor']:.2f}", curve=_svg_curve(hist, data["floor"]),
        coin_section=coin_section, trade_map=trade_map,
        trips_html=trips_html, all_fills_html=all_fills_html,
        n_trips=len(trips), n_fills=len(data["all_fills"]),
        a_provider=a["provider"] or "rules-only", a_key_line=key_line,
        a_power=a_power, a_calls=a["calls_today"],
        a_call_cap=a["call_cap"] or 0, a_toks=a["tokens_today"],
        a_tok_cap=a["token_cap"] or 0, key_list=key_list,
        positions_html=pos_html, fills_html=fills_html,
        feed_rows="".join(feed_rows))


def serve(cfg, open_browser=True):
    port = cfg.get("dashboard", {}).get("port", 8765)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            # one connection per request: ThreadingHTTPServer handles each
            # request in its own thread, and sqlite3 objects are thread-bound
            journal = Journal()
            try:
                path = urlparse(self.path).path
                if path == "/api/data":
                    body = json.dumps(build_data(cfg, journal)).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif path == "/":
                    data = build_data(cfg, journal)
                    html = render(data, cfg).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html)))
                    self.end_headers()
                    self.wfile.write(html)
                else:
                    self.send_response(404)
                    self.end_headers()
            finally:
                journal.conn.close()

    url = f"http://127.0.0.1:{port}"
    print(f"Dashboard on {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("dashboard stopped")
