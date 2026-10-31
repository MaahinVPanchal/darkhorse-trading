"""Darkhorse 3-step setup wizard.

  Step 1: pick a venue
  Step 2: paste its keys (hidden input) -> saved to Windows env vars -> verified
  Step 3: done -- the wizard enables the venue in config.json and prints the
          one command that starts trading.

Keys are never printed, never written to files, never sent anywhere except
Windows' own user-environment store.
"""

import getpass
import json
import os
import sys

import requests

TESTNET_URL = "https://api.hyperliquid-testnet.xyz"
BINANCE_TESTNET_URL = "https://testnet.binance.vision"


def _input_key(prompt):
    if sys.stdin.isatty():
        return getpass.getpass(prompt).strip().strip('"')
    return sys.stdin.readline().strip().strip('"')


def _setx(name, value):
    import subprocess
    subprocess.run(["setx", name, value], capture_output=True, check=True)
    os.environ[name] = value


def _cfg_enable_venue(key):
    cfg = json.load(open("config.json", encoding="utf-8"))
    cfg.setdefault("venues", {}).setdefault(key, {})["enabled"] = True
    json.dump(cfg, open("config.json", "w", encoding="utf-8"), indent=2)
    print(f"  config.json: venues.{key}.enabled = true")


def step_hyperliquid():
    print("Hyperliquid TESTNET (MetaMask):")
    print("  1. app.hyperliquid-testnet.xyz -> Connect Wallet")
    print("  2. API page -> Approve API Wallet -> sign in MetaMask (free)")
    print("  3. copy the API wallet's Private Key")
    key = _input_key("Paste the private key (hidden): ")
    if not key.startswith("0x") or len(key) != 66:
        if len(key) == 64:
            key = "0x" + key
        else:
            print("  that is not a private key (need 0x + 64 hex)")
            return False
    _setx("BLACKHORSE_TESTNET_KEY", key)
    print("  saved as BLACKHORSE_TESTNET_KEY")
    try:
        from eth_account import Account
        print(f"  derived address: {Account.from_key(key).address}")
    except Exception:
        pass
    _cfg_enable_venue("hyperliquid_testnet")
    return True


def step_binance():
    print("Binance SPOT TESTNET (GitHub login, free mock USDT):")
    print("  1. log in at https://testnet.binance.vision with GitHub")
    print("  2. Generate HMAC keys")
    key = _input_key("Paste the API key (hidden): ")
    sec = _input_key("Paste the API secret (hidden): ")
    if not key or not sec:
        print("  empty key/secret -- aborted")
        return False
    _setx("BINANCE_API_KEY", key)
    _setx("BINANCE_API_SECRET", sec)
    print("  saved as BINANCE_API_KEY / BINANCE_API_SECRET")
    try:
        qs = urllib.parse.urlencode({"timestamp": int(time.time() * 1000),
                                     "recvWindow": 10000})
        import hashlib
        import hmac
        sig = hmac.new(sec.encode(), qs.encode(), hashlib.sha256).hexdigest()
        r = requests.get(
            f"{BINANCE_TESTNET_URL}/api/v3/account?{qs}&signature={sig}",
            headers={"X-MBX-APIKEY": key}, timeout=15)
        r.raise_for_status()
        bal = {b["asset"]: b["free"] for b in r.json()["balances"]
               if float(b["free"]) > 0}
        print(f"  verified -- balances: {bal or '(empty, use the faucet)'}")
    except Exception as e:
        print(f"  verification failed: {e.__class__.__name__}: {e}")
        return False
    _cfg_enable_venue("binance_testnet")
    return True


def step_optional_ai():
    print("\nOptional -- AI decision layer (any one key; enter to skip):")
    print("  1 = Jev ($5 credit)  2 = OpenAI  3 = Nebius  enter = skip")
    choice = input("  choice: ").strip()
    env = {"1": "TYPESAFE_API_KEY", "2": "OPENAI_API_KEY",
           "3": "NEBIUS_API_KEY"}.get(choice)
    if not env:
        return
    key = _input_key(f"  paste {env} value (hidden): ")
    if key:
        _setx(env, key)
        print(f"  saved {env} -- test later with analyst_test.bat")


def main():
    print("=" * 62)
    print("DARKHORSE 3-STEP SETUP")
    print("=" * 62)
    print("Step 1 -- pick a venue:\n"
          "  1) Hyperliquid testnet (MetaMask, perps)\n"
          "  2) Binance spot testnet (GitHub login, mock USDT)\n"
          "  3) skip keys -- paper-only mode\n")
    choice = input("venue choice: ").strip()
    ok = True
    if choice == "1":
        ok = step_hyperliquid()
    elif choice == "2":
        ok = step_binance()
    else:
        print("Paper-only mode chosen -- no keys needed. "
              "Run start_darkhorse.bat.")
    if ok:
        step_optional_ai()
    print("\nStep 3 -- start: double-click start_darkhorse.bat "
          "(paper + dashboard), or run the venue command shown above.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\naborted")
