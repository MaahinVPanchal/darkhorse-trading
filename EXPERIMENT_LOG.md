# 📋 Experiment Log — Darkhorse Trading

Public, dated, honest. This file is the receipt trail: what we tested, what it
showed, and what we did next. Nothing here is a performance promise.

**The commitment:** paper first for weeks → testnet with mock money → mainnet
only if the pre-registered criteria below are met. Every claim in this file
links to the SQLite journal it came from (`darkhorse.db`).

---

## Pre-registered promotion criteria (written 2026-10-26, BEFORE results)

We move to the next rung of the ladder only when ALL of these hold, judged on
the paper journal as-is — no parameter re-tuning to force a pass:

| # | Criterion | Threshold |
|---|---|---|
| 1 | Minimum paper trades before judging | **≥ 100 closed trades** |
| 2 | Expectancy per trade (after 4.5 bps fee + 5 bps slippage) | **> 0** |
| 3 | Profit factor (gross win / gross loss) | **> 1.2** |
| 4 | Max drawdown | **< 50%** of start balance |
| 5 | Tested across market regimes | trending AND ranging weeks included |
| 6 | Every parameter set tried is counted | `learn.py` train AND validate stats logged |

If criteria fail → we stay on paper (or change strategy openly, logged here).
If they pass → testnet for real order mechanics, then the mainnet ACK gate.

---

## Log

### 2026-10-26 — Day 0: system built, paper run started

- **Built & verified** (all checks green, see commit history):
  - paper broker on live Hyperliquid prices (BTC/ETH/SOL, 15m candles)
  - fee (4.5 bps) + slippage (5 bps) modeled on every simulated fill
  - risk layer: 60%/trade sizing, 80% max exposure, 10 trades/day cap,
    15% daily loss limit, 30-min cooldown after stop-loss
  - $5 equity floor → flatten + halt latch (tested by forced breach)
  - dashboard at `127.0.0.1:8765` (screenshot in README)
  - walk-forward learner, Jev/Nebius analyst gate, live ACK gate
- **First full trade lifecycle** (paper, live prices):
  - entry: BTC @ $80,274.62 — fresh EMA cross up, RSI 56, volume ×3.1
  - exit: signal-exit @ $80,041.46 — EMA flipped down
  - **PnL: −$0.0020** on $0.60 notional (fees + slippage modeled)
- **First learning run:** best of 180 parameter combos for BTC = **−1.87%
  expectancy/trade on validation** (train −1.26%). ETH/SOL: not enough
  signal trades. Honest read: the default strategy has NO edge after costs
  right now. This is expected — it's why we paper trade.
- **Status:** 🟡 PAPER — collecting trades. No conclusions possible or drawn.

### Entry template (for future updates)

```
### YYYY-MM-DD — Day N: <headline>
- trades since last entry: N (total N)
- expectancy: $X/trade | profit factor: X.XX | max drawdown: X%
- what changed (if anything): ...
- verdict vs pre-registered criteria: pass/fail per item
- next action: ...
```

---

## Why we publish failures

The "$14 → $7,643" genre survives on survivorship bias — nobody posts the
liquidation. This file exists to be the opposite: pre-registered criteria,
dated entries, failures kept visible. If the day comes when every criterion
passes for 100+ trades, the receipts will already be here.
