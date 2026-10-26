#!/usr/bin/env python
"""Grokbot CLI.

  python run.py paper            run paper trading continuously (Ctrl-C to stop)
  python run.py paper --once     one single cycle
  python run.py paper --cycles N run N cycles
  python run.py report           performance summary from the journal
  python run.py learn            walk-forward parameter search -> proposals
  python run.py live             refuses unless config live.enabled is true
"""

import argparse
import json
import sys

from grokbot import dashboard, doctor, guards, learn, loop, market
from grokbot.journal import Journal
from grokbot.paper import PaperBroker


def load_cfg():
    with open("config.json", encoding="utf-8") as fh:
        return json.load(fh)


def cmd_paper(cfg, args):
    journal = Journal()
    broker = PaperBroker(journal, cfg)
    print(f"Paper trading {cfg['symbols']} on {cfg['timeframe']} candles, "
          f"start balance ${cfg['paper']['start_balance_usd']}. "
          f"Ctrl-C to stop.\n")
    try:
        loop.run(journal, broker, cfg,
                 cycles=(1 if args.once else args.cycles),
                 use_analyst=True)
    except KeyboardInterrupt:
        print("\nStopped. Journal saved in grokbot.db -- run `python run.py report`.")


def cmd_report(cfg, args):
    journal = Journal()
    stats = journal.trade_stats()
    eq = journal.latest_equity()
    start = cfg["paper"]["start_balance_usd"]
    floor, floor_desc = guards.effective_floor(cfg)
    print("=" * 60)
    print("GROKBOT PAPER REPORT")
    print("=" * 60)
    if guards.is_halted(journal):
        print(f"*** HALTED: {journal.get_state('halt_reason')} ***")
        print(f"*** run 'python run.py resume' to re-enable trading ***")
    print(f"equity floor:   ${floor:.2f} ({floor_desc})")
    if eq:
        print(f"latest equity:  ${eq['total']:.4f}  "
              f"(cash ${eq['cash']:.4f}, unrealized ${eq['unrealized']:.4f})")
        ret = (eq["total"] / start - 1) * 100 if start else 0.0
        print(f"return on start balance (${start}): {ret:+.2f}%")
    hist = journal.equity_history()
    if hist:
        peak = max(h["total"] for h in hist)
        max_dd = max((peak - h["total"]) / peak * 100 for h in hist) if peak > 0 else 0.0
        print(f"equity peak:    ${peak:.4f}   max drawdown: {max_dd:.2f}%")
    fees = journal.total_fees()
    notional = journal.traded_notional()
    print(f"closed trades:  {stats['trades']}")
    print(f"win rate:       {stats['win_rate']:.1f}%")
    print(f"total pnl:      ${stats['total_pnl']:+.4f}")
    print(f"expectancy:     ${stats['expectancy']:+.4f} per trade")
    if stats["profit_factor"] is not None:
        print(f"profit factor:  {stats['profit_factor']:.2f} "
              f"(gross win ${stats['gross_win']:.4f} / gross loss "
              f"${stats['gross_loss']:.4f}; >1.5 before trusting)")
    print(f"avg win/loss:   ${stats['avg_win']:+.4f} / ${stats['avg_loss']:+.4f} "
          f"(best ${stats['best']:+.4f}, worst ${stats['worst']:+.4f})")
    print(f"fees paid:      ${fees:.4f} on ${notional:.2f} traded notional"
          + (f" ({fees / notional * 100:.3f}%)" if notional else ""))
    print(f"decisions logged: {journal.decision_count()}")
    if stats["by_coin"]:
        print("\nby coin:")
        for coin, c in sorted(stats["by_coin"].items()):
            wr = c["wins"] / c["n"] * 100 if c["n"] else 0
            print(f"  {coin:<6} {c['n']:>4} trades  win {wr:5.1f}%  "
                  f"pnl ${c['pnl']:+.4f}")
    print("\nlast fills:")
    for f in journal.fills(10):
        pnl = f"  pnl {f['pnl']:+.4f}" if f["pnl"] is not None else ""
        print(f"  [{f['ts']}] {f['side']:<4} {f['coin']:<6} "
              f"{f['qty']:.6f} @ {f['price']:.2f} ({f['kind']}){pnl}")
    open_pos = journal.all_positions()
    if open_pos:
        print("\nopen positions:")
        prices = market.all_mids()
        for p in open_pos:
            mark = prices.get(p["coin"], p["avg_price"])
            upnl = p["qty"] * (mark - p["avg_price"])
            print(f"  {p['coin']:<6} {p['qty']:.6f} @ {p['avg_price']:.2f} "
                  f"mark {mark:.2f}  unrealized {upnl:+.4f}  "
                  f"stop {p['stop']:.2f} target {p['target']:.2f}")
    print("=" * 60)


def cmd_resume(cfg, args):
    journal = Journal()
    if guards.is_halted(journal):
        print(f"halt reason was: {journal.get_state('halt_reason')}")
        guards.resume(journal)
        print("Halt cleared. Trading re-enabled -- make sure you understand "
              "why it halted first.")
    else:
        print("Not halted.")


def cmd_learn(cfg, args):
    print("Running walk-forward parameter search (train 70% / validate 30%)...")
    learn.run(cfg)


def cmd_live(cfg, args):
    print("Real-money trading is disabled in config.json (live.enabled=false).")
    print("This is deliberate. Before enabling it you must:")
    print("  1. run paper mode for several weeks with positive expectancy")
    print("  2. practice on Hyperliquid TESTNET with a trade-only API wallet")
    print("  3. accept that perps can liquidate the whole account")
    print("  4. clear the India access/tax questions with a qualified adviser")
    print("Even then, the engine refuses to start unless config.json has")
    print('  live.acknowledgement = "I-ACCEPT-REAL-MONEY-RISK"')
    print("The live execution adapter is intentionally not implemented yet.")
    sys.exit(1)


def cmd_dashboard(cfg, args):
    dashboard.serve(cfg, open_browser=not args.no_browser)


def cmd_doctor(cfg, args):
    ok = doctor.run(cfg)
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description="Grokbot paper trading bot")
    ap.add_argument("command",
                    choices=["paper", "report", "learn", "live", "resume",
                             "dashboard", "doctor"])
    ap.add_argument("--once", action="store_true", help="run a single cycle")
    ap.add_argument("--cycles", type=int, default=None, help="run N cycles")
    ap.add_argument("--no-browser", action="store_true",
                    help="dashboard: do not open a browser window")
    args = ap.parse_args()
    cfg = load_cfg()
    {"paper": lambda: cmd_paper(cfg, args),
     "report": lambda: cmd_report(cfg, args),
     "learn": lambda: cmd_learn(cfg, args),
     "live": lambda: cmd_live(cfg, args),
     "resume": lambda: cmd_resume(cfg, args),
     "dashboard": lambda: cmd_dashboard(cfg, args),
     "doctor": lambda: cmd_doctor(cfg, args)}[args.command]()


if __name__ == "__main__":
    main()
