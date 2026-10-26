"""Hard risk limits enforced in code, never in a prompt.

The LLM (and the strategy) can only ever *request* a trade; this module can
veto it. Limits may be tightened in config, never bypassed by the bot itself.
"""

from datetime import datetime, timezone


def _minutes_since(ts):
    t = datetime.fromisoformat(ts)
    return (datetime.now(timezone.utc) - t).total_seconds() / 60.0


def check(entry_notional, equity, journal, cfg, is_paper=True, coin=None):
    """Return (allowed, reasons). is_paper skips exchange-minimum checks since
    simulated fills have no venue constraints."""
    limits = cfg["risk"]
    reasons = []

    if not is_paper and entry_notional < 10.0:
        reasons.append(
            f"notional ${entry_notional:.2f} is below Hyperliquid's ~$10 minimum order size")

    if journal.trades_today() >= limits["max_trades_per_day"]:
        reasons.append(f"daily trade cap reached ({limits['max_trades_per_day']})")

    cooldown = limits.get("cooldown_after_stop_min", 0)
    if cooldown and coin:
        last_sl = journal.last_stop_loss_ts(coin)
        if last_sl:
            mins = _minutes_since(last_sl)
            if mins < cooldown:
                reasons.append(
                    f"cooldown: stop-loss on {coin} was {mins:.0f} min ago "
                    f"(waiting {cooldown})")

    stats = journal.trade_stats()
    start = cfg["paper"]["start_balance_usd"]
    day_drawdown_pct = -stats["total_pnl"] / start * 100 if start else 0.0
    if day_drawdown_pct >= limits["daily_loss_limit_pct"]:
        reasons.append(
            f"cumulative loss {day_drawdown_pct:.1f}% hit the "
            f"{limits['daily_loss_limit_pct']}% loss limit")

    max_notional = equity * limits["max_position_pct_of_equity"] / 100.0
    if entry_notional > max_notional:
        reasons.append(
            f"notional ${entry_notional:.2f} exceeds "
            f"{limits['max_position_pct_of_equity']}% of equity ${equity:.2f}")

    return (not reasons), reasons
