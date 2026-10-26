# Blackhorse — trade with $10, never below $5

A small, fully inspectable AI trading desk that paper-trades crypto against
**live Hyperliquid prices**, journals every decision to SQLite, shows itself on
a **localhost dashboard**, and improves its parameters through a walk-forward
learning loop. AI (Jev / Nebius / Grok) is a **veto layer only** — code
enforces all risk.

> **Educational software, not financial advice.** Perps can liquidate 100% of
> an account. Nothing here promises profit — see "Honest expectations".

---

## Quick start (no account, no keys, no money)

Double-click in `D:\Blackhorse`:

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
blackhorse/
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
dashboard DB access. **v0.3**: renamed to **blackhorse-trading**; testnet
execution adapter (`testnet.bat`, `blackhorse/testnet_broker.py`) using the
official Hyperliquid SDK; `analyst-test` one-call key verification.

## How each public repo's code/patterns are used in THIS codebase

Not copied — distilled. Every borrowed idea maps to a specific file:

| Repo | Pattern taken | Where it lives here |
|---|---|---|
| **beebots** | Model never sees the order endpoint | `analyst.py` gets indicator snapshots only; `paper.py`/`testnet_broker.py` are the only order-touching code |
| **beebots** | Explicit live ACK (`LIVE_ACK=I-ACCEPT-REAL-MONEY-RISK`) | `run.py:cmd_live` + `config.json live.acknowledgement` — engine refuses without the exact string |
| **beebots** | "Who decided" tags (model vs code) | decision feed on `dashboard.py`, `CODE` / `CODE+LLM` tags from `journal.decisions.analyst_note` |
| **beebots** | Deterministic fallback when model is slow/over-budget | `analyst.advise` returns rules-only on missing key, 401, or budget cap; loop never blocks |
| **beebots** | Stops never wait for the model | `loop.run_cycle`: TP/SL check is step 1, analyst is consulted only for entries |
| **hypergrok-trading-desk** | Pre-flight desk doctor | `doctor.py` (network, config sanity, DB, keys, port, testnet reachability) |
| **hypergrok-trading-desk** | One-writer execution + keyless reads | only `paper.py`/`testnet_broker.py` place orders; `market.py` needs no key |
| **jev-trader** | Mock/dry-run first, Jev env key | `paper.py` default; `TYPESAFE_API_KEY`; `analyst-test` one-call verification |
| **jev-trader / typesafe docs** | Typed decision questions (Choice/Noul) | `analyst._advise_jev`: `enter` Choice + `trend_continues` Noul with confidence |
| **TradingAgents** | Memory then reflection loop | `journal.py` (blackboard) + `learn.py` proposals; debate roles rejected — agents repeat bias |
| **AI-Trader** | Skill-file self-registration, leaderboards | noted for later; not needed at one-desk scale |
| **chainstack hyperliquid bot** | Testnet default, validate before run | `testnet_broker.py` + `doctor` + config-gated `testnet.enabled` |
| **Freqtrade** | Dry-run classic, fee/slippage honesty | `paper.py` models 4.5 bps fee + 5 bps slippage on every simulated fill |

## The ladder: paper → testnet → mainnet

1. **Paper (free, now)** — `run_paper.bat`. Trains the strategy on live prices
   with simulated fills. Needs nothing.
2. **Testnet (mock money, real mechanics)** — `testnet.bat` places **real
   signed orders** on Hyperliquid testnet using your testnet ETH/USDC:
   1. `pip install hyperliquid-python-sdk` (already in requirements.txt)
   2. at `app.hyperliquid-testnet.xyz` → API page, create a **trade-only API
      wallet** (cannot withdraw), copy its key
   3. `setx BLACKHORSE_TESTNET_KEY "..."` — **testnet key only, never mainnet**
   4. set `testnet.enabled: true` in config.json → `testnet.bat`
   The adapter (`blackhorse/testnet_broker.py`) uses the official SDK's
   `market_open`/`market_close`, rounds size to each coin's `szDecimals`,
   pulls account equity from the exchange, and still enforces the same
   guards: $5 floor, daily loss cap, cooldowns, halt latch. If your network
   cannot reach `api.hyperliquid-testnet.xyz` (doctor will show it), stay in
   paper mode — the strategy code is identical.
3. **Mainnet ($10, later)** — only after weeks of positive paper expectancy
   AND India tax/legal clearance; `live.enabled` + the ACK string; trade-only
   API wallet; treat the $10 as tuition.

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
