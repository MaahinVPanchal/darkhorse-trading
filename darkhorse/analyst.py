"""Decision-layer providers -- provider-agnostic by design.

Two families:

DECISION APIs (typed answers, no text parsing -- ideal for the veto gate):
  - jev              TypeSafe "System One"  POST /v1/systemone
                     ~$0.042/M input tokens, output free
  - openai-decisions OpenAI Decisions API   POST /v1/decisions (gpt-6-luna)
                     $0.10/M input tokens, output free, public beta

CHAT APIs (OpenAI-compatible unless noted):
  nebius, openai, anthropic (native /v1/messages), gemini, deepseek, groq,
  mistral, together, xai, openrouter, zai, ollama (local), and a fully
  generic "custom" provider (ANALYST_BASE_URL/ANALYST_API_KEY/ANALYST_MODEL)
  that covers any other OpenAI-compatible service.

Ground rules (unchanged, provider-independent):
  - The LLM NEVER executes trades. mode 'log' annotates; mode 'gate' may only
    veto an entry the rule engine already produced. It cannot raise size,
    leverage, trade count, or move a stop -- the risk engine bounds all of it.
  - A hard daily budget (calls + input tokens, persisted in the journal) makes
    any credit last: when the cap trips, the bot falls back to rules-only.
"""

import json
import os
import re
from datetime import datetime, timezone

import requests

JEV_URL = "https://api.typesafe.ai/v1/systemone"
OPENAI_DECISIONS_URL = "https://api.openai.com/v1/decisions"

# provider -> (env key(s), default model)
DECISION_ENDPOINTS = {
    "jev": (("TYPESAFE_API_KEY", "TYPESAFE_AI_API_KEY"), "jev-latest"),
    "openai-decisions": (("OPENAI_API_KEY",), "gpt-6-luna"),
}

CHAT_ENDPOINTS = {
    "nebius": ("NEBIUS_API_KEY", "https://api.studio.nebius.ai/v1/chat/completions",
               "meta-llama/Llama-3.3-70B-Instruct"),
    "openai": ("OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions",
               "gpt-4o-mini"),
    "anthropic": ("ANTHROPIC_API_KEY", "https://api.anthropic.com/v1/messages",
                  "claude-sonnet-4-5"),
    "gemini": ("GEMINI_API_KEY",
               "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
               "gemini-2.5-flash"),
    "deepseek": ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1/chat/completions",
                 "deepseek-chat"),
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions",
             "llama-3.3-70b-versatile"),
    "mistral": ("MISTRAL_API_KEY", "https://api.mistral.ai/v1/chat/completions",
                "mistral-large-latest"),
    "together": ("TOGETHER_API_KEY", "https://api.together.xyz/v1/chat/completions",
                 "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    "xai": ("XAI_API_KEY", "https://api.x.ai/v1/chat/completions", "grok-4-fast"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions",
                   "openai/gpt-4o-mini"),
    "zai": ("ZAI_API_KEY", "https://api.z.ai/api/paas/v4/chat/completions", "glm-4.6"),
    "ollama": (None, "http://localhost:11434/v1/chat/completions", "llama3.1"),
    "custom": (("ANALYST_API_KEY",), None, None),  # ANALYST_BASE_URL + ANALYST_MODEL
}
PROVIDER_ORDER = ["jev", "openai-decisions", "nebius", "openai", "anthropic",
                  "gemini", "deepseek", "groq", "mistral", "together",
                  "xai", "openrouter", "zai", "ollama", "custom"]

ALL_KEY_ENVS = ["TYPESAFE_API_KEY", "TYPESAFE_AI_API_KEY", "NEBIUS_API_KEY",
                "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
                "DEEPSEEK_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY",
                "TOGETHER_API_KEY", "XAI_API_KEY", "OPENROUTER_API_KEY",
                "ZAI_API_KEY", "ANALYST_API_KEY"]

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
    for prov in order:
        if prov in DECISION_ENDPOINTS:
            envs, _ = DECISION_ENDPOINTS[prov]
            if any(os.environ.get(e) for e in envs):
                return prov
        elif prov == "ollama":
            if os.environ.get("OLLAMA_ENABLED") == "1":
                return prov
        elif prov == "custom":
            if os.environ.get("ANALYST_BASE_URL") and os.environ.get("ANALYST_API_KEY"):
                return prov
        elif prov in CHAT_ENDPOINTS:
            env = CHAT_ENDPOINTS[prov][0]
            if env and os.environ.get(env):
                return prov
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
        if provider in DECISION_ENDPOINTS:
            verdict = _advise_decision(cfg, provider, coin, price, signal, position)
        else:
            verdict = _advise_chat(cfg, provider, coin, price, signal, position)
    except Exception as e:  # analyst failure must never break the trading loop
        verdict = {"bias": "flat", "confidence": 0.0, "note": f"analyst error: {e}"}
    _budget_record(journal, verdict.get("input_tokens", est_tokens))
    verdict["provider"] = provider
    return verdict


def _decision_state(cfg, coin, price, signal, position):
    return json.dumps({
        "coin": coin, "price": round(price, 4), "timeframe": cfg["timeframe"],
        "rule_signal": signal["action"], "rule_reason": signal["reason"],
        "position": (None if not position else {
            "qty": round(position["qty"], 8),
            "avg_price": round(position["avg_price"], 4)}),
        "ema_fast": signal.get("ema_fast"), "ema_slow": signal.get("ema_slow"),
        "rsi": signal.get("rsi"), "vol_ratio": signal.get("vol_ratio"),
    })


def _advise_decision(cfg, provider, coin, price, signal, position):
    """Typed decision APIs. Jev: native systemone. OpenAI: /v1/decisions."""
    a = cfg["analyst"]
    state = _decision_state(cfg, coin, price, signal, position)
    if provider == "jev":
        envs, default_model = DECISION_ENDPOINTS[provider]
        key = next(os.environ[e] for e in envs if os.environ.get(e))
        r = requests.post(JEV_URL, timeout=30, headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        }, json={
            "model": a.get("model") or default_model,
            "state": state,
            "questions": {
                "enter": {"type": "choice",
                          "instructions": ("A rule engine produced an entry "
                                           "signal on a small account with "
                                           "fees. Should it proceed?"),
                          "criteria": {
                              "proceed": "Evidence supports entering now",
                              "skip": "Weak, choppy, or overextended; skip"}},
                "trend_continues": {"type": "noul",
                                    "instructions": ("The up-trend is likely "
                                                     "to persist over the next "
                                                     "several candles")},
            }})
        r.raise_for_status()
        data = r.json()
        usage = (data.get("usage") or {}).get("input_tokens", 0)
        enter = data["choices"]["enter"]
        noul = data["nouls"]["trend_continues"]
        bias = "long" if enter["choice"] == "proceed" else "flat"
        note = (f"jev choice={enter['choice']} "
                f"conf={enter.get('confidence', 0):.2f} trend_noul={noul:.2f}")
        return {"bias": bias, "confidence": float(enter.get("confidence", 0.0)),
                "note": note, "input_tokens": usage}

    # openai-decisions
    _, default_model = DECISION_ENDPOINTS[provider]
    key = os.environ["OPENAI_API_KEY"]
    r = requests.post(OPENAI_DECISIONS_URL, timeout=30, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
    }, json={
        "model": a.get("model") or default_model,
        "input": [{"role": "user",
                   "content": [{"type": "input_text", "text": state}]}],
        "questions": [
            {"type": "choice", "name": "enter",
             "instructions": ("A rule engine produced an entry signal on a "
                              "small account with fees. Should it proceed?"),
             "choices": [
                 {"value": "proceed",
                  "description": "Evidence supports entering now"},
                 {"value": "skip",
                  "description": "Weak, choppy, or overextended; skip"},
                 {"value": "other", "description": "Uncertain"}]},
            {"type": "predicate", "name": "trend_continues",
             "instructions": ("The up-trend is likely to persist over the "
                              "next several candles")},
        ]})
    r.raise_for_status()
    data = r.json()
    usage = (data.get("usage") or {}).get("input_tokens", 0)
    answers = {a2.get("name"): a2 for a2 in data.get("answers", [])}
    enter = answers.get("enter", {})
    trend = answers.get("trend_continues", {})
    if enter.get("type") == "refusal":
        return {"bias": "flat", "confidence": 0.0,
                "note": "openai-decisions refused", "input_tokens": usage}
    choice = enter.get("choice", "skip")
    bias = "long" if choice == "proceed" else "flat"
    conf = float(enter.get("confidence", 0.0))
    note = (f"openai-decisions choice={choice} conf={conf:.2f} "
            f"trend_p={float(trend.get('probability', 0)):.2f}")
    return {"bias": bias, "confidence": conf, "note": note,
            "input_tokens": usage}


def _advise_chat(cfg, provider, coin, price, signal, position):
    """OpenAI-compatible chat providers + native Anthropic + local Ollama."""
    env, url, default_model = CHAT_ENDPOINTS[provider]
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
    if provider == "anthropic":
        key = os.environ[env]
        r = requests.post(url, timeout=30, headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }, json={
            "model": cfg["analyst"].get("model") or default_model,
            "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}],
        })
        r.raise_for_status()
        data = r.json()
        usage = (data.get("usage") or {}).get("input_tokens", len(prompt) // 4)
        content = data["content"][0]["text"]
    else:
        if provider == "ollama":
            key = "ollama"
        elif provider == "custom":
            url = os.environ["ANALYST_BASE_URL"].rstrip("/") + "/chat/completions"
            key = os.environ["ANALYST_API_KEY"]
            default_model = os.environ.get("ANALYST_MODEL", "gpt-4o-mini")
        else:
            key = os.environ[env]
        r = requests.post(url, timeout=30, headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        }, json={
            "model": cfg["analyst"].get("model") or default_model,
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


def test_provider(cfg, journal):
    """One real call to the resolved provider. Verifies key, endpoint, and
    budget accounting end to end. Counts against the daily budget like any
    other call. Bypasses the enabled flag -- that's the point of the test."""
    cfg = {**cfg, "analyst": {**cfg["analyst"], "enabled": True}}
    provider = available(cfg)
    if not provider:
        return {"ok": False,
                "error": ("no provider key found in environment. Set ONE of: "
                          + ", ".join(ALL_KEY_ENVS)
                          + " (e.g. setx TYPESAFE_API_KEY \"...\"), or "
                            "ANALYST_BASE_URL+ANALYST_API_KEY+ANALYST_MODEL "
                            "for any custom OpenAI-compatible endpoint, then "
                            "open a NEW terminal")}
    signal = {"action": "enter", "reason": "analyst self-test",
              "ema_fast": 100.0, "ema_slow": 99.0, "rsi": 55.0,
              "vol_ratio": 1.2}
    verdict = advise(cfg, journal, "BTC", 80000.0, signal, None)
    if verdict is None:
        return {"ok": False, "error": "advise() returned None unexpectedly"}
    note = verdict.get("note", "")
    if note.startswith("analyst error"):
        return {"ok": False, "provider": provider,
                "error": f"{provider} call failed: {note}"}
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {"ok": True, "provider": provider, "bias": verdict["bias"],
            "confidence": verdict["confidence"], "note": note,
            "input_tokens": verdict.get("input_tokens"),
            "calls_today": journal.get_state(f"analyst_calls_{day}", "0"),
            "tokens_today": journal.get_state(f"analyst_tokens_{day}", "0")}
