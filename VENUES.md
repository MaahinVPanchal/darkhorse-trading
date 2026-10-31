# 🌍 Venue map — every platform researched, honestly rated

Research date: 2026-10-31/11-01. The question: "can Darkhorse connect
public.com, Robinhood, Schwab, Fidelity, Groww, Binance and others?"

## Shipped adapters

| Venue | Mode | Status | Setup |
|---|---|---|---|
| **Paper** (live Hyperliquid prices) | simulated fills, 4.5bps fee + 5bps slip | ✅ default, zero setup | `start_darkhorse.bat` |
| **Hyperliquid testnet** | real signed orders, mock money | ✅ built (blocked only by ISP filter on this network) | `connect_wallet.bat` |
| **Binance spot testnet** | real HMAC-signed orders, mock USDT | ✅ built — **reachable from this network** | `setup.py` option 2 |

## Researched, adapter slots ready

| Platform | API status (2026) | Verdict | What an adapter needs |
|---|---|---|---|
| **Binance mainnet** | Official, HMAC keys, FIU-registered in India | ⚠️ real money — same adapter, mainnet URL + stricter guards | keys with trade-only permission; withdraw never touches the API |
| **Charles Schwab** | Official Trader API (OAuth 2.0), successor to TD Ameritrade | ✅ best US-stock adapter candidate | OAuth device flow + account hashing; equities/options domain |
| **public.com** | Official API, open to all members, no approval — stocks/ETFs/options/crypto | ✅ strong second candidate | API keys from account settings; REST |
| **Groww** (India) | Official trading API (orders, portfolio, market data) | ✅ India-route candidate; OpenAlgo also bridges it | API tokens; NSE instruments |
| **Robinhood** | Official **crypto-only** API; stocks = unofficial wrappers (ToS risk) | ⚠️ crypto adapter possible; stocks not recommended | Robinhood Crypto API keys |
| **Fidelity** | **No public API** ("nothing to announce") | ❌ closed — cannot be supported honestly | — |

## The honest architecture note

Darkhorse does **perps** (Hyperliquid) and **spot** (Binance testnet) today.
US stock brokers are a different asset class with different risk models
(hours sessions, no 24/7, PDT rules, options multipliers). The adapter
interface is the same (`equity/cash/open_position/close_position/check_exit`),
but each new venue must be validated on its own sandbox before real money —
same ladder, every time.

## MetaMask, in 3 steps (Hyperliquid route)

1. `setup.bat` → venue 1 → paste the API-wallet key (created free in MetaMask)
2. `start_darkhorse.bat` → paper + dashboard
3. `testnet.bat` → real signed orders with your test ETH/USDC

That's the whole onboarding. No deposits. No keys leave your machine.
