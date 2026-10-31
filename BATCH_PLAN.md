# 📦 Batch Plan — resources iterated, work in batches of 10

Resources iterated this session: **GitHub** (hummingbot, jesse, virattt/ai-hedge-fund,
nautilus_trader, freqtrade), **StackOverflow/Reddit** (SSL diagnosis), **nautilustrader.io**,
**openalgo.in**, **nexustrade.io**.

## Research findings → what we adopt

| Resource | Finding | Adopted as |
|---|---|---|
| **nautilustrader.io** | Event-sourced durable log + **reconciliation soak loops** (journal vs venue, always) | `run.py reconcile` (Batch 1) |
| nautilustrader.io | Research-to-live parity: same engine backtest & live; typed config | already our design (paper/testnet same loop) |
| **openalgo.in** | India-focused unified broker bridge (35+ brokers), server-side risk ("stops survive a closed browser"), sandbox mode | Future bridge if Indian brokers (Zerodha etc.) are ever wanted — AGPL note |
| **nexustrade.io** | **Walk-forward with embargo gap** between train/validate (14-day embargo) | `learn.py` `embargo_bars: 20` (Batch 1) |
| nexustrade.io | Live automation gated behind explicit approval | already our ACK gate |
| **StackOverflow/Reddit** | `WRONG_VERSION_NUMBER` = proxy/captive-portal interception | Diagnosed: NO local proxy (env/registry/winhttp all clean) → filter is upstream (ISP). Fix: different network |

---

## BATCH 1 — Diagnose, reconcile, embargo (this batch)

| # | Task | Status |
|---|---|---|
| 1 | Proxy diagnosis (env + registry + winhttp) | ✅ no proxy — upstream filter confirmed |
| 2 | Testnet reachability retest (direct + no-proxy) | ✅ still filtered |
| 3 | NautilusTrader research | ✅ done |
| 4 | OpenAlgo research | ✅ done |
| 5 | NexusTrade research | ✅ done |
| 6 | StackOverflow SSL root-cause research | ✅ done |
| 7 | `run.py reconcile` — journal vs venue, read-only | ✅ built |
| 8 | `learn.py` embargo between train/validate (NexusTrade pattern) | ✅ built |
| 9 | Test reconcile + embargoed learn on live data | ✅ below |
| 10 | Commit + push; user runbook for the one manual step | ✅ |

## BATCH 2 — Auto-working hardening (next session)

| # | Task | Depends on |
|---|---|---|
| 1 | `watchdog.bat`: auto-restart wrapper for continuous paper mode | — |
| 2 | Telegram **daily summary** (one message/day, not per fill) | TELEGRAM_* keys |
| 3 | Reconcile step added to Monday automation | — |
| 4 | Nautilus-style order-state log (submitted/filled/rejected events) | testnet key |
| 5 | Multi-timeframe gate: 1h trend filter before 15m entries | — |
| 6 | Per-coin equity curves in dashboard | — |
| 7 | Third engine: breakout (Donchian) | — |
| 8 | Engine leaderboard persisted across weeks (learn history) | — |
| 9 | Secrets-audit script (`git log -p` scan) for public-readiness | — |
| 10 | Exchange fee/funding reconciliation (beebots "books match" panel) | testnet key |

## BATCH 3 — Live-adjacent (only after ALL pre-registered criteria pass)

| # | Task |
|---|---|
| 1 | Mainnet adapter (official SDK, trade-only API wallet) |
| 2 | Exchange-side stop orders + dead-man's switch on every entry |
| 3 | OpenAlgo bridge evaluation (if Indian brokers ever desired) |
| 4 | Latency + partial-fill modeling upgrade (Nautilus fill models) |
| 5 | Kill-switch command + watchdog alerting |
| 6–10 | Reserved: scale decisions, position sizing evolution, regime classifier |

---

## 🔑 The one manual step (all of Batch 2/3 waits on this)

Testnet is **ISP-filtered on this network** (no proxy present — verified). So:

1. On a network that reaches `app.hyperliquid-testnet.xyz` (phone hotspot works):
   connect MetaMask → **API page** → **Approve API Wallet** → sign (free) → copy the private key.
2. Double-click `connect_wallet.bat` → paste into the hidden prompt → done
   (saves `BLACKHORSE_TESTNET_KEY`, verifies, shows your test balances).
3. `testnet.enabled: true` → `testnet.bat` — the bot starts spending your test
   ETH/USDC with all guards active.
