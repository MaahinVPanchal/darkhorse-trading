# Grokbot — trade with $10, never below $5

A small, fully inspectable AI trading desk that paper-trades crypto against
**live Hyperliquid prices**, journals every decision to SQLite, shows itself on
a **localhost dashboard**, and improves its parameters through a walk-forward
learning loop. AI (Jev / Nebius / Grok) is a **veto layer only** — code
enforces all risk.

> **Educational software, not financial advice.** Perps can liquidate 100% of
> an account. Nothing here promises profit — see "Honest expectations".

---

## Quick start (no account, no keys, no money)

Double-click in `D:\Grokbot`:

| File | What it does |
|---|---|
| `run_paper.bat` | start paper trading on live prices (leave window open) |
| `run_dashboard.bat` | open **http://127.0.0.1:8765** — see what's happening live |
| `run_report.bat` | console scoreboard: equity, win rate, profit factor, drawdown, fees |
| `run_learn.bat` | walk-forward parameter search → `learned_proposals.json` |
| `doctor.bat` | pre-flight checks (python, API, config, DB, keys, port) |
| `resume.bat` | re-enable trading after the equity floor halt |

CLI equivalent: `python run.py paper|report|learn|dashboard|doctor|resume|live`.

## What the dashboard shows (beebots.tech style, zero dependencies)

Dark terminal page, auto-refresh every 15s, no npm/CDN needed:

- **Stat cards**: equity, return vs start, max drawdown, win rate/trades,
  expectancy per trade, profit factor, fees paid, equity floor.
- **Equity curve** (server-side SVG) with the **$5 floor drawn as a red line**.
- **Agent hive**: every agent, its key/connection, and exactly what power it has.
- **Decision feed**: what the agents are saying, tagged `CODE` vs `CODE+LLM`
  (who actually decided — the beebots pattern).
- **Open positions & recent fills** with unrealized PnL, stops, targets.
- JSON API at `/api/data` for your own scripts.

## The agents and how their keys are connected

Communication is a **blackboard** (the SQLite journal), not a chat group. Every
agent reads and appends; the loop orders the turns.

| Agent | Module | Key / connection | Can do | Cannot do |
|---|---|---|---|---|
| Signal | `strategy.py` | none — local code | propose enter/exit | execute, size |
| Risk Officer | `risk.py` | none — local code | veto: caps, cooldown, loss limit | approve anything |
| Execution | `paper.py` | none (paper) / trade-only API wallet (live) | fill, TP/SL | move its own limits |
| Account Guard | `guards.py` | none — local code | floor breach → flatten + halt | resume itself |
| Analyst | `analyst.py` | `TYPESAFE_API_KEY` (Jev) / `NEBIUS_API_KEY` / `XAI_API_KEY` / `OPENROUTER_API_KEY` / `ZAI_API_KEY` | log opinions or veto entries (`mode: "gate"`) | open/size/modify trades, touch keys |
| Coach | `learn.py` | none — local code | propose config edits | apply them |

Key rules: keys live in **environment variables** (`setx NAME "value"`), never
in code or the repo. The daily analyst budget (200 calls / 200k input tokens
by default) is persisted in SQLite — restarts can't reset it; over budget the
bot falls back to rules-only. Jev costs ~$0.042 per **million** input tokens
with output free, so a $5 credit is effectively unlimited for this workload.

### How the agents reach Hyperliquid — "just connect and trade"?

No — and the difference matters. `app.hyperliquid.xyz/trade` is the **human**
client:

- **You (browser)**: click "Connect Wallet" → MetaMask signs an ownership
  message → the site sends signed actions to the same backend the bots use.
- **The bot (no browser)**: it never opens or "sees" the website. It talks to
  the **API** directly: public reads via `POST /info` (what we use in paper
  mode — no key at all), and orders via `POST /exchange`, where every action is
  cryptographically signed with a wallet key (EIP-712 structured signatures).
  For a bot you create a separate **API wallet** on Hyperliquid — a delegated
  key that can **trade but cannot withdraw** — so the bot never holds your
  seed phrase. beebots enforces the same shape: "the model is stateless and
  never sees an order endpoint"; signed calls go through the exchange kit.
- The live adapter (deliberately not built yet) will use the official
  `hyperliquid-python-sdk` with a trade-only API wallet, exchange-side stops,
  and a dead-man's switch — the loop-side floor check in `guards.py` is a
  backstop, not a substitute.

## Files (and what changed in the 26 Oct build session)

```
run.py                  CLI: paper/report/learn/resume/dashboard/doctor/live
config.json             symbols, risk caps, floor, fees, analyst providers+budget
requirements.txt        requests only
START_HERE.md           beginner guide (run today, account path, India notes)
AGENTS_AND_STRATEGIES.md  agent roster, strategy families, honest eval rules
run_paper.bat / run_report.bat / run_learn.bat
run_dashboard.bat / doctor.bat / resume.bat
grokbot/
  market.py     Hyperliquid public data (no keys needed to read)
  strategy.py   EMA cross + RSI + volume signals on CLOSED candles
  risk.py       veto layer: caps, daily loss limit, cooldown-after-stop-loss
  paper.py      simulated broker: fees (4.5 bps) + slippage (5 bps) modeling
  journal.py    SQLite: fills, positions, decisions, equity, state (halts, budget)
  guards.py     $5 equity floor -> flatten + halt latch; resume by human only
  analyst.py    Jev (native /v1/systemone Choice+Noul) + Nebius/Grok/OpenRouter/ZAI
                (OpenAI-compatible), daily budget cap, graceful fallback
  learn.py      walk-forward grid search (train 70% / validate 30%) -> proposals
  loop.py       orchestration: guard -> TP/SL -> signal -> analyst gate -> risk -> fill
  dashboard.py  localhost web UI (stdlib http.server, SVG equity curve)
  doctor.py     pre-flight checks
```

Recent changes: equity floor + halt latch + `resume`; profit-factor/drawdown/
fee-share reporting; Jev + Nebius providers with persisted spend cap;
**localhost dashboard**; `doctor` pre-flight; cooldown after a stop-loss
(30 min default); live ACK gate; signals on closed candles only; thread-safe
dashboard DB access.

## What we learned from public AI-trading repos

Surveyed before building (details in `AGENTS_AND_STRATEGIES.md`):

- **[beebots](https://github.com/imikerussell/beebots)** — three AI bees on OKX,
  decisions by Jev, paper by default. Adopted: model-is-stateless / never sees
  the order endpoint; explicit live ACK string; "who decided" tags; deterministic
  code fallback when the model is unavailable or over budget; stops never wait
  for the model.
- **[hypergrok-trading-desk](https://github.com/galleonlabs/hypergrok-trading-desk)**
  — 7-role desk on Hyperliquid. Adopted: `doctor` pre-flight, one-writer
  execution, ticket-style inspectability.
- **[jev-trader](https://github.com/jarrodwatts/jev-trader)** — Jev decision
  loop reference; confirmed the API shape and the mock/dry-run-first pattern.
- **[TradingAgents](https://github.com/tauricresearch/tradingagents)** (80k+
  stars), **[AI-Trader](https://github.com/HKUDS/AI-Trader)**,
  **[Freqtrade](https://github.com/freqtrade/freqtrade)** — multi-agent debate
  and web-UI patterns; noted but not copied: agent debate ≠ independent checks,
  and heavy frameworks hide the risk logic we want in plain sight.
- ⚠️ Anonymous GitHub repos matching "AI trading bot + guaranteed profit" are a
  common scam pattern for stealing keys/deposits. Everything here is readable
  code with zero deps beyond `requests`.

## Honest expectations

The public evidence (population studies of ~825k Hyperliquid wallets, LLM agent
fleet studies, Alpha Arena) says **most retail and AI-agent traders lose after
costs**. Our own first learning run found the best BTC parameter set loses
−1.87%/trade on validation data. That is the point of building it honestly:
measure, don't believe screenshots. Viral "$14 → $7,643" posts are
survivorship-bait; the one transparent public experiment ($10k, 22h, on camera)
made **$0.84**.

## Path to real money (all four, in order)

1. **Paper for weeks** — positive expectancy over many trades, across market regimes.
2. **Clear India access/tax** with a qualified adviser (Hyperliquid is not
   FIU-registered as far as research found; VDA gains ~30% + 1% TDS; losses
   can't be set off).
3. **Testnet** with a trade-only API wallet (can trade, cannot withdraw).
4. Only then: set `live.enabled=true` AND
   `live.acknowledgement="I-ACCEPT-REAL-MONEY-RISK"` — the engine refuses
   otherwise. Even so, start with an amount you are fine losing entirely.
