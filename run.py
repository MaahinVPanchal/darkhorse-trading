#!/usr/bin/env python
"""Darkhorse CLI.

  python run.py paper            run paper trading continuously (Ctrl-C to stop)
  python run.py paper --once     one single cycle
  python run.py paper --cycles N run N cycles
  python run.py report           performance summary from the journal
  python run.py learn            walk-forward parameter search -> proposals
  python run.py live             refuses unless config live.enabled is true
"""

import argparse
import json
import os
import sys

import requests

from darkhorse import analyst, dashboard, doctor, guards, learn, loop, market, notify
from darkhorse.journal import Journal
from darkhorse.paper import PaperBroker

TESTNET_URL = "https://api.hyperliquid-testnet.xyz"
MAINNET_URL = "https://api.hyperliquid.xyz"


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
        print("\nStopped. Journal saved in darkhorse.db -- run `python run.py report`.")


def cmd_report(cfg, args):
    journal = Journal()
    stats = journal.trade_stats()
    eq = journal.latest_equity()
    start = cfg["paper"]["start_balance_usd"]
    floor, floor_desc = guards.effective_floor(cfg)
    print("=" * 60)
    print("DARKHORSE PAPER REPORT")
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
    """Rung 3: REAL money. Triple gate: config + ACK + promotion criteria."""
    from darkhorse import promotion
    journal = Journal()
    ok, detail = promotion.report(journal, cfg)
    ack_set = cfg["live"].get("acknowledgement") == "I-ACCEPT-REAL-MONEY-RISK"
    print("LIVE TRADING GATE (real money)")
    print(f"  live.enabled: {cfg['live'].get('enabled')}")
    print(f"  ACK string set: {ack_set}")
    print("  promotion criteria (computed from journal, not editable):")
    print(detail)
    ready = cfg["live"].get("enabled") and ack_set and ok
    if not ready:
        print("\nGATES NOT PASSED -- live trading refused. Paper keeps running.")
        sys.exit(1)
    print("\nAll gates passed. Starting MAINNET trading with REAL money.")
    print("Perps can liquidate the entire account.\n")
    try:
        from darkhorse.mainnet_broker import MainnetBroker
        broker = MainnetBroker(journal, cfg)
    except ImportError:
        print("hyperliquid-python-sdk missing: pip install hyperliquid-python-sdk")
        sys.exit(1)
    except RuntimeError as e:
        print(f"Setup problem: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Could not reach mainnet: {e.__class__.__name__}: {e}")
        sys.exit(1)
    account = broker.equity()
    cfg["paper"]["start_balance_usd"] = max(
        2 * cfg["halt"]["equity_floor_usd"], account)
    print(f"wallet: {broker.address} | account value: ${account:.2f} (REAL)")
    try:
        loop.run(journal, broker, cfg,
                 cycles=(1 if args.once else args.cycles), use_analyst=True)
    except KeyboardInterrupt:
        print("\nStopped. Journal updated -- `python run.py report`.")


def cmd_digest(cfg, args):
    """One Telegram/console summary: equity, trades, criteria verdict."""
    from darkhorse import notify, promotion
    journal = Journal()
    stats = journal.trade_stats()
    eq = journal.latest_equity()
    total = eq["total"] if eq else cfg["paper"]["start_balance_usd"]
    halted = guards.is_halted(journal)
    ok, detail = promotion.report(journal, cfg)
    msg = notify.digest_message(cfg, stats, total, halted)
    print(msg)
    print("  promotion: " + ("ALL PASS" if ok else "not yet"))
    if notify.configured():
        notify.send(msg, silent=True)
        print("  (sent to Telegram)")
    else:
        print("  (Telegram not configured -- setx TELEGRAM_BOT_TOKEN / CHAT_ID)")


def cmd_audit(cfg, args):
    """Secrets scan over git history -- go-public readiness."""
    import re
    import subprocess
    log = subprocess.run(["git", "log", "-p", "--all"], capture_output=True,
                         text=True, errors="ignore").stdout
    tracked = subprocess.run(["git", "ls-files"], capture_output=True,
                             text=True).stdout.split()
    print(f"scanning {len(log):,} chars of git history, {len(tracked)} tracked files")
    patterns = {
        "private key (0x + 64 hex)": "0x[a-fA-F0-9]{64}",
        "AWS access key": "AKIA[0-9A-Z]{16}",
        "inline token/secret": "(?i)(token|secret|api[_-]?key)[:=][A-Za-z0-9_]{20,}",
    }
    clean = True
    for name, pat in patterns.items():
        hits = re.findall(pat, log)
        print(f"  [{'FAIL' if hits else 'OK'}] {name}: {len(hits)} hit(s)")
        clean = clean and not hits
    bad_files = [f for f in tracked if f == ".env" or f.endswith(".db")]
    print(f"  [{'FAIL' if bad_files else 'OK'}] .env / *.db tracked: {bad_files or 'none'}")
    clean = clean and not bad_files
    print("\nsecrets audit:", "CLEAN -- public-ready" if clean
          else "DIRTY -- do NOT go public; rotate any exposed key")
    sys.exit(0 if clean else 1)


def cmd_panic(cfg, args):
    """Kill switch: flatten everything NOW, latch the halt."""
    journal = Journal()
    prices = market.all_mids()
    broker = None
    if cfg.get("testnet", {}).get("enabled") and os.environ.get("DARKHORSE_TESTNET_KEY"):
        try:
            from darkhorse.testnet_broker import TestnetBroker
            broker = TestnetBroker(journal, cfg)
        except Exception as e:
            print(f"testnet broker unavailable ({e.__class__.__name__}) -- "
                  f"REAL positions may need MANUAL closing!")
    if broker is None:
        broker = PaperBroker(journal, cfg)
    closed = []
    for p in journal.all_positions():
        price = prices.get(p["coin"], p["avg_price"])
        try:
            fill = broker.close_position(p["coin"], price, "panic-exit",
                                         "manual kill switch")
        except Exception as e:
            print(f"FAILED to close {p['coin']}: {e} -- close it MANUALLY")
            continue
        if fill:
            closed.append(fill)
    guards.halt(journal, "manual kill switch (panic)")
    notify.send("PANIC: positions closed, halt latched. resume.bat to re-enable.")
    print(f"closed {len(closed)} position(s); halt latched. "
          f"resume.bat to re-enable.")


def cmd_analyst_test(cfg, args):
    journal = Journal()
    print("Firing one real call at the configured analyst provider...\n")
    r = analyst.test_provider(cfg, journal)
    if not r.get("ok"):
        print(f"FAILED: {r.get('error')}")
        sys.exit(1)
    print(f"provider:      {r['provider']}")
    print(f"verdict:       bias={r['bias']} confidence={r['confidence']:.2f}")
    print(f"note:          {r['note']}")
    if r.get("input_tokens"):
        print(f"input tokens:  {r['input_tokens']} (this call counted against today's budget)")
    print(f"budget today:  {r['calls_today']} calls / {r['tokens_today']} input tokens")
    print("\nThe decision layer is connected. Enable it in config.json "
          "(analyst.enabled) and restart run_paper.bat.")


def cmd_testnet(cfg, args):
    """Rung 2: real signed orders, MOCK money on Hyperliquid testnet."""
    t = cfg.get("testnet", {})
    if not t.get("enabled"):
        print("Testnet trading is disabled (config testnet.enabled=false).")
        print("Setup: 1) pip install hyperliquid-python-sdk")
        print("       2) create a TESTNET API wallet at app.hyperliquid-testnet.xyz")
        print('       3) setx DARKHORSE_TESTNET_KEY "..."   (trade-only key)')
        print("       4) set testnet.enabled=true in config.json")
        sys.exit(1)
    from darkhorse.testnet_broker import TestnetBroker, TESTNET_URL, SDK_AVAILABLE
    if not SDK_AVAILABLE:
        print("hyperliquid-python-sdk is not installed: pip install hyperliquid-python-sdk")
        sys.exit(1)
    journal = Journal()
    try:
        broker = TestnetBroker(journal, cfg)  # raises with setup help if key missing
    except RuntimeError as e:
        print(f"Testnet setup problem: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Could not initialize the testnet connection: "
              f"{e.__class__.__name__}: {e}")
        print("If this is an SSL/network error, your network cannot reach "
              "api.hyperliquid-testnet.xyz -- run doctor, or try another "
              "network. Paper mode keeps working meanwhile.")
        sys.exit(1)
    account = broker.equity()
    # scale the floor/loss-limit math to the testnet account (floor stays $5)
    cfg["paper"]["start_balance_usd"] = max(
        2 * cfg["halt"]["equity_floor_usd"], account)
    print(f"TESTNET mode on {TESTNET_URL}")
    print(f"wallet: {broker.address}  |  account value: ${account:.2f} (mock money)")
    print("This places REAL signed orders on testnet. Ctrl-C to stop.\n")
    try:
        loop.run(journal, broker, cfg, cycles=(1 if args.once else args.cycles),
                 use_analyst=True)
    except KeyboardInterrupt:
        print("\nStopped. Journal updated in darkhorse.db -- `python run.py report`.")


def cmd_account(cfg, args):
    """READ-ONLY account lookup. Proves connectivity and shows balances.
    An address can VIEW an account; only its key can TRADE from it."""
    address = args.address
    key = os.environ.get("DARKHORSE_TESTNET_KEY")
    if not address and key:
        try:
            from eth_account import Account
            address = Account.from_key(key).address
            print(f"address resolved from DARKHORSE_TESTNET_KEY: {address}")
        except Exception:
            pass
    if not address:
        print("No address. Usage: python run.py account --address 0x...")
        print("(or set DARKHORSE_TESTNET_KEY and it derives the address)")
        sys.exit(1)

    for label, base in (("TESTNET", TESTNET_URL), ("MAINNET", MAINNET_URL)):
        try:
            r = requests.post(f"{base}/info", json={
                "type": "clearinghouseState", "user": address, "dex": ""},
                timeout=12)
            r.raise_for_status()
            st = r.json()
            s = requests.post(f"{base}/info", json={
                "type": "spotClearinghouseState", "user": address}, timeout=12)
            s.raise_for_status()
            spot = s.json()
        except Exception as e:
            print(f"[{label}] unreachable from this network "
                  f"({e.__class__.__name__})")
            continue
        ms = st.get("marginSummary", {})
        print(f"\n[{label}] read-only view of {address}")
        print(f"  perp account value: ${float(ms.get('accountValue', 0)):.2f}")
        print(f"  withdrawable:       ${float(st.get('withdrawable', 0)):.2f}")
        balances = spot.get("balances", [])
        if balances:
            print("  spot balances:")
            for b in balances:
                if float(b.get("total", 0)) > 0:
                    print(f"    {b.get('coin')}: total {b.get('total')} "
                          f"(hold {b.get('hold')})")
        else:
            print("  spot balances: none")
        pos = st.get("assetPositions", [])
        if pos:
            for p in pos:
                pi = p["position"]
                print(f"  perp position: {pi['coin']} {pi['szi']} "
                      f"@ entry {pi.get('entryPx')}")
        else:
            print("  perp positions: none open")
        if label == "TESTNET":
            print("  -> this is your mock-money test account. testnet.bat "
                  "can trade it once the API key is set.")
        else:
            print("  -> shown via mainnet because testnet is filtered on "
                  "this network; same address, same public API.")
    print("\nSecurity model: an ADDRESS is public -- anyone can read this "
          "view. Trading requires the account KEY, which only you hold "
          "(env var, never chat, never git).")


def cmd_reconcile(cfg, args):
    """NautilusTrader-style reconciliation: journal vs venue, READ-ONLY."""
    address = args.address
    key = os.environ.get("DARKHORSE_TESTNET_KEY")
    if not address and key:
        try:
            from eth_account import Account
            address = Account.from_key(key).address
        except Exception:
            pass
    if not address:
        print("Usage: python run.py reconcile --address 0x...")
        sys.exit(1)
    journal = Journal()
    jpos = {}
    for p in journal.all_positions():
        jpos[p["coin"]] = jpos.get(p["coin"], 0.0) + p["qty"]

    any_venue = False
    for label, base in (("TESTNET", TESTNET_URL), ("MAINNET", MAINNET_URL)):
        try:
            r = requests.post(f"{base}/info", json={
                "type": "clearinghouseState", "user": address, "dex": ""},
                timeout=12)
            r.raise_for_status()
            st = r.json()
        except Exception as e:
            print(f"[{label}] unreachable ({e.__class__.__name__})")
            continue
        any_venue = True
        xpos = {}
        for p in st.get("assetPositions", []):
            pi = p["position"]
            xpos[pi["coin"]] = xpos.get(pi["coin"], 0.0) + float(pi["szi"])
        print(f"\n[{label}] reconciliation for {address}")
        print(f"  account value: ${float(st.get('marginSummary', {}).get('accountValue', 0)):.2f}")
        try:
            fr = requests.post(f"{base}/info", json={
                "type": "userFunding", "user": address}, timeout=12)
            fr.raise_for_status()
            fundings = fr.json()
            net = sum(float(f.get("usdc", 0)) for f in fundings)
            print(f"  funding history: {len(fundings)} events, net {net:+.4f} USDC")
        except Exception:
            pass
        coins = sorted(set(jpos) | set(xpos))
        if not coins:
            print("  no positions on either side -- trivially PASS")
            continue
        ok = True
        for coin in coins:
            j, x = jpos.get(coin, 0.0), xpos.get(coin, 0.0)
            match = abs(j - x) < 1e-9
            ok = ok and match
            tag = "PASS" if match else "MISMATCH"
            print(f"  {coin:<6} journal {j:+.6f} | venue {x:+.6f}  [{tag}]")
        if jpos and not xpos and label == "MAINNET":
            print("  (expected: paper positions never exist on the exchange)")
        print(f"  reconciliation: {'PASS' if ok else 'MISMATCH -- investigate'}")
    if not any_venue:
        print("\nNo venue reachable -- reconciliation impossible right now.")
    print("\nNote: paper-journal positions are simulated by design; use this "
          "command against TESTNET once the API key is connected.")


def cmd_notify_test(cfg, args):
    from darkhorse import notify
    ok, msg = notify.test()
    print(("OK: " if ok else "FAILED: ") + msg)
    sys.exit(0 if ok else 1)


def cmd_binance_testnet(cfg, args):
    """Venue adapter 2: Binance SPOT TESTNET -- real signed orders, mock money."""
    v = cfg.get("venues", {}).get("binance_testnet", {})
    if not v.get("enabled"):
        print("Binance spot-testnet trading is disabled "
              "(config venues.binance_testnet.enabled=false).")
        print("Setup: 1) log in at https://testnet.binance.vision with GitHub")
        print("       2) Generate HMAC keys")
        print('       3) setx BINANCE_API_KEY "..."  setx BINANCE_API_SECRET "..."')
        print("       4) set venues.binance_testnet.enabled=true, then rerun")
        sys.exit(1)
    from darkhorse.binance_broker import BinanceSpotBroker
    journal = Journal()
    try:
        broker = BinanceSpotBroker(journal, cfg)
    except RuntimeError as e:
        print(f"Setup problem: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Could not reach Binance testnet: {e.__class__.__name__}: {e}")
        sys.exit(1)
    account = broker.equity()
    cfg["paper"]["start_balance_usd"] = max(
        2 * cfg["halt"]["equity_floor_usd"], account)
    print("BINANCE SPOT TESTNET (real signed orders, MOCK money)")
    print(f"account value: ${account:.2f} | Ctrl-C to stop.")
    print()
    try:
        loop.run(journal, broker, cfg,
                 cycles=(1 if args.once else args.cycles), use_analyst=True)
    except KeyboardInterrupt:
        print()
        print("Stopped. Journal updated -- `python run.py report`.")


def cmd_dashboard(cfg, args):
    dashboard.serve(cfg, open_browser=not args.no_browser)


def cmd_doctor(cfg, args):
    ok = doctor.run(cfg)
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description="Darkhorse paper trading bot")
    ap.add_argument("command",
                    choices=["paper", "report", "learn", "live", "resume",
                             "dashboard", "doctor", "analyst-test", "testnet",
                             "account", "notify-test", "reconcile",
                             "digest", "audit", "panic", "binance-testnet"])
    ap.add_argument("--address", default=None,
                    help="account: read-only lookup of this 0x address")
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
     "doctor": lambda: cmd_doctor(cfg, args),
     "analyst-test": lambda: cmd_analyst_test(cfg, args),
     "testnet": lambda: cmd_testnet(cfg, args),
     "account": lambda: cmd_account(cfg, args),
     "notify-test": lambda: cmd_notify_test(cfg, args),
     "reconcile": lambda: cmd_reconcile(cfg, args),
     "digest": lambda: cmd_digest(cfg, args),
     "audit": lambda: cmd_audit(cfg, args),
     "panic": lambda: cmd_panic(cfg, args),
     "binance-testnet": lambda: cmd_binance_testnet(cfg, args)}[args.command]()


if __name__ == "__main__":
    main()
