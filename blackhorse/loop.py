"""Main trading loop: poll live prices -> manage open positions (TP/SL first)
-> evaluate strategy -> optional analyst gate -> risk veto -> paper fill -> log.
"""

import time

from . import analyst, guards, market, notify, risk, strategy
from .paper import PaperBroker


def run_cycle(journal, broker, cfg, use_analyst=True, verbose=True):
    prices = market.all_mids()

    # 0. account guards first: equity floor, halt latch
    was_halted = guards.is_halted(journal)
    halted, floor, note = guards.enforce(journal, broker, cfg, prices)
    if halted:
        equity = broker.equity(prices)
        journal.record_equity(broker.cash(), broker.unrealized(prices), equity)
        if not was_halted:
            notify.send(f"BLACKHORSE HALTED (equity ${equity:.4f} <= floor "
                        f"${floor:.2f}):\n{note}\n\n"
                        f"Run resume.bat to re-enable (your call).")
        if verbose:
            print(f"[{time.strftime('%H:%M:%S')}] HALTED: {note} | "
                  f"equity ${equity:.4f} | floor ${floor:.2f} | "
                  f"run 'python run.py resume' to re-enable")
        return []

    actions = []
    for coin in cfg["symbols"]:
        price = prices.get(coin)
        if not price:
            continue

        # 1. protect the open position first: stop-loss / take-profit
        if broker.check_exit(coin, price) is not None:
            continue

        pos = journal.get_position(coin)
        candles = market.candles(coin, cfg["timeframe"], cfg["candle_lookback"])
        # signal on CLOSED candles only (drop the still-forming bar)
        sig = strategy.evaluate(candles[:-1], cfg["strategy"])

        # 2. signal exit (trend flip)
        if sig["action"] == "exit" and pos:
            fill = broker.close_position(coin, price, "signal-exit", sig["reason"])
            if fill:
                actions.append(fill)
            journal.record_decision(coin, "exit", sig["reason"], price)
            continue

        # 3. entry path
        if sig["action"] == "enter" and not pos:
            verdict = analyst.advise(cfg, journal, coin, price, sig, pos) \
                if use_analyst and analyst.available(cfg) else None
            note = None
            if verdict:
                note = (f"[{verdict['provider']}] {verdict['bias']} "
                        f"{verdict['confidence']:.2f}: {verdict['note']}")
                if cfg["analyst"].get("mode") == "gate" and not analyst.agrees(verdict, sig):
                    journal.record_decision(coin, "skip",
                                            f"analyst gate rejected: {note}", price, note)
                    continue

            mtf = cfg.get("mtf", {})
            if mtf.get("enabled"):
                try:
                    h1 = market.candles(coin, mtf.get("timeframe", "1h"), 60)
                    f = strategy.ema([c["close"] for c in h1],
                                     mtf.get("ema_fast", 10))
                    s = strategy.ema([c["close"] for c in h1],
                                     mtf.get("ema_slow", 30))
                    if f is None or s is None or f < s:
                        journal.record_decision(
                            coin, "skip",
                            f"MTF gate: {mtf.get('timeframe', '1h')} trend down",
                            price, note)
                        continue
                except Exception as e:
                    journal.record_decision(coin, "skip",
                                            f"MTF gate error: {e}", price, note)
                    continue
            equity = broker.equity(prices)
            notional = equity * cfg["risk"]["position_pct_per_trade"] / 100.0
            allowed, reasons = risk.check(notional, equity, journal, cfg,
                                          is_paper=True, coin=coin)
            if not allowed:
                journal.record_decision(coin, "skip", "; ".join(reasons), price, note)
                continue
            fill = broker.open_position(coin, price, notional, sig["reason"], note)
            actions.append(fill)
            journal.record_decision(coin, "enter", sig["reason"], price, note)
        else:
            journal.record_decision(coin, sig["action"], sig["reason"], price)

    equity = broker.equity(prices)
    journal.record_equity(broker.cash(), broker.unrealized(prices), equity)

    if actions:
        notify.send(notify.fills_message(actions, equity), silent=True)

    if verbose:
        n_pos = len(journal.all_positions())
        print(f"[{time.strftime('%H:%M:%S')}] equity ${equity:.4f} | "
              f"cash ${broker.cash():.4f} | positions {n_pos} | "
              f"actions this cycle: {len(actions)}")
        for a in actions:
            pnl = f" pnl {a['pnl']:+.4f}" if "pnl" in a else ""
            print(f"    {a['action']:<12} {a['coin']} @ {a['price']:.2f}{pnl}"
                  f" -- {a.get('reason') or ''}")
    return actions


def run(journal, broker, cfg, cycles=None, use_analyst=True):
    i = 0
    while cycles is None or i < cycles:
        try:
            run_cycle(journal, broker, cfg, use_analyst=use_analyst)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"cycle error (will retry): {e}")
        i += 1
        if cycles is None or i < cycles:
            time.sleep(cfg["cycle_seconds"])
