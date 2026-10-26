# START HERE — complete beginner guide

## 1. Run the bot TODAY (no account, no signup, no money)

The paper bot trades simulated money against REAL live crypto prices.
It needs nothing from you except this folder.

- Double-click **`run_paper.bat`** — the bot starts trading. Leave the window
  open. Close it (or Ctrl+C) to stop; everything is saved.
- Double-click **`run_report.bat`** — see equity, win rate, profit factor,
  max drawdown, fees, and open positions.
- Double-click **`run_learn.bat`** — the bot replays recent history and writes
  `learned_proposals.json` with better parameter suggestions (you apply them by
  editing `config.json` — it never edits itself).

Let it run for hours/days. The journal (`grokbot.db`) keeps everything.

## 2. Optional: turn on the AI decision layer (your $5 Jev credit)

1. Get your API key from the TypeSafe console (the service your $5 credit is on).
2. In a Command Prompt run (once):
   `setx TYPESAFE_API_KEY "your-key-here"`
3. In `config.json`, set `"enabled": true` inside the `analyst` section.
4. Restart `run_paper.bat`. The analyst now vets entries and logs its opinion;
   with `"mode": "gate"` it can also VETO bad entries. It can never place,
   size, or modify a trade. The daily budget cap keeps the credit lasting for
   months. Nebius works the same way with `setx NEBIUS_API_KEY "..."`.

## 3. Real-money account — NOT YET, but here is the honest map

Do NOT deposit anything until (a) the paper bot shows positive expectancy over
weeks, and (b) the India legal/tax questions below are cleared with a
qualified adviser. When that day comes, this is the path:

1. **Wallet**: install MetaMask (browser extension) or Rabby. Write the seed
   phrase on paper, never photograph or share it. Anyone with it owns your money.
2. **Buy USDC with INR** on a FIU-registered Indian exchange (e.g. CoinDCX,
   Mudrex, ZebPay — they require PAN/KYC). Withdraw the USDC on-chain
   (Arbitrum network) to your own wallet address.
3. **Deposit to Hyperliquid** (app.hyperliquid.xyz, connect wallet). The old
   bridge has a 5 USDC minimum; Hyperliquid charges ~$1 per withdrawal, which
   on a $5 balance is 20% — factor that in.
4. **Practice manually first** — place one tiny trade yourself and watch how
   stop-loss, leverage and fees behave before any bot touches it.
5. **Only then a bot API wallet**: Hyperliquid lets you create a separate
   API wallet that can TRADE but CANNOT WITHDRAW. The bot only ever gets that
   key — never your seed phrase. When we reach this step, the live adapter
   gets built and tested on testnet first.

Hard limits to remember: ~$10 minimum order size on Hyperliquid perps
(so the $10 start = one small position at a time), fees ~0.045% per fill,
and perps can liquidate 100% of the account.

## 4. India cautions (from the 26 Oct research report)

- Hyperliquid's terms do not name India as restricted, but it is NOT
  FIU-registered as far as the research found; legality of using it from
  India is unconfirmed. Check with a qualified adviser.
- India taxes virtual-digital-asset gains at a flat 30% (+cess), losses
  cannot be set off, and 1% TDS applies to certain transfers. How this maps
  to perps on a foreign DeFi venue needs professional advice.
- Rules are moving (RBI has pushed for prohibition in 2026). Keep records.

## 5. Daily use

- Morning/evening: `run_report.bat` — glance at drawdown and fees.
- Weekly: `run_learn.bat` — review proposals; only apply ones with positive
  VALIDATION expectancy over enough trades.
- If equity hits the floor: the bot halts itself; `python run.py resume`
  re-enables it (run via the python path or ask for a resume.bat).
