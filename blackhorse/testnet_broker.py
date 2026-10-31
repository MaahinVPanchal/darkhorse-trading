"""Testnet execution adapter: REAL orders, MOCK money (Hyperliquid testnet).

This is rung 2 of the ladder (paper -> testnet -> tiny mainnet). It practices
the mechanics paper mode can't: signed orders, rate limits, real matching.

Requirements (all enforced at startup):
  1. pip install hyperliquid-python-sdk
  2. a TESTNET API wallet key in the environment: BLACKHORSE_TESTNET_KEY
     (create at app.hyperliquid-testnet.xyz -> API; trade-only, no withdrawals)
  3. config.json testnet.enabled = true

Never put a mainnet key in BLACKHORSE_TESTNET_KEY. If testnet is unreachable
from your network (doctor will tell you), stay in paper mode -- the strategy
logic is identical.
"""

import os

try:
    from eth_account import Account
    from hyperliquid.exchange import Exchange
    from hyperliquid.info import Info
    from hyperliquid.utils import constants
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

TESTNET_URL = constants.TESTNET_API_URL  # https://api.hyperliquid-testnet.xyz


class TestnetBroker:
    """Same interface as PaperBroker, but orders are signed and real
    (on testnet). Account equity comes from the exchange, not simulation."""

    def __init__(self, journal, cfg):
        if not SDK_AVAILABLE:
            raise RuntimeError("hyperliquid-python-sdk not installed: "
                               "pip install hyperliquid-python-sdk")
        key = os.environ.get("BLACKHORSE_TESTNET_KEY", "")
        if not key:
            raise RuntimeError("BLACKHORSE_TESTNET_KEY not set. Create a "
                               "TESTNET API wallet at app.hyperliquid-testnet.xyz "
                               "(API page), copy its key, then: "
                               "setx BLACKHORSE_TESTNET_KEY \"...\"")
        self.j = journal
        self.cfg = cfg
        self.wallet = Account.from_key(key)
        self.address = self.wallet.address
        self.info = Info(TESTNET_URL, skip_ws=True)
        self.exchange = Exchange(self.wallet, TESTNET_URL)
        meta = self.info.meta()
        self.sz_decimals = {u["name"]: u["szDecimals"] for u in meta["universe"]}
        self.slippage = cfg.get("testnet", {}).get("slippage", 0.05)
        self.url = TESTNET_URL

    # -- account -----------------------------------------------------------
    def _user_state(self):
        return self.info.user_state(self.address)

    def equity(self, prices=None):
        return float(self._user_state()["marginSummary"]["accountValue"])

    def cash(self):
        return float(self._user_state()["withdrawable"])

    def unrealized(self, prices=None):
        return self.equity(prices) - self.cash()

    # -- orders ------------------------------------------------------------
    def _round_sz(self, coin, sz):
        dec = self.sz_decimals.get(coin)
        return round(sz, dec) if dec is not None else sz

    def _parse_fill(self, resp, coin, side, kind, reason):
        """Pull the fill out of an order response; raise on exchange errors."""
        if resp.get("status") == "err":
            raise RuntimeError(f"exchange rejected order: {resp.get('response')}")
        statuses = resp.get("response", {}).get(
            "data", {}).get("statuses", [])
        for st in statuses:
            if "error" in st:
                raise RuntimeError(f"order error: {st['error']}")
            if "filled" in st:
                f = st["filled"]
                return float(f["avgPx"]), float(f["totalSz"])
            if "resting" in st or "waitingTrigger" in st:
                return None, None  # not filled now; reconciliation catches it
        raise RuntimeError(f"unexpected order response: {resp}")

    def open_position(self, coin, price, notional, reason, analyst_note=None):
        sz = self._round_sz(coin, notional / price)
        self.j.record_event(coin, "order_submitted",
                            f"market_open buy {sz} {coin} ({reason})")
        resp = self.exchange.market_open(coin, True, sz, None, self.slippage)
        try:
            fill_px, fill_sz = self._parse_fill(resp, coin, "buy",
                                                "testnet-entry", reason)
        except RuntimeError:
            self.j.record_event(coin, "order_rejected", str(resp)[:200])
            raise
        if fill_px is None:
            self.j.record_event(coin, "order_unfilled", str(resp)[:200])
            raise RuntimeError(f"{coin} entry did not fill: {resp}")
        self.j.record_event(coin, "order_filled",
                            f"entry {fill_sz} {coin} @ {fill_px}")
        exits = self.cfg["exits"]
        stop = fill_px * (1 - exits["stop_loss_pct"] / 100)
        target = fill_px * (1 + exits["take_profit_pct"] / 100)
        self.j.open_position(coin, fill_sz, fill_px, stop, target, reason)
        self.j.record_fill(coin, "buy", fill_sz, fill_px, fill_sz * fill_px,
                           0.0, None, "testnet-entry", reason)
        return {"coin": coin, "action": "TESTNET-ENTRY", "qty": fill_sz,
                "price": fill_px, "fee": 0.0, "reason": reason,
                "stop": stop, "target": target, "analyst_note": analyst_note}

    def close_position(self, coin, price, kind, reason=None):
        pos = self.j.get_position(coin)
        if not pos:
            return None
        resp = self.exchange.market_close(coin, None, None, self.slippage)
        fill_px, fill_sz = self._parse_fill(resp, coin, "sell", kind, reason)
        if fill_px is None:
            raise RuntimeError(f"{coin} exit did not fill: {resp}")
        pnl = fill_sz * (fill_px - pos["avg_price"])
        self.j.record_fill(coin, "sell", fill_sz, fill_px, fill_sz * fill_px,
                           0.0, pnl, kind, reason)
        self.j.close_position(coin)
        return {"coin": coin, "action": kind.upper(), "qty": fill_sz,
                "price": fill_px, "fee": 0.0, "pnl": pnl, "reason": reason}

    def check_exit(self, coin, price):
        pos = self.j.get_position(coin)
        if not pos:
            return None
        if price <= pos["stop"]:
            return self.close_position(coin, price, "stop-loss",
                                       f"price {price:.2f} <= stop {pos['stop']:.2f}")
        if price >= pos["target"]:
            return self.close_position(coin, price, "take-profit",
                                       f"price {price:.2f} >= target {pos['target']:.2f}")
        return None
