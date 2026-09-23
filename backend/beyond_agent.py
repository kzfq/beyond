
"""
Beyond — PC-side relay agent.

This is the "hosted from your PC" half of the remote control panel. It runs on
YOUR machine, right next to the real selfbot, and connects OUTBOUND to the
relay running on selfbot.fyi. That relay serves the web panel at
https://selfbot.fyi/session and shuttles messages between your browser and this
agent. Because the panel is served from the UI bundle THIS agent pushes, the
page lives and dies with your PC: close this and /session goes offline.

It reuses beyond_backend unchanged — same selfbot, same cogs, same command
handler. The only swap is transport: instead of Electron's stdin/stdout, events
and commands travel over the relay WebSocket.

    viewer(browser) <-> relay(selfbot.fyi) <-> THIS agent(PC) <-> Discord

Multi-tenant: every install gets its OWN unguessable link + password.
  - On first run the app generates a 256-bit `agent_secret` (its identity) and a
    strong `viewer_password`, then enrolls with the relay, which returns a random
    `slug`. All three are saved locally (agent_config.json) so the link and
    password stay the SAME across restarts. The app prints the shareable link +
    password on every start.
  - The relay stores only Argon2id/scrypt HASHES of the password and secret,
    never plaintext. The slug is a capability: the URL is https://<host>/p/<slug>.

Wire protocol (matches the relay contract):
    HTTPS POST {relay_base}/enroll  {enroll_key, agent_secret, password}
                                    -> {slug}                (first run only)
    agent WS  {relay_base_ws}/agent/ws
        headers: X-Beyond-Slug: <slug>, Authorization: Bearer <agent_secret>
        agent -> relay : {"t":"ui_bundle","files":{...}}  (once, on connect)
                         {"t":"event","data":{...}}
                         {"t":"pong"}
        relay -> agent : {"t":"cmd","data":{...}}
                         {"t":"ping"}

Config (backend/agent_config.json; env overrides where noted):
    relay_base      https base for agent traffic  (default https://agent.selfbot.fyi)
    viewer_base     public base users open         (default https://selfbot.fyi)
    enroll_key      shared enrollment key from the relay setup (BEYOND_ENROLL_KEY)
    slug/agent_secret/viewer_password  filled in automatically after first enroll
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
import traceback

import aiohttp

import beyond_backend as bb

HERE = os.path.dirname(os.path.abspath(__file__))
RENDERER = os.path.join(HERE, "..", "renderer")
CFG_PATH = os.path.join(HERE, "agent_config.json")

DEFAULT_RELAY_BASE = "https://agent.selfbot.fyi"
DEFAULT_VIEWER_BASE = "https://selfbot.fyi"

_QUEUE: "asyncio.Queue[dict]" = None
_LOOP: asyncio.AbstractEventLoop = None
_CUR_WS = None

def _agent_emit(obj: dict) -> None:
    """Replacement for beyond_backend.emit — thread/loop-safe enqueue."""
    try:
        if _LOOP is not None and _LOOP.is_running():
            _LOOP.call_soon_threadsafe(_QUEUE.put_nowait, obj)
    except Exception:
        pass

def _local_log(msg: str) -> None:
    """Agent's own diagnostics go to stderr (never the relay protocol)."""
    try:
        sys.stderr.write(f"[beyond-agent] {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass

def load_cfg() -> dict:
    cfg = {
        "relay_base": "", "viewer_base": "", "enroll_key": "",
        "slug": "", "agent_secret": "", "viewer_password": "",
    }
    if os.path.exists(CFG_PATH):
        try:
            with open(CFG_PATH, "r", encoding="utf-8") as f:
                j = json.load(f)
            for k in cfg:
                if j.get(k):
                    cfg[k] = str(j[k]).strip()
        except Exception as e:
            _local_log(f"could not read agent_config.json: {e}")

    cfg["relay_base"] = (os.environ.get("BEYOND_RELAY_BASE", "").strip() or cfg["relay_base"] or DEFAULT_RELAY_BASE)
    cfg["viewer_base"] = (os.environ.get("BEYOND_VIEWER_BASE", "").strip() or cfg["viewer_base"] or DEFAULT_VIEWER_BASE)
    cfg["enroll_key"] = os.environ.get("BEYOND_ENROLL_KEY", "").strip() or cfg["enroll_key"]
    cfg["relay_base"] = cfg["relay_base"].rstrip("/")
    cfg["viewer_base"] = cfg["viewer_base"].rstrip("/")
    return cfg

def save_cfg(cfg: dict) -> None:
    """Persist config with owner-only perms (contains this install's secrets)."""
    keep = ("relay_base", "viewer_base", "enroll_key",
            "slug", "agent_secret", "viewer_password")
    data = {k: cfg.get(k, "") for k in keep}
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        try:
            os.chmod(CFG_PATH, 0o600)
        except Exception:
            pass
    except Exception as e:
        _local_log(f"could not save agent_config.json: {e}")

def _gen_password() -> str:
    """A strong, human-copyable password: 4 groups of 4 url-safe chars."""
    alpha = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    groups = ["".join(secrets.choice(alpha) for _ in range(4)) for _ in range(4)]
    return "-".join(groups)

def _agent_ws_url(cfg: dict) -> str:
    base = cfg["relay_base"]
    ws = "wss://" + base.split("://", 1)[-1] if base.startswith("https://") else "ws://" + base.split("://", 1)[-1]
    return ws + "/agent/ws"

async def ensure_enrolled(cfg: dict, session: "aiohttp.ClientSession") -> bool:
    """First run: generate this install's identity + password and register with
    the relay to obtain a slug. Returns True when the tenant is ready."""
    if cfg.get("slug") and cfg.get("agent_secret"):
        return True

    if not cfg.get("enroll_key"):
        _local_log("ERROR: no enroll_key set. Put the relay's BEYOND_ENROLL_KEY "
                   "into backend/agent_config.json (\"enroll_key\") to register this install.")
        return False

    agent_secret = cfg.get("agent_secret") or secrets.token_urlsafe(32)
    password = cfg.get("viewer_password") or _gen_password()

    url = cfg["relay_base"] + "/enroll"
    _local_log(f"first run — enrolling with {url} …")
    try:
        async with session.post(url, json={
            "enroll_key": cfg["enroll_key"],
            "agent_secret": agent_secret,
            "password": password,
        }, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            body = await resp.text()
            if resp.status != 200:
                _local_log(f"enrollment failed (HTTP {resp.status}): {body[:200]}")
                return False
            data = json.loads(body)
            slug = str(data.get("slug", "")).strip()
            if not slug:
                _local_log("enrollment response had no slug")
                return False
    except Exception as e:
        _local_log(f"enrollment error: {e}")
        return False

    cfg["slug"] = slug
    cfg["agent_secret"] = agent_secret
    cfg["viewer_password"] = password
    save_cfg(cfg)
    _local_log("enrolled successfully")
    return True

def _print_panel_info(cfg: dict) -> None:
    url = f"{cfg['viewer_base']}/p/{cfg['slug']}"
    line = "=" * 56
    _local_log("\n" + line +
               f"\n  Your Beyond panel:\n    Link:     {url}"
               f"\n    Password: {cfg['viewer_password']}"
               "\n  Share these with nobody you don't trust — they are full"
               "\n  control of this account. Keep this window running.\n" + line)

def build_ui_bundle() -> dict:
    """Produce a fully SELF-CONTAINED web index.html.

    The page is served at /session (no trailing slash), so relative asset
    references like href="styles.css" would resolve to /styles.css and 404.
    To avoid depending on how the relay routes assets or what MIME type it
    sends (nosniff will reject a wrong type), we inline styles.css and app.js
    straight into the HTML, plus the browser shim before app.js. Result: the
    relay only has to serve one file (index.html) at /session.
    """
    import re

    def _read(name: str) -> str:
        with open(os.path.join(RENDERER, name), "r", encoding="utf-8") as f:
            return f.read()

    index = _read("index.html")
    app_js = _read("app.js")
    styles = _read("styles.css")
    shim = _read("web-shim.js")

    style_block = "<style>\n" + styles + "\n</style>"
    new_index, n = re.subn(
        r"<link[^>]*href=[\"']styles\.css[\"'][^>]*>", lambda m: style_block, index, count=1
    )
    index = new_index if n else index.replace("</head>", style_block + "\n</head>", 1)

    script_block = "<script>\n" + shim + "\n</script>\n<script>\n" + app_js + "\n</script>"
    new_index, n = re.subn(
        r"<script[^>]*src=[\"']app\.js[\"'][^>]*>\s*</script>", lambda m: script_block, index, count=1
    )
    index = new_index if n else index.replace("</body>", script_block + "\n</body>", 1)

    return {"index.html": index, "app.js": app_js, "styles.css": styles}

async def _sender():
    """Drain the event queue into the current relay WS (drop while offline —
    a reconnecting viewer is re-hydrated by the relay's refresh)."""
    while True:
        obj = await _QUEUE.get()
        ws = _CUR_WS
        if ws is None or ws.closed:
            continue
        try:
            await ws.send_str(json.dumps({"t": "event", "data": obj}))
        except Exception:
            pass

async def _handle_cmd(data: dict, state: dict):
    try:
        await bb.handle(data, state)
    except Exception as e:
        _agent_emit({"type": "log", "msg": f"handler error: {e}"})
        _local_log("handler error:\n" + traceback.format_exc())

async def run_once(cfg: dict, session: "aiohttp.ClientSession", state: dict) -> None:
    global _CUR_WS
    headers = {
        "X-Beyond-Slug": cfg["slug"],
        "Authorization": f"Bearer {cfg['agent_secret']}",
    }
    ws_url = _agent_ws_url(cfg)
    _local_log(f"connecting to {ws_url} (slug {cfg['slug']}) …")
    async with session.ws_connect(
        ws_url, headers=headers, heartbeat=None, max_msg_size=0
    ) as ws:
        _CUR_WS = ws
        _local_log("connected — sending UI bundle")
        try:
            await ws.send_str(json.dumps({"t": "ui_bundle", "files": build_ui_bundle()}))
        except Exception as e:
            _local_log(f"failed to send ui_bundle: {e}")

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    frame = json.loads(msg.data)
                except Exception:
                    continue
                t = frame.get("t")
                if t == "ping":
                    try:
                        await ws.send_str(json.dumps({"t": "pong"}))
                    except Exception:
                        pass
                elif t == "cmd":
                    data = frame.get("data") or {}
                    if isinstance(data, dict) and data.get("cmd"):

                        asyncio.create_task(_handle_cmd(data, state))
            elif msg.type in (aiohttp.WSMsgType.CLOSED,
                              aiohttp.WSMsgType.CLOSING,
                              aiohttp.WSMsgType.ERROR):
                break
    _CUR_WS = None

async def main():
    global _QUEUE, _LOOP
    _LOOP = asyncio.get_event_loop()
    _QUEUE = asyncio.Queue()

    bb.emit = _agent_emit

    cfg = load_cfg()
    state: dict = {}
    asyncio.create_task(_sender())

    timeout = aiohttp.ClientTimeout(total=None, sock_connect=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:

        while not await ensure_enrolled(cfg, session):
            _local_log("enrollment not complete — retrying in 30s")
            await asyncio.sleep(30)

        _print_panel_info(cfg)

        backoff = 1.0
        while True:
            try:

                _agent_emit({"type": "panel_info",
                             "url": f"{cfg['viewer_base']}/p/{cfg['slug']}",
                             "password": cfg["viewer_password"]})
                await run_once(cfg, session, state)
                _local_log("relay connection closed — reconnecting")
                backoff = 1.0
            except aiohttp.ClientResponseError as e:
                hdrs = getattr(e, "headers", None) or {}
                server = str(hdrs.get("Server", "")).lower()
                cf = hdrs.get("cf-mitigated") or ("cloudflare" in server)
                if e.status == 403 and cf:
                    _local_log(
                        "Cloudflare is BLOCKING this agent with a bot challenge "
                        "(HTTP 403, cf-mitigated). Point relay_base at a DNS-only "
                        "(grey-cloud) host like https://agent.selfbot.fyi."
                    )
                    backoff = 30.0
                elif e.status in (401, 403):
                    _local_log(f"relay rejected this agent (HTTP {e.status}) — the "
                               "slug/agent_secret don't match the relay's record. If you "
                               "reset the relay, delete backend/agent_config.json to re-enroll.")
                    backoff = min(backoff * 2, 30.0)
                else:
                    _local_log(f"relay handshake failed (HTTP {e.status})")
                    backoff = min(backoff * 2, 30.0)
            except Exception as e:
                _local_log(f"relay connection error: {e}")
                backoff = min(backoff * 2, 30.0)
            await asyncio.sleep(backoff)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
