# Agents, strategies, and how to judge loss/gain

Companion to README.md. Grounded in the research report from 26 Oct 2026
(Hyperliquid docs, population studies, LLM-agent fleet studies).

## Part 1: which agents exist here, and how they talk

This bot is already a small agent team. The communication pattern is a
**blackboard**, not a chat group: every agent reads and writes to the shared
SQLite journal (`blackhorse.db`), and the loop orchestrates the order. That is
deliberate -- chat-style agent swarms mostly repeat each other's bias, and the
fleet studies found on-chain LLM trading agents have **no directional edge**
(41% vs 50% round-trip win rate for Hyperliquid agents).

| Agent (module) | Job | Can do | Cannot do |
|---|---|---|---|
| **Scanner/Signal** (`strategy.py`) | EMA cross + RSI + volume on closed candles | propose enter/exit | execute, size |
| **Risk Officer** (`risk.py`) | veto layer: caps, loss limit, sizing bounds | reject any trade | approve around limits |
| **Execution** (`paper.py`, later live adapter) | fill, fees, slippage, TP/SL | place/clear positions | change its own limits |
| **Journalist** (`journal.py`) | append-only record of every decision + fill | record | delete or edit history |
| **Account Guard** (`guards.py`) | equity floor ($10 -> stop under $5), halt latch | flatten everything, halt | resume itself (human runs `resume`) |
| **Analyst** (`analyst.py`, Jev/Nebius/Grok) | optional veto/annotation on entries | say no, or log an opinion | open trades, raise size/leverage/count |
| **Coach** (`learn.py`) | walk-forward parameter search -> proposals | propose config edits | apply them (human applies) |

Message flow per cycle:

```
market data -> Guard (floor check) -> TP/SL (Execution)
            -> Signal proposes -> Analyst (veto?) -> Risk (veto?) -> Execution fills
            -> everything appended to the Journal (the blackboard)
Coach reads the Journal offline -> writes learned_proposals.json -> human approves
```

If you later want *true* multi-agent (separate processes/models talking), the
journal is already the message bus: each agent is a loop that polls its role's
table and appends decisions. Start extra agents only when a measured need
exists -- every LLM agent burns credit and adds latency without proven edge.
The viral "6 agents / 350 agents" architectures look impressive but six agents
repeating one bullish thesis are not six independent checks.

### Using Jev and Nebius as the decision layer

- **Jev** (TypeSafe AI, "System One" decision model) is the best fit for the
  veto gate at your size: it returns typed decisions (Choice/Noul) with
  confidence, at ~$0.042 per million INPUT tokens with output free. Your $5
  credit covers roughly 119 billion input tokens -- the binding limit is the
  daily call cap we enforce (200 calls/day default), not the money. Set
  `TYPESAFE_API_KEY` in the environment; the bot calls `POST
  api.typesafe.ai/v1/systemone` with the market state and two questions
  ("proceed or skip", "trend continues?") and only vetoes when it says so.
- **Nebius AI Studio** (OpenAI-compatible, `https://api.studio.nebius.ai/v1`)
  is the fallback: set `NEBIUS_API_KEY`, model configurable (default
  `meta-llama/Llama-3.3-70B-Instruct` -- check studio.nebius.ai for current
  ids/pricing). It can also serve the Coach's journal-summarizing role.
- Both can run together: Jev as the fast veto referee on entries, Nebius as a
  nightly post-mortem reader that summarizes losing trades into rule-change
  proposals you review. Neither ever touches keys or sizes.

## Part 2: strategies that exist, honestly rated

| Family | Evidence | Fit for $10 |
|---|---|---|
| Slow trend following (time-series momentum) | strongest published support in crypto; but portfolio-level studies, not $10 accounts | the least-bad starting point; keep turnover low |
| MA/breakout rules (what we run) | mixed; ~15,000-rule study found no Bitcoin edge out of sample; costs decide | expect nothing after fees; that's why we paper trade |
| Funding-rate carry | registry backtests: 1 of 13 beat benchmark, none confirmed after multiple-testing correction | needs 2 legs + more capital; no |
| Market making / scalping | fee tier + latency decides; $10 pays top fees | no |
| LLM-picked directional trades | fleet studies + Alpha Arena: variance, not skill (2 of 6 models up, 4 down 42-59%) | veto role only, never the decider |

## Part 3: how to check loss and gain without lying to yourself

The report command now prints the honest set:

- **Expectancy per trade** (mean pnl) -- the single number that matters.
- **Profit factor** (gross win / gross loss). Below ~1.5 with fees included,
  don't get excited.
- **Max drawdown** from the equity curve (and the $5 floor that enforces it).
- **Fee share**: fees paid vs traded notional. At $10 scale this is a
  silent tax that turns small edges negative.
- **Win rate alone is meaningless** -- 68% wins with bigger losses still bleeds.

Rules for reading results (from the research, compressed):

1. Define pass/fail criteria BEFORE looking. Changing settings after each
   result is how bots become curve-fit.
2. Trade count is not a pass mark. With ~2% per-trade swings, even a true
   +0.1%/trade edge needs on the order of 1,500 trades to distinguish from
   zero; 100 trades has about +/-0.4% uncertainty.
3. Trades overlap and regimes cluster, so real uncertainty is worse than the
   arithmetic. Test across trending, ranging, and crash periods.
4. Count every parameter set you tried (`learn` reports train AND validate for
   a reason); the more you try, the higher the bar for believing the winner.
5. Walk-forward only: tune on one window, test untouched on the next. Keep one
   final untouched slice you look at exactly once.
6. Benchmark against holding BTC and against doing nothing.
7. Backtests flatter. Assume live paper results will be worse, and live-real
   worse again.
