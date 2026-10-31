"""Promotion gate: the pre-registered criteria, enforced IN CODE.

The same criteria from EXPERIMENT_LOG.md, computed directly from the
journal so they cannot be editorialized. Live trading refuses until every
check passes -- this is the machine-readable version of the human promise.
"""


def max_drawdown_pct(journal, start):
    hist = journal.equity_history()
    if len(hist) < 2 or start <= 0:
        return 0.0
    peak, dd = hist[0]["total"], 0.0
    for h in hist:
        peak = max(peak, h["total"])
        dd = max(dd, (peak - h["total"]) / peak * 100 if peak > 0 else 0.0)
    return dd


def check(journal, cfg):
    """Returns (all_pass, [(name, pass, detail), ...])."""
    stats = journal.trade_stats()
    start = cfg["paper"]["start_balance_usd"]
    dd = max_drawdown_pct(journal, start)
    pf = stats["profit_factor"]
    checks = [
        ("trades >= 100",
         stats["trades"] >= 100,
         f"{stats['trades']} closed trades"),
        ("expectancy > 0 after fees",
         stats["expectancy"] > 0,
         f"${stats['expectancy']:+.4f}/trade"),
        ("profit factor > 1.2",
         pf is not None and pf > 1.2,
         f"{pf:.2f}" if pf else "n/a"),
        ("max drawdown < 50%",
         dd < 50.0,
         f"{dd:.2f}%"),
    ]
    return all(ok for _, ok, _ in checks), checks


def report(journal, cfg):
    ok, checks = check(journal, cfg)
    lines = [f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}"
             for name, ok, detail in checks]
    return ok, "\n".join(lines)
