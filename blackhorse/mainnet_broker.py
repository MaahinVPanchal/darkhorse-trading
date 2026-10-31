"""MAINNET adapter: real money, real risk. Triple-gated.

Refuses to initialize unless ALL of:
  1. config live.enabled == true
  2. config live.acknowledgement == "I-ACCEPT-REAL-MONEY-RISK" (exact string)
  3. the pre-registered promotion criteria PASS (computed from the journal,
     not from the log file -- see promotion.py)
  4. HYPERLIQUID_MAINNET_KEY is set, and MUST belong to a trade-only API
     wallet (cannot withdraw). Never your seed phrase.

Even then: start with an amount you are completely fine losing.
"""

import os

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

from .promotion import check as promotion_check
from .testnet_broker import TestnetBroker
from .utils_urls import MAINNET_URL


class MainnetBroker(TestnetBroker):
    """Identical mechanics to the testnet adapter -- only the venue URL,
    the key, and the gates differ."""

    def __init__(self, journal, cfg):
        live = cfg.get("live", {})
        if not live.get("enabled"):
            raise RuntimeError("live.enabled is false in config.json")
        if live.get("acknowledgement") != "I-ACCEPT-REAL-MONEY-RISK":
            raise RuntimeError('live.acknowledgement must be exactly '
                               '"I-ACCEPT-REAL-MONEY-RISK"')
        ok, checks = promotion_check(journal, cfg)
        if not ok:
            failed = "; ".join(n for n, passed, _ in checks if not passed)
            raise RuntimeError(
                "promotion criteria NOT met -- live trading locked: " + failed)
        key = os.environ.get("HYPERLIQUID_MAINNET_KEY", "")
        if not key:
            raise RuntimeError("HYPERLIQUID_MAINNET_KEY not set. It must be a "
                               "TRADE-ONLY mainnet API wallet key (cannot "
                               "withdraw) -- never your seed phrase.")
        self.j = journal
        self.cfg = cfg
        self.wallet = Account.from_key(key)
        self.address = self.wallet.address
        self.info = Info(MAINNET_URL, skip_ws=True)
        self.exchange = Exchange(self.wallet, MAINNET_URL)
        meta = self.info.meta()
        self.sz_decimals = {u["name"]: u["szDecimals"] for u in meta["universe"]}
        self.slippage = cfg.get("live", {}).get("slippage", 0.03)
        self.url = MAINNET_URL
