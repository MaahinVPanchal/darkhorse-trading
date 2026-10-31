"""SQLite journal: every decision, fill and equity mark is recorded, so any
result can be audited later. "Make the decisions inspectable before making the
profit screenshot impressive."
"""

import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    coin TEXT NOT NULL,
    side TEXT NOT NULL,          -- 'buy' | 'sell'
    qty REAL NOT NULL,
    price REAL NOT NULL,
    notional REAL NOT NULL,
    fee REAL NOT NULL,
    pnl REAL,                    -- realized pnl on sells only
    kind TEXT NOT NULL,          -- 'entry' | 'take-profit' | 'stop-loss' | 'signal-exit'
    reason TEXT
);
CREATE TABLE IF NOT EXISTS positions (
    coin TEXT PRIMARY KEY,
    qty REAL NOT NULL,
    avg_price REAL NOT NULL,
    stop REAL NOT NULL,
    target REAL NOT NULL,
    opened_ts TEXT NOT NULL,
    entry_reason TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    coin TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT,
    price REAL,
    analyst_note TEXT
);
CREATE TABLE IF NOT EXISTS equity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    cash REAL NOT NULL,
    unrealized REAL NOT NULL,
    total REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    coin TEXT,
    event TEXT NOT NULL,
    detail TEXT
);
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class Journal:
    def __init__(self, path="darkhorse.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # -- fills -------------------------------------------------------------
    def record_fill(self, coin, side, qty, price, notional, fee, pnl, kind, reason):
        self.conn.execute(
            "INSERT INTO fills (ts, coin, side, qty, price, notional, fee, pnl, kind, reason) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (now_iso(), coin, side, qty, price, notional, fee, pnl, kind, reason))
        self.conn.commit()

    # -- positions ---------------------------------------------------------
    def get_position(self, coin):
        row = self.conn.execute(
            "SELECT * FROM positions WHERE coin=?", (coin,)).fetchone()
        return dict(row) if row else None

    def open_position(self, coin, qty, avg_price, stop, target, entry_reason):
        self.conn.execute(
            "INSERT OR REPLACE INTO positions (coin, qty, avg_price, stop, target, opened_ts, entry_reason) "
            "VALUES (?,?,?,?,?,?,?)",
            (coin, qty, avg_price, stop, target, now_iso(), entry_reason))
        self.conn.commit()

    def close_position(self, coin):
        self.conn.execute("DELETE FROM positions WHERE coin=?", (coin,))
        self.conn.commit()

    def all_positions(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM positions")]

    # -- decisions ---------------------------------------------------------
    def record_decision(self, coin, action, reason, price, analyst_note=None):
        self.conn.execute(
            "INSERT INTO decisions (ts, coin, action, reason, price, analyst_note) "
            "VALUES (?,?,?,?,?,?)",
            (now_iso(), coin, action, reason, price, analyst_note))
        self.conn.commit()

    # -- equity ------------------------------------------------------------
    def record_equity(self, cash, unrealized, total):
        self.conn.execute(
            "INSERT INTO equity (ts, cash, unrealized, total) VALUES (?,?,?,?)",
            (now_iso(), cash, unrealized, total))
        self.conn.commit()

    def latest_equity(self):
        row = self.conn.execute(
            "SELECT * FROM equity ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def equity_history(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM equity ORDER BY id ASC")]

    # -- order-state events (Nautilus-style: submitted/filled/rejected) ----
    def record_event(self, coin, event, detail=""):
        self.conn.execute(
            "INSERT INTO events (ts, coin, event, detail) VALUES (?,?,?,?)",
            (now_iso(), coin, event, detail))
        self.conn.commit()

    def events(self, limit=20):
        rows = self.conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # -- key/value state (halts, spend counters) ---------------------------
    def get_state(self, key, default=None):
        row = self.conn.execute(
            "SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_state(self, key, value):
        self.conn.execute(
            "INSERT OR REPLACE INTO state (key, value) VALUES (?,?)",
            (key, str(value)))
        self.conn.commit()

    # -- risk queries ------------------------------------------------------
    def trades_today(self, day=None):
        day = day or today_utc()
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM fills WHERE side='buy' AND substr(ts,1,10)=?",
            (day,)).fetchone()
        return row["n"]

    def last_stop_loss_ts(self, coin):
        row = self.conn.execute(
            "SELECT ts FROM fills WHERE coin=? AND kind='stop-loss' "
            "ORDER BY id DESC LIMIT 1", (coin,)).fetchone()
        return row["ts"] if row else None

    def realized_pnl(self):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(pnl),0) AS p FROM fills WHERE side='sell'").fetchone()
        return row["p"]

    def total_fees(self):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(fee),0) AS f FROM fills").fetchone()
        return row["f"]

    def traded_notional(self):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(notional),0) AS n FROM fills").fetchone()
        return row["n"]

    def open_cost(self):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(qty*avg_price),0) AS c FROM positions").fetchone()
        return row["c"]

    def entry_fees_paid(self):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(fee),0) AS f FROM fills WHERE side='buy'").fetchone()
        return row["f"]

    # -- reporting ---------------------------------------------------------
    def fills(self, limit=20):
        rows = self.conn.execute(
            "SELECT * FROM fills ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def trade_stats(self):
        rows = self.conn.execute(
            "SELECT coin, pnl FROM fills WHERE side='sell' AND pnl IS NOT NULL").fetchall()
        trades = [(r["coin"], r["pnl"]) for r in rows]
        n = len(trades)
        wins = sum(1 for _, p in trades if p > 0)
        total = sum(p for _, p in trades)
        gross_win = sum(p for _, p in trades if p > 0)
        gross_loss = -sum(p for _, p in trades if p < 0)
        by_coin = {}
        for coin, p in trades:
            c = by_coin.setdefault(coin, {"n": 0, "wins": 0, "pnl": 0.0})
            c["n"] += 1
            c["wins"] += 1 if p > 0 else 0
            c["pnl"] += p
        return {
            "trades": n,
            "win_rate": (wins / n * 100) if n else 0.0,
            "total_pnl": total,
            "expectancy": (total / n) if n else 0.0,
            "gross_win": gross_win,
            "gross_loss": gross_loss,
            "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else None,
            "avg_win": (gross_win / wins) if wins else 0.0,
            "avg_loss": (gross_loss / (n - wins)) if n > wins else 0.0,
            "best": max((p for _, p in trades), default=0.0),
            "worst": min((p for _, p in trades), default=0.0),
            "by_coin": by_coin,
        }

    def decision_count(self):
        return self.conn.execute("SELECT COUNT(*) AS n FROM decisions").fetchone()["n"]
