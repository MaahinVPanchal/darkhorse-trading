# 📦 Batch Plan — resources iterated, work in batches of 10

Resources iterated: **GitHub** (hummingbot, jesse, virattt/ai-hedge-fund,
nautilus_trader, freqtrade, beebots, jev-trader), **StackOverflow/Reddit**
(SSL root-cause), **nautilustrader.io**, **openalgo.in**, **nexustrade.io**,
plus prop-firm edge research (see **EDGE_RESEARCH.md**).

## Research findings → what we adopted

| Resource | Finding | Adopted as |
|---|---|---|
| **nautilustrader.io** | Event-sourced durable log + **reconciliation soak loops** | `run.py reconcile` + `journal.events` order-state log |
| nautilustrader.io | Research-to-live parity; typed config | same loop for paper/testnet/mainnet |
| **openalgo.in** | India broker bridge (35+), server-side risk | Batch 3 evaluation note |
| **nexustrade.io** | **Walk-forward with embargo gap** | `learn.py` `embargo_bars: 20` |
| nexustrade.io | Approval-gated live automation | ACK gate + `promotion.py` code-enforced criteria |
| **StackOverflow/Reddit** | `WRONG_VERSION_NUMBER` = proxy/captive portal | Diagnosed: no local proxy → upstream ISP filter |
| **EDGE_RESEARCH.md** | Jane Street: many small edges + cost control + discipline; funding carry = best retail-evidence edge | roadmap: funding filter, OBI filter, Donchian engine |

---

## BATCH 1 — Diagnose, reconcile, embargo — ✅ 10/10

Proxy diagnosis · testnet retest · NautilusTrader/OpenAlgo/NexusTrade research ·
SSL root-cause · `reconcile` · learn embargo · live tests · commit/push · runbook.

## BATCH 2 — Auto-working hardening — ✅ 10/10

| # | Task | Status |
|---|---|---|
| 1 | `watchdog.bat` auto-restart wrapper | ✅ |
| 2 | Telegram daily digest (`run.py digest`, auto-sends if configured) | ✅ |
| 3 | Reconcile step in Monday automation | ✅ |
| 4 | Nautilus-style order-state event log (submitted/filled/rejected) | ✅ `journal.events` + testnet broker |
| 5 | Multi-timeframe gate (1h EMA filter before 15m entries) | ✅ `config.mtf` |
| 6 | Per-coin realized-PnL curves in dashboard | ✅ |
| 7 | Third engine: Donchian breakout | ✅ `strategy._eval_breakout` |
| 8 | Engine leaderboard persisted across weeks | ✅ `learn_history.jsonl` |
| 9 | Secrets-audit script (`run.py audit`) | ✅ verdict: CLEAN |
| 10 | Fee/funding reconciliation | ✅ `reconcile` shows userFunding |

## BATCH 3 — Live-adjacent — 6/10 done, rest by design

| # | Task | Status |
|---|---|---|
| 1 | Mainnet adapter (`darkhorse/mainnet_broker.py`) | ✅ TRIPLE-GATED: live.enabled + exact ACK + promotion criteria computed from journal |
| 2 | Exchange-side stop orders + dead-man's switch | ⏸ deferred — needs a live testnet session to verify trigger orders (code slot ready) |
| 3 | OpenAlgo bridge evaluation | ✅ research note (AGPL caveat) |
| 4 | Latency + partial-fill modeling upgrade | ⏸ reserved — paper modeling already covers fee+slip; upgrade when testnet data exists |
| 5 | Kill-switch (`run.py panic`) + watchdog | ✅ |
| 6 | Regime classifier (trend/range tagging in learner) | ⏸ reserved |
| 7 | Funding-rate signal as position filter | ⏸ reserved — data already fetched in reconcile |
| 8 | OBI filter via public `l2Book` | ⏸ reserved |
| 9 | Position-sizing evolution (fixed-fractional → vol-adjusted) | ⏸ reserved |
| 10 | Scale-out/take-profit laddering | ⏸ reserved |

---

## 🔑 The one manual step (everything else is automatic)

Testnet is **ISP-filtered on this network** (verified: no proxy, upstream filter):

1. On a network that reaches `app.hyperliquid-testnet.xyz` (phone hotspot):
   MetaMask → **API page** → **Approve API Wallet** → sign (free) → copy key.
2. `connect_wallet.bat` → paste into hidden prompt → auto-saves + verifies.
3. `testnet.enabled: true` → `testnet.bat` → real orders, mock money, all guards.

Live mainnet (`run.py live`) is code-complete and refuses until
`live.enabled` + exact ACK string + ALL promotion criteria pass — computed
from the journal, not editable.
