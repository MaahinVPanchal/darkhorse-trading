"""Patch 7: binance-testnet command + venues config. No escape sequences."""
import ast
import json

p = "run.py"
src = open(p, encoding="utf-8").read()

def rep(old, new):
    global src
    assert old in src, "NOT FOUND: " + old[:70]
    src = src.replace(old, new, 1)

rep('''def cmd_dashboard(cfg, args):''',
    '''def cmd_binance_testnet(cfg, args):
    """Venue adapter 2: Binance SPOT TESTNET -- real signed orders, mock money."""
    v = cfg.get("venues", {}).get("binance_testnet", {})
    if not v.get("enabled"):
        print("Binance spot-testnet trading is disabled "
              "(config venues.binance_testnet.enabled=false).")
        print("Setup: 1) log in at https://testnet.binance.vision with GitHub")
        print("       2) Generate HMAC keys")
        print('       3) setx BINANCE_API_KEY "..."  '
              'setx BINANCE_API_SECRET "..."')
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
        print("\\nStopped. Journal updated -- `python run.py report`.")


def cmd_dashboard(cfg, args):''')

rep('''                             "digest", "audit", "panic"])''',
    '''                             "digest", "audit", "panic", "binance-testnet"])''')
rep('''     "panic": lambda: cmd_panic(cfg, args)}[args.command]()''',
    '''     "panic": lambda: cmd_panic(cfg, args),
     "binance-testnet": lambda: cmd_binance_testnet(cfg, args)}[args.command]()''')

open(p, "w", encoding="utf-8", newline="").write(src)
ast.parse(open(p, encoding="utf-8").read())
print("run.py patched and parses")

cfg = json.load(open("config.json", encoding="utf-8"))
cfg["venues"] = {
    "hyperliquid_testnet": {"enabled": False,
                            "env": ["BLACKHORSE_TESTNET_KEY"],
                            "command": "run.py testnet"},
    "binance_testnet": {"enabled": False,
                        "env": ["BINANCE_API_KEY", "BINANCE_API_SECRET"],
                        "command": "run.py binance-testnet"},
    "mainnet": {"enabled": False,
                "env": ["HYPERLIQUID_MAINNET_KEY"],
                "command": "run.py live",
                "gate": "promotion criteria + ACK (code-enforced)"},
    "note": "Pluggable venue adapters. All share the same loop, guards, "
            "analyst veto and journal. See VENUES.md for the full platform "
            "map (Schwab/public.com/Groww/Robinhood research)."
}
json.dump(cfg, open("config.json", "w", encoding="utf-8"), indent=2)
print("config.json venues added")
