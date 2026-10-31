# 🔬 Edge Research — what actually pays, and what a $10 account can reach

Question: prop firms like Jane Street treat strong algorithms as their core
strength — where does edge actually come from, and what is reachable here?

## How the big firms actually make money (2026 research synthesis)

| Firm | Edge source | Lesson for us |
|---|---|---|
| **Jane Street** (~$39.6B net trading revenue 2025) | >20% of US ETF market making; converts "hard-to-hedge" ETF **order flow into correlation signals**; discipline across many small edges; trades only own capital | Edge = information extracted from *flow*, compounded across many small advantages — not one magic indicator |
| **Citadel Securities** | Retail PFOF internalization; latency + queue position (SmartProvide/FastFill-type algos); stat-arb inside multi-strat | Execution algorithms are the product, not the signal |
| **Microstructure literature** (Cartea et al.) | **Transaction cost control is the single most important profitability factor**; microstructure mean-reversion = trading your own flow's pricing errors, net of costs | Our fee+slippage modeling is not overhead — it IS the game |
| **Academic crypto work** | Momentum exists but regime-dependent; OBI predictive at seconds–minutes; funding carry documented | Rank edges by (evidence × accessibility), not by excitement |

## Retail-accessible edges, ranked by (evidence × accessibility at our scale)

1. **Funding-rate carry** (delta-neutral: long spot / short perp) — strongest
   published evidence for retail (up to ~115.9%/6mo in Werapun 2025), but needs
   capital on both legs and survives funding flips. **Accessible later** once
   account equity justifies two-leg positions. Funding data is public via
   `/info` — we already log it in `reconcile`.
2. **Low-frequency momentum/trend** — weakest evidence, but fully accessible at
   15m–1h timeframes. This is what our three engines trade now.
3. **Orderbook imbalance (OBI)** — academically predictive (arXiv:2108.09750)
   but at seconds–minutes horizon: latency-bound, fee-tier-sensitive. At our
   scale, useful as a **filter** (public `l2Book` endpoint), not a strategy.
4. **Cross-exchange arbitrage** — dominated by HFT with pre-positioned capital
   (Kristoufek 2023: opportunities are episodic, stress-linked). Skip.
5. **LLM sentiment/event overlay** — unproven (fleet studies show no edge);
   our analyst keeps its veto-only role.

## The honest Jane Street takeaway for Blackhorse

Jane Street's moat is not a secret algorithm — it's (a) flow information,
(b) execution cost control, (c) risk discipline across MANY small edges,
(d) years of data infrastructure. We can copy (c) and (d) today (guards,
journal, walk-forward learner, embargo), approximate (b) (fee/slippage
modeling, exchange-side stops), and must be humble about (a): at $10 on 15m
candles, we are fishing in the weakest-but-most-accessible pond, and the
pre-registered criteria exist precisely because most such fishing yields zero.

**Next edge experiments (Batch 2/3 candidates):** funding-rate signal as a
position filter (public data, zero cost); OBI as an entry filter via `l2Book`;
Donchian breakout engine (shipped); session-based regime tagging in the
learner.

## Sources

- Bloomberg via search synthesis: Jane Street 2025 revenue; "hedge fund disguised as a market maker" (Rupak Ghose)
- Fox (2024) on internalizer strategies vs HFTs; FINRA algo analysis
- Cartea et al. (2023/2026): optimal trading of microstructure mean reversion
- Albers (2021), arXiv:2108.09750 — deep learning on crypto book imbalance
- Angerer et al. (2025) — order book liquidity on crypto exchanges
- Kristoufek et al. (2023, Finance Research Letters) — Bitcoin stat-arb sources
- Werapun et al. (2025) — funding-rate arbitrage risk/return profiles
- arXiv:2212.06888 — fundamentals of perpetual futures
