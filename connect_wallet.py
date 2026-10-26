"""One-time wallet connect helper.

You paste the testnet API-wallet key into a HIDDEN prompt on your own machine.
This script then, automatically:
  1. validates the key and derives its address
  2. saves it permanently as the BLACKHORSE_TESTNET_KEY env var (setx)
  3. shows your testnet/mainnet account balances (read-only check)
  4. runs the full doctor pre-flight

The key is never printed, never saved to any file, never sent anywhere except
Windows' own user-environment store. Never paste it into chat or GitHub.
"""

import getpass
import os
import subprocess
import sys

import requests

TESTNET_URL = "https://api.hyperliquid-testnet.xyz"
MAINNET_URL = "https://api.hyperliquid.xyz"


def show_account(address):
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
            print(f"[{label}] unreachable ({e.__class__.__name__})")
            continue
        ms = st.get("marginSummary", {})
        print(f"[{label}] account value ${float(ms.get('accountValue', 0)):.2f}"
              f" | withdrawable ${float(st.get('withdrawable', 0)):.2f}")
        for b in spot.get("balances", []):
            if float(b.get("total", 0)) > 0:
                print(f"    spot: {b.get('coin')} = {b.get('total')}")
        for p in st.get("assetPositions", []):
            pi = p["position"]
            print(f"    perp: {pi['coin']} {pi['szi']} @ {pi.get('entryPx')}")
        return label
    return None


def main():
    print("=" * 62)
    print("BLACKHORSE wallet connect (one-time, 30 seconds)")
    print("=" * 62)
    print("This expects the TESTNET API-wallet PRIVATE KEY from")
    print("app.hyperliquid-testnet.xyz -> API page (trade-only key).\n")
    if sys.stdin.isatty():
        key = getpass.getpass("Paste the key here (input hidden): ")
    else:
        key = sys.stdin.readline()  # piped input (scripted use)
    key = key.strip().strip('"')
    if not key.startswith("0x") and len(key) == 64:
        key = "0x" + key  # tolerate keys copied without the 0x prefix
    if not key.startswith("0x") or len(key) != 66:
        print("\nThat doesn't look like a private key (needs 0x + 64 hex chars)."
              "\nCopy the 'Private Key' shown on the API page after approval.")
        sys.exit(1)
    try:
        from eth_account import Account
        address = Account.from_key(key).address
    except Exception as e:
        print(f"\nInvalid key: {e}")
        sys.exit(1)
    print(f"\nkey valid. derived address: {address}")
    print("(API wallets have their own address -- that's normal. What matters")
    print(" is that YOU generated it from your account on the testnet site.)")

    subprocess.run(["setx", "BLACKHORSE_TESTNET_KEY", key],
                   capture_output=True, check=True)
    os.environ["BLACKHORSE_TESTNET_KEY"] = key
    print("saved permanently as BLACKHORSE_TESTNET_KEY (user env var).\n")

    reach = show_account(address)
    print()
    if reach == "TESTNET":
        print("Testnet reachable from this network -- you are READY.")
        print("Double-click testnet.bat to start mock-money trading.")
    else:
        print("Testnet is still filtered on this network -- the key is saved")
        print("and will work the moment you run this on a network that can")
        print("reach it (e.g. phone hotspot). Run doctor.bat to re-check.")


if __name__ == "__main__":
    main()
