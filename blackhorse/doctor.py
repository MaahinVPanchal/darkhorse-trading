"""Pre-flight check: python, network, config sanity, journal, keys, ports.
Run `python run.py doctor` (or doctor.bat) before trusting anything.
"""

import json
import os
import socket
import sqlite3
import sys
import time

from . import analyst, guards

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    mark = "OK  " if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def run(cfg):
    print("Blackhorse doctor -- pre-flight checks\n")

    v = sys.version_info
    check("python >= 3.10", v >= (3, 10), f"{v.major}.{v.minor}.{v.micro}")

    t0 = time.time()
    try:
        from . import market
        mids = market.all_mids()
        check("Hyperliquid API reachable", True,
              f"{len(mids)} symbols in {time.time() - t0:.2f}s")
        bad = [s for s in cfg["symbols"] if s not in mids]
        check("configured symbols exist on Hyperliquid", not bad,
              f"missing: {bad}" if bad else ", ".join(cfg["symbols"]))
    except Exception as e:
        check("Hyperliquid API reachable", False, str(e))

    try:
        floor, desc = guards.effective_floor(cfg)
        check("equity floor sane",
              floor < cfg["paper"]["start_balance_usd"],
              f"floor ${floor:.2f} ({desc}), start "
              f"${cfg['paper']['start_balance_usd']}")
    except Exception as e:
        check("equity floor sane", False, str(e))

    check("take-profit above stop-loss",
          cfg["exits"]["take_profit_pct"] > 0 and cfg["exits"]["stop_loss_pct"] > 0,
          f"TP {cfg['exits']['take_profit_pct']}% / SL {cfg['exits']['stop_loss_pct']}%")
    check("daily loss limit set",
          0 < cfg["risk"]["daily_loss_limit_pct"] <= 100,
          f"{cfg['risk']['daily_loss_limit_pct']}%")

    try:
        from .journal import Journal
        j = Journal()
        counts = {t: j.conn.execute(
            f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
            for t in ("fills", "decisions", "equity")}
        j.conn.close()
        check("journal database opens", True,
              ", ".join(f"{k}={v}" for k, v in counts.items()))
    except sqlite3.Error as e:
        check("journal database opens", False, str(e))

    provider = analyst.available(cfg)
    if cfg["analyst"].get("enabled"):
        from .analyst import ALL_KEY_ENVS
        keys_found = [k for k in ALL_KEY_ENVS if os.environ.get(k)]
        check("analyst enabled and provider resolves", provider is not None,
              f"provider={provider}, keys={keys_found or 'NONE -- set one'}")
    else:
        check("analyst layer", True, "disabled (rules-only mode) by config")

    port = cfg.get("dashboard", {}).get("port", 8765)
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        check("dashboard port free", True, f"127.0.0.1:{port}")
    except OSError as e:
        check("dashboard port free", False, f"port {port} in use? {e}")
    finally:
        s.close()

    check("live trading locked off", not cfg["live"].get("enabled"),
          "live.enabled=false -- deliberate until paper results justify it")

    t = cfg.get("testnet", {})
    if not t.get("enabled"):
        check("testnet adapter", True, "disabled (paper mode is the trainer)")
    else:
        import requests as _rq
        try:
            from hyperliquid.exchange import Exchange  # noqa: F401
            sdk = "sdk installed"
        except ImportError:
            sdk = "SDK MISSING: pip install hyperliquid-python-sdk"
        key = os.environ.get("BLACKHORSE_TESTNET_KEY")
        t0 = time.time()
        try:
            r = _rq.post("https://api.hyperliquid-testnet.xyz/info",
                         json={"type": "allMids"}, timeout=10)
            net = f"reachable in {time.time() - t0:.2f}s"
            ok_net = r.status_code == 200
        except Exception as e:
            net, ok_net = f"UNREACHABLE from this network ({e.__class__.__name__})", False
        check("testnet network", ok_net, net)
        check("testnet sdk + key", bool(sdk.startswith("sdk") and key),
              f"{sdk}; key={'set' if key else 'MISSING (setx BLACKHORSE_TESTNET_KEY)'}")

    fails = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"\n{len(RESULTS) - fails}/{len(RESULTS)} checks passed."
          + ("" if not fails else f"  FIX THE {fails} FAILURES ABOVE."))
    return fails == 0
