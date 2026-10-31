"""Seamless MetaMask connection: one click + one signature.

How it works (the security model, in order):
  1. the bot generates a FRESH agent keypair locally (trade-only)
  2. a localhost page asks MetaMask for one EIP-712 signature:
     HyperliquidTransaction:ApproveAgent -- the user's key NEVER leaves
     MetaMask; the bot only receives the SIGNATURE of the approval
  3. the bot posts the approval to Hyperliquid /exchange, then saves the
     agent key as DARKHORSE_TESTNET_KEY (env var) and enables the venue

The agent key can sign orders but cannot withdraw. The master key stays in
MetaMask forever. If testnet is unreachable from this network, the agent key
is still saved (pending approval) -- rerun on a reachable network.
"""

import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import requests

from .utils_urls import MAINNET_URL, TESTNET_URL

PAGE_HOST, PAGE_PORT = "127.0.0.1", 8766

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Darkhorse -- connect MetaMask</title>
<style>
 body{background:#0d1117;color:#c9d1d9;font-family:Consolas,monospace;
      display:flex;min-height:100vh;align-items:center;justify-content:center}
 .box{max-width:560px;background:#161b22;border:1px solid #21262d;
      border-radius:10px;padding:28px}
 h1{font-size:18px;color:#58a6ff;margin:0 0 8px}
 button{background:#1f6feb;color:#fff;border:0;border-radius:8px;
        padding:12px 22px;font-size:15px;margin:8px 6px 0 0;cursor:pointer}
 button.gray{background:#30363d}
 .small{color:#8b949e;font-size:12px;line-height:1.5}
 #status{margin-top:14px;font-size:14px}
 .ok{color:#3fb950} .bad{color:#f85149}
</style></head>
<body><div class="box">
<h1>Connect MetaMask to Darkhorse</h1>
<p class="small">This creates a <b>trade-only agent wallet</b> for
Hyperliquid TESTNET (mock money). Your MetaMask key never leaves MetaMask --
you only sign an approval. The agent cannot withdraw. Nothing is sent
anywhere except Hyperliquid's own testnet API.</p>
<p>step 1: connect your wallet &nbsp; step 2: approve the agent (one free signature)</p>
<button id="connect">1. Connect MetaMask</button>
<button id="sign" class="gray">2. Approve agent (sign)</button>
<p>wallet: <span id="addr" class="small">not connected</span></p>
<div id="status" class="small"></div>
</div>
<script>
const TD = __TYPED_DATA__;
let addr = null;
document.getElementById("connect").onclick = async () => {
  try {
    const accs = await ethereum.request({method: "eth_requestAccounts"});
    addr = accs[0];
    document.getElementById("addr").textContent =
      addr + "  (master wallet -- stays in MetaMask)";
  } catch (e) { document.getElementById("status").textContent =
      "connect failed: " + e.message; }
};
document.getElementById("sign").onclick = async () => {
  if (!addr) { document.getElementById("status").textContent =
      "click step 1 first"; return; }
  try {
    document.getElementById("status").textContent = "waiting for MetaMask...";
    const sig = await ethereum.request({
      method: "eth_signTypedData_v4",
      params: [addr, JSON.stringify(TD)]});
    document.getElementById("status").textContent =
      "signature received -- registering agent...";
    const r = await fetch("/approve", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({signature: sig, address: addr})});
    const t = await r.text();
    document.getElementById("status").innerHTML =
      '<span class="ok">' + t + "</span>";
  } catch (e) { document.getElementById("status").innerHTML =
      '<span class="bad">' + (e.message || "signing failed") + "</span>"; }
};
</script></body></html>"""


def _typed_data(agent_address, hl_chain, chain_id):
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
            ],
            "HyperliquidTransaction:ApproveAgent": [
                {"name": "hyperliquidChain", "type": "string"},
                {"name": "agentAddress", "type": "address"},
                {"name": "agentName", "type": "string"},
                {"name": "nonce", "type": "uint256"},
            ],
        },
        "primaryType": "HyperliquidTransaction:ApproveAgent",
        "domain": {"name": "HyperliquidSignTransaction",
                   "version": "1", "chainId": chain_id},
        "message": {"hyperliquidChain": hl_chain,
                    "agentAddress": agent_address,
                    "agentName": "dh", "nonce": int(time.time() * 1000)},
    }


def _split_sig(sig_hex):
    sig = sig_hex[2:] if sig_hex.startswith("0x") else sig_hex
    r, s, v = sig[:64], sig[64:128], sig[128:130]
    v = int(v, 16)
    if v < 27:
        v += 27
    return {"r": "0x" + r, "s": "0x" + s, "v": v}


def _register_agent(base_url, agent_address, sig_hex, hl_chain, nonce):
    """Post the approveAgent action. Returns (ok, detail)."""
    rsv = _split_sig(sig_hex)
    payload = {
        "action": {"type": "approveAgent", "hyperliquidChain": hl_chain,
                   "agentAddress": agent_address, "agentName": "dh",
                   "nonce": nonce},
        "nonce": nonce,
        "signature": rsv,
    }
    try:
        r = requests.post(base_url + "/exchange", json=payload, timeout=15)
        if r.status_code == 200 and r.json().get("status") == "ok":
            return True, "agent approved by Hyperliquid"
        return False, f"exchange responded: {r.status_code} {r.text[:160]}"
    except requests.exceptions.SSLError:
        return False, ("testnet is UNREACHABLE from this network (filtered) -- "
                       "agent key saved as pending; rerun `darkhorse connect` "
                       "on a reachable network (e.g. phone hotspot) to "
                       "register it")
    except Exception as e:
        return False, f"registration failed: {e.__class__.__name__}: {e}"


def run_connect(cfg, args):
    """`darkhorse connect`: local page -> MetaMask signature -> registration."""
    from eth_account import Account
    agent = Account.create()
    agent_key = agent.key.hex()
    if not agent_key.startswith("0x"):
        agent_key = "0x" + agent_key
    is_mainnet = bool(cfg.get("live", {}).get("enabled"))
    hl_chain = "Mainnet" if is_mainnet else "Testnet"
    chain_id = 42161 if is_mainnet else 1337
    td = _typed_data(agent.address, hl_chain, chain_id)
    result = {"approved": False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if urlparse(self.path).path == "/":
                body = PAGE.replace("__TYPED_DATA__", json.dumps(td)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if urlparse(self.path).path != "/approve":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            base = MAINNET_URL if is_mainnet else TESTNET_URL
            ok, detail = _register_agent(
                base, agent.address, body.get("signature", ""), hl_chain,
                td["message"]["nonce"])
            if ok:
                result["approved"] = True
                _save_key(cfg, agent_key)
            text = ("DARKHORSE CONNECTED -- agent saved, venue enabled. "
                    "You can close this tab. Run testnet.bat / start_darkhorse.bat."
                    if ok else "NOT REGISTERED: " + detail)
            body2 = text.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body2)))
            self.end_headers()
            self.wfile.write(body2)

    from .utils_urls import MAINNET_URL
    url = f"http://{PAGE_HOST}:{PAGE_PORT}"
    print("MetaMask connect page:", url)
    print("(the bot generated a fresh trade-only agent key locally; your")
    print(" MetaMask key never leaves MetaMask. Ctrl-C to cancel.)")
    if args and getattr(args, "no_browser", False) is False:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    server = ThreadingHTTPServer((PAGE_HOST, PAGE_PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        while not result["approved"]:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    server.shutdown()
    if result["approved"]:
        print("\nConnected. Testnet trading is enabled in config.json.")
        print("Start with: start_darkhorse.bat  (or: darkhorse testnet)")


def _save_key(cfg, agent_key):
    import subprocess
    name = ("HYPERLIQUID_MAINNET_KEY" if cfg.get("live", {}).get("enabled")
            else "DARKHORSE_TESTNET_KEY")
    subprocess.run(["setx", name, agent_key], capture_output=True, check=True)
    os.environ[name] = agent_key
    cfgp = json.load(open("config.json", encoding="utf-8"))
    vkey = ("mainnet" if cfg.get("live", {}).get("enabled")
            else "hyperliquid_testnet")
    cfgp.setdefault("venues", {}).setdefault(vkey, {})["enabled"] = True
    json.dump(cfgp, open("config.json", "w", encoding="utf-8"), indent=2)
    print(f"agent key saved as {name}; venue enabled in config.json")
