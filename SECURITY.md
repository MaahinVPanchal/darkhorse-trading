# Security Policy

## The short version

- **We will NEVER ask you for private keys, seed phrases, deposits, or payments.**
  Not in issues, not in DMs, not in "support" chats. Anyone who does is
  impersonating this project -- report and block them.
- Keys used by this bot live **only in your machine's environment variables**
  (`setx ...`), and only trade-only API-wallet keys are supported. The code
  cannot withdraw; the venue-side API wallet cannot withdraw.

## Reporting a vulnerability

Open a **private security advisory** via GitHub (repo → Security → Advisories)
or contact the maintainer through the GitHub profile. Do **not** open a public
issue for anything that could expose a user.

Scope: anything that could (a) leak keys or journal data, (b) cause the bot to
trade beyond the risk limits in `config.json` + `risk.py`, (c) defeat the
promotion gates in `promotion.py` / the ACK gate in `run.py live`, or (d)
break the audit trail in the journal.

## What we do to keep the repo safe

- `run.py audit` scans the full git history for secrets (must be CLEAN before
  any release or publicity).
- `.gitignore` blocks `.env` and `*.db` (the journal may contain your trading
  history).
- Dependencies are minimal (`requests`, `hyperliquid-python-sdk`) and
  reviewed; new dependencies need justification in the PR.

## About clones and impersonation

Crypto-trading repos get cloned and re-shipped with key-stealing code by
scammers. The **only** official home of this project is
`github.com/MaahinVPanchal/darkhorse-trading`. Forks are welcome under the
MIT license but must be renamed and must not present themselves as the
original project. If you find a fake claiming to be us -- especially one
asking for deposits -- please open an issue so we can warn users and report it.
