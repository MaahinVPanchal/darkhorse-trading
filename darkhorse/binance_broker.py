"""Binance SPOT TESTNET adapter: real signed orders, mock money.

The second venue adapter (after Hyperliquid testnet) -- same interface as
PaperBroker/TestnetBroker, so the whole loop, guards, analyst and journal
work unchanged. Uses stdlib HMAC-SHA256 signing; no new dependencies.

Setup (the same 3-step pattern as every venue):
  1. log in at https://testnet.binance.vision with a GitHub account
     (free mock USDT/BNB faucet included)
  2. generate an HMAC API key + secret
  3. setx BINANCE_API_KEY "..."  and  setx BINANCE_API_SECRET "..."
     then config venues.binance_testnet.enabled = true -> run.py binance-testnet

Never put production Binance keys here.
"""

import hashlib
import hmac
import os
import time
import urllib.parse

import requests

from .utils_urls import BINANCE_TESTNET_URL


class BinanceSpotBroker:
    """Spot testnet broker: market buys/sells on *USDT pairs, positions and
    TP/SL tracked in the journal (same in-loop exits as paper mode)."""

    def __init__(self, journal, cfg):
        self.key = os.environ.get("BINANCE_API_KEY", "")
        self.sec = os.environ.get("BINANCE_API_SECRET", "")
        if not self.key or not self.sec:
            raise RuntimeError(
                "BINANCE_API_KEY / BINANCE_API_SECRET not set. Create them at "
                "https://testnet.binance.vision (log in with GitHub -> Generate "
                "HMAC keys), then setx both and open a NEW terminal.")
        self.j = journal
        self.cfg = cfg
        self.base = BINANCE_TESTNET_URL + "/api"
        info = requests.get(self.base + "/v3/exchangeInfo", timeout=20).json()
        self.filters = {s["symbol"]: s["filters"] for s in info["symbols"]}
        self.slip_bps = cfg["fees"]["slippage_bps"]

    # -- signing -----------------------------------------------------------
    def _signed(self, method, path, params):
        params = dict(params)
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 10000
        qs = urllib.parse.urlencode(params)
        sig = hmac.new(self.sec.encode(), qs.encode(), hashlib.sha256).hexdigest()
        r = requests.request(
            method, f"{self.base}{path}?{qs}&signature={sig}",
            headers={"X-MBX-APIKEY": self.key}, timeout=20)
        r.raise_for_status()
        return r.json()

    def _round_sz(self, symbol, qty):
        for f in self.filters.get(symbol, []):
            if f.get("filterType") == "LOT_SIZE":
                step = float(f["stepSize"])
                return int(qty / step) * step
        return qty

    # -- account -----------------------------------------------------------
    def _balances(self):
        acct = self._signed("GET", "/v3/account", {})
        return {b["asset"]: float(b["free"]) + float(b["locked"])
                for b in acct["balances"] if float(b["free"]) + float(b["locked"]) > 0}

    def equity(self, prices=None):
        """USDT cash + market value of coin balances."""
        prices = prices or {}
        total = 0.0
        for asset, amt in self._balances().items():
            if asset == "USDT":
                total += amt
            else:
                total += amt * prices.get(asset, 0.0)
        return total

    def cash(self):
        return self._balances().get("USDT", 0.0)

    def unrealized(self, prices=None):
        return self.equity(prices) - self.cash()

    # -- orders ------------------------------------------------------------
    def _market(self, symbol, side, params, kind, reason):
        resp = self._signed("POST", "/v3/order",
                            {"symbol": symbol, "side": side,
                             "type": "MARKET", **params})
        if resp.get("status") not in ("FILLED", "PARTIALLY_FILLED", "NEW"):
            self.j.record_event(symbol, "order_rejected", str(resp)[:200])
            raise RuntimeError(f"{symbol} {side} not filled: {resp}")
        qty = float(resp.get("executedQty", 0) or 0)
        quote = float(resp.get("cummulativeQuoteQty", 0) or 0)
        if qty <= 0 or quote <= 0:
            self.j.record_event(symbol, "order_unfilled", str(resp)[:200])
            raise RuntimeError(f"{symbol} {side} did not fill: {resp}")
        px = quote / qty
        self.j.record_event(symbol, "order_filled",
                            f"{side} {qty} {symbol} @ {px:.4f}")
        return qty, px

    def open_position(self, coin, price, notional, reason, analyst_note=None):
        symbol = f"{coin}USDT"
        qty = self._round_sz(symbol, notional / price)
        if qty <= 0:
            raise RuntimeError(f"{symbol}: notional ${notional:.2f} rounds to 0 size")
        qty, fill_px = self._market(symbol, "BUY", {"quoteOrderQty": notional},
                                    "entry", reason)
        exits = self.cfg["exits"]
        stop = fill_px * (1 - exits["stop_loss_pct"] / 100)
        target = fill_px * (1 + exits["take_profit_pct"] / 100)
        self.j.open_position(coin, qty, fill_px, stop, target, reason)
        self.j.record_fill(coin, "buy", qty, fill_px, qty * fill_px, 0.0,
                           None, "testnet-entry", reason)
        return {"coin": coin, "action": "BINANCE-ENTRY", "qty": qty,
                "price": fill_px, "fee": 0.0, "reason": reason,
                "stop": stop, "target": target, "analyst_note": analyst_note}

    def close_position(self, coin, price, kind, reason=None):
        pos = self.j.get_position(coin)
        if not pos:
            return None
        symbol = f"{coin}USDT"
        qty = self._round_sz(symbol, pos["qty"])
        qty, fill_px = self._market(symbol, "SELL", {"quantity": qty},
                                    kind, reason)
        pnl = qty * (fill_px - pos["avg_price"])
        self.j.record_fill(coin, "sell", qty, fill_px, qty * fill_px, 0.0,
                           pnl, kind, reason)
        self.j.close_position(coin)
        return {"coin": coin, "action": kind.upper(), "qty": qty,
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
