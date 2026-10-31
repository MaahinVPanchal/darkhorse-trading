# Contributing to Darkhorse Trading

First: **thank you**. This project exists to be built in public — the honest
counter-example to "$14 → $7,643" screenshots. Every contribution, from a
typo fix to a new strategy engine, moves that forward.

## The one non-negotiable rule

**The AI layer may only VETO or ANNOTATE — it may never place, size, or
modify a trade, and risk limits live in code, never in prompts.** Any PR that
gives an LLM execution power will be declined, no matter how clever it is.
This is the project's thesis: measure honestly, automate discipline.

Also: **never commit keys, wallet addresses with funds, or personal data.**
Keys live in environment variables only. `run.py audit` scans git history —
keep it CLEAN.

## Good first tasks (each is scoped to roughly one file)

| Task | File(s) | Difficulty |
|---|---|---|
| Funding-rate position filter (public `/info` data already fetched in `reconcile`) | `loop.py`, `config.json` | ⭐⭐ |
| Orderbook-imbalance (OBI) entry filter via public `l2Book` | `market.py`, `loop.py` | ⭐⭐ |
| Regime classifier (trend/range tag per candle, reported by the learner) | `learn.py` | ⭐⭐ |
| Session tagging (Asia/Europe/US) in the journal + session stats | `journal.py`, `run.py report` | ⭐ |
| New provider for the decision layer (any decision-API or chat API) | `analyst.py` | ⭐⭐ |
| New strategy engine (breakout/meanrev/trend exist — bring your own, with a backtest branch in `learn.py`) | `strategy.py`, `learn.py` | ⭐⭐⭐ |
| Per-coin dashboard improvements (volume bars, funding overlay) | `dashboard.py` | ⭐⭐ |
| Backtest-vs-paper drift tracker (the 2026 benchmark idea) | `learn.py`, `journal.py` | ⭐⭐⭐ |
| Docs, translations, README screenshots | anywhere | ⭐ |

Open an issue before big changes: describe the idea, the evidence it might
have an edge (or that it improves *inspectability*), and how it will be
validated. Strategy changes must come with train/validate numbers from
`run.py learn` — including the ones that failed.

## Ground rules

- **Python 3.10+, stdlib-first.** Dependencies beyond `requests` +
  `hyperliquid-python-sdk` need strong justification.
- **Every decision must be journaled.** New features must log to the
  blackboard (`journal.py`) so any trade can be replayed and explained.
- **Walk-forward or it didn't happen.** Strategy claims need train/validate
  splits (with the embargo), and failures belong in `EXPERIMENT_LOG.md`.
- **No financial-advice language** in docs or output. We publish numbers,
  never promises.
- Tests: `run.py doctor` must pass 11/11 before a PR; add checks for new
  features where possible.

## The promotion ladder (what we're all working toward)

`paper → testnet → mainnet`, gated by pre-registered criteria
(`EXPERIMENT_LOG.md`, enforced in `promotion.py`). Contributors help build
the machine that either finds a real edge or proves there isn't one — both
outcomes are wins here.

## How to PR

1. Fork → branch (`feat/funding-filter`) → commit with a message that says
   *why*, not just *what*.
2. Run `doctor.bat` + `run.py audit` locally; paste the 11/11 + CLEAN lines
   into the PR.
3. If your change touches strategy or risk: include a learn run summary
   (train AND validate) in the PR description.

*Idea credit: the "build your own X" philosophy — you don't understand a
trading system until you've built one and watched it lose money honestly.*
