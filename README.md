<div align="center">

# 🐎 Darkhorse Trading

### A $10 AI trading desk that refuses to go below $5 — with receipts, not screenshots.

**Darkhorse** (n.): the little-known competitor that wins against all
expectations. That's the thesis — not a lambo promise, but the disciplined
underdog that publishes every loss.

[![Python](https://img.shields.io/badge/python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![Status](https://img.shields.io/badge/stage-paper--trading-yellow?style=flat-square)](#-the-ladder-paper--testnet--mainnet)
[![Dependencies](https://img.shields.io/badge/deps-2-success?style=flat-square)](requirements.txt)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)
[![Live AI](https://img.shields.io/badge/AI-15%20providers%20%7C%20Jev%20%2B%20gpt--6--luna%20decisions-8957E5?style=flat-square)](#-where-keys-go-and-where-they-never-go)

**Paper-trades crypto against live Hyperliquid prices • localhost dashboard • AI veto layer • walk-forward learning**

*Educational software — not financial advice. Perps can liquidate 100% of an account.*

<img src="docs/dashboard.png" alt="Darkhorse live dashboard: stat cards, equity curve with the $5 floor as a red line, agent hive, decision feed with CODE vs CODE+LLM tags" width="100%">

</div>

> *"What I cannot create, I do not understand."* — Richard Feynman
>
> This repo is that idea applied to trading: **build your own AI trading desk
> from scratch** — the order signing, the risk engine, the walk-forward
> statistics, the LLM orchestration — and you will finally understand why most
> Hyperliquid wallets lose, why viral screenshots lie, and what your own edge
> actually is. You cannot learn that from a paid course. You learn it here, in
> public, with receipts.

---

## 📖 Table of Contents

- [Why this exists](#-why-this-exists)
- [Quick Start](#-quick-start-no-account-no-keys-no-money)
- [The Dashboard](#-the-dashboard-what-is-happening-right-now)
- [The Agent Hive](#-the-agent-hive-who-does-what)
- [Where keys go](#-where-keys-go-and-where-they-never-go)
- [The Ladder](#-the-ladder-paper--testnet--mainnet)
- [How it learns](#-how-it-learns-honestly)
- [Repo comparison](#-how-it-compares-to-the-public-repos)
- [Contributing](#-contributing-build-this-with-us)
- [Naming & rights](#-naming--rights)
- [Honest numbers](#-honest-numbers)
- [India note](#-india-note)

## 🎯 Why this exists

X.com is full of *"Grok bot turned $14 into $7,643"* screenshots. We checked —
they're survivorship bait (even [Grok itself debunked one](https://x.com/sector_sol/status/2114260024675741783)).
The **one transparent public experiment** ($10,000, 22 hours, real account, on
camera) made **$0.84**.

So this project is built the boring, honest way:

- **Deterministic strategy core** (EMA cross + RSI + volume) — every signal replayable
- **Risk enforced in code, never in prompts** — the LLM can veto a trade, never place one
- **Everything journaled** — every decision, fill, and equity mark in SQLite
- **AI = referee, not gambler** — Jev/Nebius may only say "skip"; they never size or execute
- **A floor that halts the bot**: `$10 in → equity touches $5 → everything flattens`

## ⚡ Quick Start — 3 steps, anyone can run it

```bash
1. pip install -r requirements.txt      # 30 seconds
2. setup.bat                            # pick a venue, paste its key (hidden input) -- or skip for paper-only
3. start_darkhorse.bat                  # paper bot + dashboard, browser opens
```

Venues: paper (no keys) · Hyperliquid testnet (MetaMask) · Binance spot
testnet (GitHub login). Full platform map incl. Schwab/public.com/Groww
adapters: [VENUES.md](VENUES.md)

| Double-click | What happens |
|---|---|
| 🚀 `start_darkhorse.bat` | **one click = everything**: paper bot (auto-restart) + dashboard, browser opens |
| 🟢 `run_paper.bat` | **paper-trades live crypto prices** with simulated money. Leave the window open. |
| 📊 `run_dashboard.bat` | opens **http://127.0.0.1:8765** — watch the agents work |
| 🧾 `run_report.bat` | scoreboard: equity, win rate, profit factor, drawdown, fees |
| 🧠 `run_learn.bat` | walk-forward parameter search → `learned_proposals.json` |
| 🩺 `doctor.bat` | pre-flight: python, API, config, DB, keys, ports, testnet |
| 🔑 `connect_wallet.bat` | **one-time**: paste your testnet API key (hidden prompt) → auto-saves, verifies, shows balances |
| 🤖 `analyst_test.bat` | fires **one real call** at Jev/Nebius — proves your AI key works |
| 📲 `notify_test.bat` | sends one real Telegram message — proves your alert wiring |
| 🧪 `testnet.bat` | **real signed orders, mock money** on Hyperliquid testnet |
| 🔓 `resume.bat` | re-enable trading after the equity-floor halt |

CLI: `python run.py paper|report|learn|dashboard|doctor|resume|testnet|account|analyst-test|live`

## 🖥️ The Dashboard (what is happening right now)

Auto-refreshing dark terminal page — zero npm, zero CDN, pure Python + SVG:

| Panel | You see |
|---|---|
| Stat cards | equity, return vs start, max drawdown, win rate, expectancy/trade, profit factor, fees, **equity floor** |
| Equity curve | live SVG with the **$5 floor drawn as a red line** |
| Agent hive | every agent + its key/connection + exactly what power it has |
| Decision feed | every enter/skip/wait/exit tagged **`CODE`** vs **`CODE+LLM`** — who actually decided |
| Positions & fills | open positions with stops/targets, last 25 fills with PnL |
| JSON API | `GET /api/data` — build your own views |

## 🤖 The Agent Hive (who does what)

Communication is a **blackboard** (the SQLite journal) — not a chat group where
agents echo each other into confidence.

| Agent | Module | Key | Power | Cannot |
|---|---|---|---|---|
| 📡 Signal | `strategy.py` | none | propose enter/exit | execute, size |
| 🛡️ Risk Officer | `risk.py` | none | veto: caps, cooldown, loss limit | approve anything |
| ⚡ Execution | `paper.py` / `testnet_broker.py` | none / trade-only API wallet | fill, TP/SL | move its own limits |
| 🚨 Account Guard | `guards.py` | none | floor breach → flatten + **halt latch** | resume itself |
| 🧙 Analyst | `analyst.py` | `TYPESAFE_API_KEY` (Jev) / `NEBIUS_API_KEY` / `XAI_API_KEY` / `OPENROUTER_API_KEY` / `ZAI_API_KEY` | log opinions or **veto entries** (`mode: "gate"`) | open/size/modify trades |
| 🎓 Coach | `learn.py` | none | propose config edits | apply them |

## 🔑 Where keys go (and where they never go)

Keys live **only in Windows environment variables** — never in chat, never in
this repo, never in a file:

```bat
setx TYPESAFE_API_KEY "jev-key"        :: decision API: Jev ($0.042/M input, output free — $5 credit ≈ unlimited)
setx OPENAI_API_KEY "openai-key"       :: decision API: gpt-6-luna Decisions API ($0.10/M) OR chat, auto-prefers Decisions
setx NEBIUS_API_KEY "nebius-key"       :: chat fallback, OpenAI-compatible
setx ANTHROPIC_API_KEY "claude-key"    :: chat (native /v1/messages)
setx GEMINI_API_KEY / DEEPSEEK_API_KEY / GROQ_API_KEY / MISTRAL_API_KEY / TOGETHER_API_KEY / XAI_API_KEY / OPENROUTER_API_KEY / ZAI_API_KEY
setx OLLAMA_ENABLED 1                  :: local models, no key, no cost
setx ANALYST_BASE_URL "..."  + ANALYST_API_KEY + ANALYST_MODEL   :: ANY other OpenAI-compatible endpoint
setx DARKHORSE_TESTNET_KEY "0x..."    :: testnet API-wallet key (trade-only, CANNOT withdraw)
setx TELEGRAM_BOT_TOKEN "..."          :: optional: phone alerts on every fill + halt
setx TELEGRAM_CHAT_ID "..."            :: optional: your chat id (see below)
```

**15 providers, one interface.** Two decision APIs (Jev, OpenAI gpt-6-luna)
answer typed *proceed/skip + trend-probability* questions; 12 chat providers
answer strict JSON; one `custom` slot accepts any OpenAI-compatible endpoint.
Whichever key exists first (in that order) is used; the others are fallbacks.
Every provider obeys the same budget cap and the same veto-only rules.

**Telegram alerts (5 min, optional):** talk to **@BotFather** → `/newbot` → copy
the token → send any message to your new bot → open
`https://api.telegram.org/bot<TOKEN>/getUpdates` → copy the `chat.id` →
`setx` both vars → reopen terminals → `notify_test.bat` sends you a real
message. After that, every entry/exit/halt lands on your phone automatically.

Then reopen terminals → verify with `analyst_test.bat` → set `"analyst": {"enabled": true}`
in `config.json`. Daily AI budget (default **200 calls / 200k input tokens**) is
persisted in SQLite — restarts can't reset it; over budget the bot falls back
to rules-only.

> ⚠️ **Never** paste a private key into chat, WhatsApp, screenshots, or GitHub.
> An address can *view* an account — only its key can *trade* it.

## 🪜 The Ladder (paper → testnet → mainnet)

```
 ① PAPER ──────── live prices, simulated money, no keys        ← you are here
 ② TESTNET ───── real signed orders, MOCK money (your test ETH/USDC)
 ③ MAINNET ───── $10 real, trade-only API wallet, ACK gate
```

- **①** runs today: `run_paper.bat`.
- **②** needs the API key: testnet site → **API page** → *Approve API Wallet* →
  sign in MetaMask (free) → copy the private key → `connect_wallet.bat` →
  `testnet.enabled: true` → `testnet.bat`. Same guards: $5 floor, daily loss
  cap, cooldowns, halt latch.
- **③** unlocks only when `live.enabled = true` **and**
  `live.acknowledgement = "I-ACCEPT-REAL-MONEY-RISK"` — the engine refuses
  otherwise. Weeks of positive paper expectancy and India tax/legal clearance
  come first. Perps have a ~$10 minimum order size.

## 🧠 How it learns (honestly)

An LLM cannot rewrite its own weights from trading. So the loop is real
engineering: **journal → measure → walk-forward re-optimize → propose → human
applies**. `run_learn.bat` replays ~1,500 recent candles per coin, grid-searches
EMA/TP/SL combos on a **70/30 train/validate split**, and writes
`learned_proposals.json` with validation stats. The bot never edits its own
brain — that road is curve fitting.

**First run's honest result:** the *best* BTC parameter set found lost
**−1.87%/trade** on validation data. That's the baseline reality the viral
posts hide.

## 🧪 How it compares to the public repos

Blackhorse borrows deliberately, not accidentally. From beebots: the model
never sees the order endpoint, the live ACK gate, `CODE` vs `CODE+LLM`
decision tags, code fallback when the AI is over budget. From hypergrok: the
pre-flight doctor and keyless reads. From Freqtrade/chainstack: dry-run-first
with honest fee + slippage modeling and testnet defaults. From TradingAgents:
the journal-then-reflect loop — but **not** agent debates, because six agents
repeating one thesis are not six independent checks.

Full 11-repo comparison table (TradingAgents, AI-Trader, beebots,
ai-hedge-fund, Hummingbot, Jesse, Freqtrade and more), with what each taught
us: **[REPOS_COMPARED.md](REPOS_COMPARED.md)**

## 📉 Honest numbers

- Population studies (~825k Hyperliquid wallets): **most traders lose after costs**; median realized PnL per wallet: −$1.41
- Alpha Arena (6 models, real $10k each): 2 up, **4 down 42–59%** — variance, not skill
- beebots (2.4M AI decisions, 30 days): **−$214**
- This repo's first learning run: best BTC combo **−1.87%/trade** after fees

> The bot's job is to *measure* your real edge — not to promise one.

### 📋 We tested on paper first — and we publish it

We don't claim profits; we claim **process**: paper first, every decision
journaled, promotion to the next rung only if **pre-registered criteria** pass
(≥100 trades, positive expectancy after fees, profit factor > 1.2, drawdown
< 50%). The criteria were written before the results existed.

**→ See [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md) — dated entries, failures included.**

## 🇮🇳 India note

Hyperliquid's terms don't name India as restricted, but it is **not
FIU-registered** as far as research found; legality of using it from India is
unconfirmed. VDA gains ≈ **30% flat + 1% TDS**, losses can't be set off. Clear
this with a qualified adviser before rung ③. Nothing here is financial, legal,
or tax advice.

## 🗂 Files

```
run.py                  CLI: paper|report|learn|resume|dashboard|doctor|analyst-test|testnet|account|live
config.json             every knob: symbols, risk caps, floor, fees, analyst providers + budget
connect_wallet.py/.bat  one-time: hidden key prompt -> setx -> verify -> balances
grokbot→darkhorse/
  market.py             Hyperliquid public data (no keys to read)
  strategy.py           TWO engines: EMA trend cross + RSI mean-reversion (config picks)
  risk.py               veto layer: caps, loss limit, cooldown
  paper.py              simulated broker: 4.5 bps fee + 5 bps slippage
  testnet_broker.py     real signed orders via official SDK (testnet)
  journal.py            SQLite blackboard: fills, positions, decisions, equity, state
  guards.py             $5 equity floor -> flatten + halt latch
  analyst.py            Jev (/v1/systemone Choice+Noul) + Nebius/Grok/OpenRouter/ZAI
  notify.py             Telegram push: every fill + halt, to your phone
  learn.py              walk-forward grid search, RACES trend vs meanrev engines
  loop.py               guard -> TP/SL -> signal -> analyst gate -> risk -> fill
  dashboard.py          localhost UI (stdlib, SVG curve)
  doctor.py             pre-flight checks
```

## 🛡️ Naming & rights

- **The name**: "Darkhorse" = the unexpected winner. It was chosen over
  "Blackhorse" specifically to stay clear of the Lloyds Bank black-horse mark
  and existing Blackhorse-branded financial firms. If you fork: rename your
  fork and don't present it as the original.
- **No financial services**: this is open-source *software* under MIT. It is
  not a broker, adviser, or fund; nothing here solicits deposits. Names,
  logos, and the "publish our failures" format refer to this repository only.
- **Impersonation warning**: we will never DM you, never run a "support"
  Telegram that asks for keys, and never take deposits. Report fakes via the
  repo's Issues tab. See [SECURITY.md](SECURITY.md).
- **Code of conduct**: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — promoting
  deposit links or "guaranteed profit" schemes is an instant ban.

## 📜 License

MIT — see [LICENSE](LICENSE). Use at your own risk. The authors take no
responsibility for trading losses; perps can liquidate your entire account.

<div align="center">

**Built to measure, not to promise.** 🐎

</div>
