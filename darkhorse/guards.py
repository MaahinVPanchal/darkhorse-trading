"""Account guards: the equity floor ("invest $10, stop below $5") and the halt
latch.

Honest limits (per the research report): a floor check runs when the loop runs
-- a fast move between cycles can push past it, stop fills can gap, and
liquidation can take a cross account to zero. The floor is a guard rail, not a
guarantee. On the exchange side, place real stop orders at entry and use a
dead-man's switch; this module is the bot-side backstop on top of that.
"""

from .journal import now_iso


def effective_floor(cfg):
    """$ floor for real-scale balances; %-floor for tiny paper accounts so the
    guard still gets exercised at $1 scale (50% of start by default)."""
    halt = cfg["halt"]
    start = cfg["paper"]["start_balance_usd"]
    if start >= 2 * halt["equity_floor_usd"]:
        return halt["equity_floor_usd"], f"${halt['equity_floor_usd']:.2f}"
    pct = halt.get("paper_floor_pct", 50)
    return start * pct / 100.0, f"{pct}% of ${start:.2f}"


def is_halted(journal):
    return journal.get_state("halt") == "1"


def halt(journal, reason):
    journal.set_state("halt", "1")
    journal.set_state("halt_ts", now_iso())
    journal.set_state("halt_reason", reason)


def resume(journal):
    for k in ("halt", "halt_ts", "halt_reason"):
        journal.set_state(k, "")


def enforce(journal, broker, cfg, prices):
    """Call at the top of every cycle. Flattens everything and latches the
    halt when equity touches the floor. Returns (halted, floor, note)."""
    floor, floor_desc = effective_floor(cfg)
    equity = broker.equity(prices)

    if equity <= floor:
        flattened = []
        for pos in journal.all_positions():
            fill = broker.close_position(
                pos["coin"], prices.get(pos["coin"], pos["avg_price"]),
                "floor-exit", f"equity ${equity:.4f} <= floor ${floor:.4f}")
            if fill:
                flattened.append(fill["coin"])
        if not is_halted(journal):
            reason = (f"equity ${equity:.4f} touched floor ${floor:.2f} "
                      f"({floor_desc}); trading halted, positions closed: "
                      f"{flattened or 'none open'}")
            halt(journal, reason)
            journal.record_decision("account", "halt", reason, equity)
        return True, floor, reason if journal.get_state("halt_reason") else "halted"

    if is_halted(journal):
        return True, floor, journal.get_state("halt_reason") or "halted"

    return False, floor, None
