"""Telegram push notifications: the bot reports to your phone.

Setup (5 min, optional):
  1. In Telegram, talk to @BotFather -> /newbot -> copy the bot token
  2. Send any message to your new bot (this starts the chat)
  3. Visit https://api.telegram.org/bot<TOKEN>/getUpdates and copy
     "chat":{"id": ...} from the response
  4. setx TELEGRAM_BOT_TOKEN "..."  and  setx TELEGRAM_CHAT_ID "..."
  5. reopen terminals, then run `python run.py notify-test`

If either var is missing, notifications are silently skipped -- the trading
loop never depends on them.
"""

import os

import requests

API = "https://api.telegram.org"


def configured():
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN")
                and os.environ.get("TELEGRAM_CHAT_ID"))


def send(text, silent=False):
    """Best-effort delivery. Never raises; returns True if sent."""
    if not configured():
        return False
    try:
        r = requests.post(
            f"{API}/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
            json={"chat_id": os.environ["TELEGRAM_CHAT_ID"],
                  "text": text[:4000],
                  "disable_notification": silent},
            timeout=8)
        return r.ok
    except Exception:
        return False


def fills_message(actions, equity):
    lines = []
    for a in actions:
        line = f"{a['action']} {a['coin']} @ {a['price']:.2f}"
        if a.get("pnl") is not None:
            line += f" | pnl {a['pnl']:+.4f}"
        if a.get("reason"):
            line += f"\n{i_reason(a['reason'])}"
        lines.append(line)
    return ("Darkhorse paper desk\n" + "\n".join(lines)
            + f"\nequity ${equity:.4f}")


def i_reason(reason):
    return f"   ({reason})"


def digest_message(cfg, stats, total, halted):
    return ("Darkhorse daily digest\n"
            f"equity ${total:.4f} | trades {stats['trades']} | "
            f"win {stats['win_rate']:.0f}%\n"
            f"expectancy ${stats['expectancy']:+.4f}/trade | "
            f"halted: {'YES' if halted else 'no'}")


def test():
    """One real message to verify the wiring end to end."""
    if not configured():
        return False, ("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set. "
                       "Create a bot with @BotFather, then setx both vars "
                       "and open a NEW terminal.")
    ok = send("Darkhorse notify test -- connection OK.")
    if ok:
        return True, "message delivered to your chat"
    return False, "send failed -- check the token and that you messaged the bot once"
