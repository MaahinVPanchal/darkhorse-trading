"""Decision-layer providers for the veto gate.

Providers (tried in config order, first key found wins):
  - Jev (TypeSafe AI "System One" decision model): native /v1/systemone API,
    returns typed Choice/Noul answers with probabilities and confidence.
    ~$0.042 per million INPUT tokens, output free -- a $5 credit is roughly
    119 billion input tokens, so the real limit is our own call cap, not cost.
  - Nebius AI Studio: OpenAI-compatible chat completions, cheap open models.
  - xAI Grok / OpenRouter / ZAI: OpenAI-compatible chat completions.

Ground rules (unchanged):
  - The LLM NEVER executes trades. mode 'log' annotates; mode 'gate' may only
    veto an entry the rule engine already produced. It cannot raise size,
    leverage, trade count, or move a stop -- the risk engine bounds all of it.
  - A hard daily budget (calls + input tokens, persisted in the journal) makes
    the credit last: when the cap trips, the bot falls back to rules-only.
"""

import json
import os
import re
from datetime import datetime, timezone

import requests

JEV_URL = "https://api.typesafe.ai/v1/systemone"
CHAT_ENDPOINTS = {
    "nebius": ("NEBIUS_API_KEY", "https://api.studio.nebius.ai/v1/chat/completions",
               "meta-llama/Llama-3.3-70B-Instruct"),
    "xai": ("XAI_API_KEY", "https://api.x.ai/v1/chat/completions", "grok-4-fast"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions",
                   "openai/gpt-4o-mini"),
    "zai": ("ZAI_API_KEY", "https://api.z.ai/api/paas/v4/chat/completions", "glm-4.6"),
}
PROVIDER_ORDER = ["jev", "nebius", "xai", "openrouter", "zai"]

CHAT_PROMPT = """You are the risk-conscious analyst on a small trading desk.
Current state for {coin} on Hyperliquid ({timeframe} candles):

price: {price:.2f}
signal from the rule engine: {action} ({reason})
open position: {position}
indicators: EMA_fast={ema_fast:.2f} EMA_slow={ema_slow:.2f} RSI={rsi:.1f} vol_ratio={vol_ratio:.2f}

Reply with ONLY a JSON object, no prose:
{{"bias": "long"|"flat", "confidence": 0.0-1.0, "note": "one-sentence justification"}}
Be skeptical: confidence below 0.5 means "no trade"."""


def available(cfg):
    a = cfg.get("analyst", {})
    if not a.get("enabled"):
        return None
    order = a.get("provider") or "auto"
    if isinstance(order, str):
        order = PROVIDER_ORDER if order == "auto" else [order]
    for p in order:
        if p == "jev":
            if os.environ.get("TYPESAFE_API_KEY") or os.environ.get("TYPESAFE_AI_API_KEY"):
                return "jev"
        elif p in CHAT_ENDPOINTS:
            env = CHAT_ENDPOINTS[p][0]
            if os.environ.get(env):
                return p
    return None


def _budget_ok(journal, cfg, est_input_tokens):
    """Daily call + input-token cap, persisted so restarts don't reset it."""
    a = cfg["analyst"]
    budget = a.get("budget", {})
    call_cap = budget.get("daily_call_cap", 200)
    tok_cap = budget.get("daily_input_token_cap", 200000)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    calls = int(journal.get_state(f"analyst_calls_{day}", "0"))
    toks = int(journal.get_state(f"analyst_tokens_{day}", "0"))
    if calls >= call_cap:
        return False, f"daily call cap reached ({calls}/{call_cap})"
    if toks + est_input_tokens >= tok_cap:
        return False, f"daily input-token cap reached ({toks}/{tok_cap})"
    return True, None


def _budget_record(journal, input_tokens):
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    calls = int(journal.get_state(f"analyst_calls_{day}", "0"))
    toks = int(journal.get_state(f"analyst_tokens_{day}", "0"))
    journal.set_state(f"analyst_calls_{day}", calls + 1)
    journal.set_state(f"analyst_tokens_{day}", toks + int(input_tokens))


def advise(cfg, journal, coin, price, signal, position):
    """Return {bias, confidence, note, provider} or None (rules-only fallback)."""
    provider = available(cfg)
    if not provider:
        return None
    est_tokens = max(200, len(repr(signal)) // 2)
    ok, why = _budget_ok(journal, cfg, est_tokens)
    if not ok:
        return {"bias": "flat", "confidence": 0.0,
                "note": f"analyst skipped: {why}", "provider": "budget"}
    try:
        if provider == "jev":
            verdict = _advise_jev(cfg, coin, price, signal, position)
        else:
            verdict = _advise_chat(cfg, provider, coin, price, signal, position)
    except Exception as e:  # analyst failure must never break the trading loop
        verdict = {"bias": "flat", "confidence": 0.0, "note": f"analyst error: {e}"}
    _budget_record(journal, verdict.get("input_tokens", est_tokens))
    verdict["provider"] = provider
    return verdict


def _advise_jev(cfg, coin, price, signal, position):
    key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("TYPESAFE_AI_API_KEY")
    a = cfg["analyst"]
    state = json.dumps({
        "coin": coin, "price": round(price, 4), "timeframe": cfg["timeframe"],
        "rule_signal": signal["action"], "rule_reason": signal["reason"],
        "position": (None if not position else {
            "qty": round(position["qty"], 8), "avg_price": round(position["avg_price"], 4)}),
        "ema_fast": signal.get("ema_fast"), "ema_slow": signal.get("ema_slow"),
        "rsi": signal.get("rsi"), "vol_ratio": signal.get("vol_ratio"),
    })
    r = requests.post(JEV_URL, timeout=30, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
    }, json={
        "model": a.get("model") or "jev-latest",
        "state": state,
        "questions": {
            "enter": {
                "type": "choice",
                "instructions": ("A rule engine produced an entry signal on a "
                                 "small account with fees. Should it proceed?"),
                "criteria": {
                    "proceed": "Evidence supports entering now",
                    "skip": "Weak, choppy, or overextended; skip",
                },
            },
            "trend_continues": {
                "type": "noul",
                "instructions": ("The up-trend is likely to persist over the "
                                 "next several candles"),
            },
        },
    })
    r.raise_for_status()
    data = r.json()
    usage = (data.get("usage") or {}).get("input_tokens", 0)
    enter = data["choices"]["enter"]
    noul = data["nouls"]["trend_continues"]
    bias = "long" if enter["choice"] == "proceed" else "flat"
    note = (f"jev choice={enter['choice']} "
            f"conf={enter.get('confidence', 0):.2f} "
            f"trend_noul={noul:.2f}")
    return {"bias": bias, "confidence": float(enter.get("confidence", 0.0)),
            "note": note, "input_tokens": usage}


def _advise_chat(cfg, provider, coin, price, signal, position):
    env, url, default_model = CHAT_ENDPOINTS[provider]
    key = os.environ[env]
    a = cfg["analyst"]
    prompt = CHAT_PROMPT.format(
        coin=coin, timeframe=cfg["timeframe"], price=price,
        action=signal["action"], reason=signal["reason"],
        position=(f"{position['qty']:.6f} @ {position['avg_price']:.2f}"
                  if position else "none"),
        ema_fast=signal.get("ema_fast") or 0.0,
        ema_slow=signal.get("ema_slow") or 0.0,
        rsi=signal.get("rsi") or 0.0,
        vol_ratio=signal.get("vol_ratio") or 1.0,
    )
    r = requests.post(url, timeout=30, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
    }, json={
        "model": a.get("model") or default_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 200,
    })
    r.raise_for_status()
    data = r.json()
    usage = (data.get("usage") or {}).get("prompt_tokens", len(prompt) // 4)
    content = data["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", content, re.S)
    out = json.loads(m.group(0))
    return {"bias": out.get("bias", "flat"),
            "confidence": float(out.get("confidence", 0.0)),
            "note": out.get("note", ""), "input_tokens": usage}


def agrees(verdict, signal):
    """For gate mode: entry allowed only when the analyst leans the same way."""
    if not verdict:
        return False
    return signal["action"] == "enter" and verdict["bias"] == "long" \
        and verdict["confidence"] >= 0.5
