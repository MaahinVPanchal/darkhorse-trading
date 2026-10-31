"""Paper broker: fills simulated against LIVE prices with fee + slippage.

Cash is fully derived from the journal (start balance + realized pnl - open
costs), so the account state survives restarts and can always be recomputed.
"""

from .journal import today_utc


class PaperBroker:
    def __init__(self, journal, cfg):
        self.j = journal
        self.cfg = cfg
        self.start_balance = cfg["paper"]["start_balance_usd"]
        self.taker_bps = cfg["fees"]["taker_bps"]
        self.slip_bps = cfg["fees"]["slippage_bps"]

    # -- account -----------------------------------------------------------
    def cash(self):
        return (self.start_balance
                + self.j.realized_pnl()
                - self.j.open_cost()
                - self.j.entry_fees_paid())

    def unrealized(self, prices):
        total = 0.0
        for pos in self.j.all_positions():
            price = prices.get(pos["coin"], pos["avg_price"])
            total += pos["qty"] * (price - pos["avg_price"])
        return total

    def equity(self, prices):
        total = self.cash()
        for pos in self.j.all_positions():
            total += pos["qty"] * prices.get(pos["coin"], pos["avg_price"])
        return total

    # -- order simulation --------------------------------------------------
    def open_position(self, coin, price, notional, reason, analyst_note=None):
        """Buy `notional` USD worth. Returns the fill description dict."""
        fill_price = price * (1 + self.slip_bps / 1e4)  # buy slips up
        fee = notional * self.taker_bps / 1e4
        qty = notional / fill_price
        exits = self.cfg["exits"]
        stop = fill_price * (1 - exits["stop_loss_pct"] / 100)
        target = fill_price * (1 + exits["take_profit_pct"] / 100)
        self.j.open_position(coin, qty, fill_price, stop, target, reason)
        self.j.record_fill(coin, "buy", qty, fill_price, notional, fee,
                           None, "entry", reason)
        return {"coin": coin, "action": "ENTRY", "qty": qty,
                "price": fill_price, "fee": fee, "reason": reason,
                "stop": stop, "target": target, "analyst_note": analyst_note}

    def close_position(self, coin, price, kind, reason=None):
        """Sell the whole position at `price`. Returns fill dict, or None."""
        pos = self.j.get_position(coin)
        if not pos:
            return None
        fill_price = price * (1 - self.slip_bps / 1e4)  # sell slips down
        notional = pos["qty"] * fill_price
        fee = notional * self.taker_bps / 1e4
        pnl = notional - pos["qty"] * pos["avg_price"] - fee
        self.j.record_fill(coin, "sell", pos["qty"], fill_price, notional,
                           fee, pnl, kind, reason)
        self.j.close_position(coin)
        return {"coin": coin, "action": kind.upper(), "qty": pos["qty"],
                "price": fill_price, "fee": fee, "pnl": pnl, "reason": reason}

    def check_exit(self, coin, price):
        """TP/SL check against live price. Runs BEFORE any new signals."""
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
