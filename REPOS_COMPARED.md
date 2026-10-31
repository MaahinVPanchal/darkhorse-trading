# 🔍 Repos compared — the research behind Blackhorse's design

Moved out of the README (it aged badly there — star counts and model names
drift). This is the reference snapshot from the Oct 2026 research sessions.

| Repo | What it is | How the LLM connects | Real or paper? |
| --- | --- | --- | --- |
| [TradingAgents](https://github.com/tauricresearch/tradingagents) (~80k★) | Simulated trading firm on LangGraph: fundamentals/sentiment/news/technical analysts → bull-vs-bear researcher debate → trader → risk team → portfolio manager | Any provider via env keys (OpenAI, Grok, DeepSeek, Gemini, OpenRouter, local Ollama); two tiers — quick_think_llm for analysts, deep_think_llm for managers | Paper only — simulated exchange, no real execution |
| [AI-Trader](https://github.com/HKUDS/AI-Trader) (~23k★, HKU) | Agent-native platform: AI agents publish signals, copy each other; FastAPI + React, leaderboards | Agents self-register via a SKILL.md URL (OpenClaw, Claude Code, Cursor…) | Paper ($100K simulated); real money only via your own broker signal-sync |
| [chainstacklabs/hyperliquid-trading-bot](https://github.com/chainstacklabs/hyperliquid-trading-bot) | Grid-trading bot for Hyperliquid (YAML strategies, conservative BTC grid) | No LLM — but the exchange wiring is the reference: private key in .env, testnet default, --validate check, WebSocket data | Testnet by default, mainnet only if you flip it |
| [hypergrok-trading-desk](https://github.com/galleonlabs/hypergrok-trading-desk) | 7-role trading desk on Hyperliquid (SKILL.md; works with Grok Bot/Claude) | Keyless public reads; execution only via a trade-only API wallet | Testnet first, then mainnet |
| [jev-trader](https://github.com/jarrodwatts/jev-trader) (~3.1k★) | Jev decides every Monad block (~300ms), post-only limit orders | TYPESAFE_AI_API_KEY env var; MockModel fallback | Dry-run by default |
| [Freqtrade](https://github.com/freqtrade/freqtrade) | The granddad of open-source bots (Python, web UI, plotting) | No LLM natively | Dry-run mode is the classic pattern |
| [beebots](https://github.com/imikerussell/beebots) | Three AI bees on OKX; decisions by Jev; paper by default | Jev/Gemini via env keys; model stateless, never sees the order endpoint | Paper by default; live needs explicit ACK |
| [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (~70k★) | AI hedge-fund team: analyst agents run structured bull-vs-bear debates; legendary-investor personas | Any provider via env keys; agent reports feed a risk check | Research/simulation only — cannot place trades |
| [Hummingbot](https://github.com/hummingbot/hummingbot) (~10k★) | Market-making framework across CEXs/DEXes | No LLM — config-driven strategies, order lifecycle management, dead-man's switch | Live-capable; complex by design |
| [Jesse](https://jesse.trade) (~5k★) | Strategy research & backtesting framework, clean Python API | No LLM | Backtest/paper focus |
| [OctoBot](https://github.com/Drakkar-Software/OctoBot) | User-friendly bot with AI/ML integrations | Pluggable AI/ML evaluators | Paper/trading modes |

## What Blackhorse took from each (and where it lives)

- **beebots** → model never sees the order endpoint · live ACK string · `CODE`/`CODE+LLM` tags · code fallback on budget/latency *(analyst.py, run.py, dashboard.py)*
- **hypergrok** → pre-flight `doctor` · one-writer execution · keyless reads *(doctor.py, market.py)*
- **jev-trader** → Jev Choice/Noul veto questions · dry-run-first *(analyst.py, paper.py)*
- **TradingAgents** → memory-then-reflection loop, **not** agent debate *(journal.py, learn.py)*
- **chainstack** → testnet-default + validate-before-run *(config gates, doctor.py)*
- **Freqtrade** → dry-run classic with honest fee/slippage modeling *(paper.py: 4.5 bps + 5 bps)*
- **AI-Trader / Jesse / OctoBot / Hummingbot** → patterns noted for scale (skill-file onboarding, clean strategy API, pluggable evaluators, order lifecycle) — not needed at one-desk size

⚠️ Anonymous GitHub repos matching "AI trading bot + guaranteed profit" are a
common scam pattern for stealing keys/deposits. Everything here is readable
code with two dependencies.
