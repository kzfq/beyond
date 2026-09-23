from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import urllib.request as _ur
import uuid
import zlib
from typing import Optional

from modifyself.commands.cog import Cog, listener
from modifyself.commands.core import command
from modifyself.http.route import Route

from ascii_helper import ASCIIMixin, asend
import persistence

_KEEPALIVE_INTERVAL = 25 * 60
_DEFAULT_ROTATE_INTERVAL = 20
_ASSET_CHANNEL_ID = "1477758738772525239"

_CDN_PAT = r"https?://(?:cdn\.discordapp\.com|media\.discordapp\.net)/attachments/(\d+)/(\d+)/(.+)"

_ROTATABLE_FIELDS = [
    "text", "state", "details", "name", "song", "artist", "album",
    "video_title", "channel_name", "anime_title", "episode_title",
    "game_name", "large_text", "small_text",
]

_RPC_TYPES = [
    "custom_status", "playing", "watching", "listening", "streaming",
    "competing", "spotify", "youtube", "xbox", "playstation",
    "crunchyroll", "vrchat", "custom", "clear",
]

_PLATFORM_PROPS: dict[str, dict] = {
    "desktop": {
        "os": "Windows", "browser": "Discord Client", "device": "",
        "system_locale": "en-US",
        "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "browser_version": "124.0.0.0", "os_version": "10",
        "referrer": "", "referring_domain": "",
    },
    "web": {
        "os": "Windows", "browser": "Discord Web", "device": "",
        "system_locale": "en-US",
        "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "browser_version": "124.0.0.0", "os_version": "10",
        "referrer": "", "referring_domain": "",
    },
    "phone": {
        "os": "iOS", "browser": "Discord iOS", "device": "iPhone16,2",
        "system_locale": "en-US",
        "browser_user_agent": "Discord/268.0 CFNetwork/1474 Darwin/23.0.0",
        "browser_version": "268.0", "os_version": "17.4.1",
        "referrer": "", "referring_domain": "",
    },
    "android": {
        "os": "Android", "browser": "Discord Android", "device": "Pixel 8",
        "system_locale": "en-US",
        "browser_user_agent": "Discord-Android/214116;ROM:13;Device:Pixel 8",
        "browser_version": "214.116", "os_version": "13",
        "referrer": "", "referring_domain": "",
    },
    "xbox": {
        "os": "Console", "browser": "Discord Embedded", "device": "Xbox Series X",
        "system_locale": "en-US",
        "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Xbox; Xbox Series X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/46.0.2486.0 Safari/537.36 Edge/13.10586",
        "browser_version": "", "os_version": "",
        "referrer": "", "referring_domain": "",
    },
    "console": {
        "os": "Console", "browser": "Discord Embedded", "device": "PlayStation 5",
        "system_locale": "en-US",
        "browser_user_agent": "Mozilla/5.0 (PlayStation 5 3.11) AppleWebKit/605.1.15 (KHTML, like Gecko)",
        "browser_version": "", "os_version": "",
        "referrer": "", "referring_domain": "",
    },
    "vr": {
        "os": "Console", "browser": "Discord VR", "device": "VR-Headset",
        "system_locale": "en-US",
        "browser_user_agent": "DiscordVR/12.45",
        "browser_version": "23.7.91", "os_version": "10.0.45",
        "referrer": "", "referring_domain": "",
    },
    "off": {
        "os": "Windows", "browser": "Chrome", "device": "",
        "system_locale": "en-US",
        "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "browser_version": "124.0.0.0", "os_version": "10",
        "referrer": "", "referring_domain": "",
    },
}

# ── main-gateway platform spoof ──────────────────────────────────────────────
# modifyself's GatewayWebSocket hardcodes Windows/Chrome properties in
# _identify() and uses __slots__, so per-instance attribute patching is
# impossible (AttributeError). We class-patch _identify ONCE with a version
# that builds the payload from the active platform. "off" → original payload.
_ACTIVE_PLATFORM: dict = {"key": "off"}


def set_active_platform(key: str) -> None:
    _ACTIVE_PLATFORM["key"] = key if key in _PLATFORM_PROPS else "off"


def get_active_platform() -> str:
    return _ACTIVE_PLATFORM["key"]


def install_platform_patch() -> None:
    from modifyself.gateway.websocket import GatewayWebSocket

    if getattr(GatewayWebSocket, "_platform_patched", False):
        return

    _orig_identify = GatewayWebSocket._identify

    async def _identify(self) -> None:
        key = _ACTIVE_PLATFORM.get("key", "off")
        props = _PLATFORM_PROPS.get(key)

        if key == "off" or props is None:
            await _orig_identify(self)
            return

        spoofer = self._headers
        identify_payload = {
            "op": 2,
            "d": {
                "token": self._token,
                "capabilities": 1734653,
                "properties": {
                    "os": props["os"],
                    "browser": props["browser"],
                    "device": props["device"],
                    "system_locale": props.get("system_locale") or spoofer.profile.locale,
                    "has_client_mods": False,
                    "browser_user_agent": props.get("browser_user_agent") or spoofer.profile.user_agent,
                    "browser_version": props.get("browser_version") or spoofer.profile.browser_version,
                    "os_version": props.get("os_version") or "10",
                    "referrer": props.get("referrer", ""),
                    "referring_domain": props.get("referring_domain", ""),
                    "referrer_current": "https://discord.com/",
                    "referring_domain_current": "discord.com",
                    "release_channel": "stable",
                    "client_build_number": spoofer.build_number,
                    "client_event_source": None,
                    "client_launch_id": spoofer._launch_id,
                    "launch_signature": spoofer._launch_signature,
                    "client_heartbeat_session_id": spoofer._heartbeat_session_id,
                    "client_app_state": spoofer._app_state,
                    "is_fast_connect": self._identify_sent,
                    "gateway_connect_reasons": "AppSkeleton",
                    "installation_id": spoofer._installation_id,
                },
                "presence": {
                    "status": "unknown",
                    "since": 0,
                    "activities": [],
                    "afk": False,
                },
                "compress": False,
                "client_state": {
                    "guild_versions": {},
                },
                "qos_token": "CgA=",
            },
        }
        await self.send_json(identify_payload)

    GatewayWebSocket._identify = _identify
    GatewayWebSocket._platform_patched = True


install_platform_patch()


class _PlatformGateway:
    """Lightweight extra gateway connection that only IDENTIFYs with a specific platform."""

    _GATEWAY = "wss://gateway.discord.gg/?encoding=json&v=9&compress=zlib-stream"
    _ZLIB_SUFFIX = b"\x00\x00\xff\xff"

    def __init__(self, token: str, props: dict):
        self._token = token
        self._props = props
        self._ws = None
        self._hb_task: Optional[asyncio.Task] = None
        self._running = False
        self._buf = bytearray()
        self._inflator = zlib.decompressobj()

    async def start(self):
        import websockets
        self._running = True
        while self._running:
            self._buf = bytearray()
            self._inflator = zlib.decompressobj()
            try:
                self._ws = await websockets.connect(self._GATEWAY, max_size=2**26)
                while True:
                    try:
                        raw = await self._ws.recv()
                    except Exception:
                        break
                    should_break = await self._handle(raw)
                    if should_break:
                        break
            except Exception:
                pass
            finally:
                if self._hb_task and not self._hb_task.done():
                    self._hb_task.cancel()
                if self._ws:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None
            if self._running:
                await asyncio.sleep(5)

    async def _handle(self, raw) -> bool:
        if isinstance(raw, bytes):
            self._buf.extend(raw)
            if len(raw) < 4 or raw[-4:] != self._ZLIB_SUFFIX:
                return False
            try:
                raw = self._inflator.decompress(self._buf).decode()
                self._buf = bytearray()
            except Exception:
                self._buf = bytearray()
                self._inflator = zlib.decompressobj()
                return False
        try:
            payload = json.loads(raw)
        except Exception:
            return False
        op = payload.get("op")
        if op == 10:
            interval = payload["d"]["heartbeat_interval"]
            if self._hb_task and not self._hb_task.done():
                self._hb_task.cancel()
            self._hb_task = asyncio.ensure_future(self._heartbeat(interval))
            await self._identify()
        elif op == 1:
            await self._send({"op": 1, "d": None})
        elif op == 7:
            return True  # reconnect
        elif op == 9:
            await asyncio.sleep(random.uniform(1, 5))
            await self._identify()
        return False

    async def _heartbeat(self, interval: float):
        await asyncio.sleep(interval / 1000 * random.random())
        while self._running and self._ws:
            try:
                await self._send({"op": 1, "d": None})
                await asyncio.sleep(interval / 1000)
            except Exception:
                break

    async def _identify(self):
        await self._send({
            "op": 2,
            "d": {
                "token": self._token,
                "capabilities": 1767421,
                "properties": self._props,
                "compress": False,
                "presence": {"status": "online", "since": 0, "activities": [], "afk": False},
                "client_state": {
                    "guild_versions": {}, "highest_last_message_id": "0",
                    "read_state_version": 0, "user_guild_settings_version": -1,
                    "user_settings_version": -1,
                },
            },
        })

    async def _send(self, data: dict):
        if self._ws:
            try:
                await self._ws.send(json.dumps(data))
            except Exception:
                pass

    async def close(self):
        self._running = False
        if self._hb_task and not self._hb_task.done():
            self._hb_task.cancel()
        if self._ws:
            try:
                await self._ws.close(1000)
            except Exception:
                pass
            self._ws = None


def _split_rotatable(cmd: dict) -> list:
    splits = {}
    for field in _ROTATABLE_FIELDS:
        val = cmd.get(field, "")
        if val and "," in str(val):
            splits[field] = [p.strip() for p in str(val).split(",")]
    if not splits:
        return [cmd]
    max_len = max(len(v) for v in splits.values())
    variants = []
    for i in range(max_len):
        variant = dict(cmd)
        for field, parts in splits.items():
            variant[field] = parts[i % len(parts)]
        variants.append(variant)
    return variants


def _parse_kv(args: list) -> dict:
    cmd = {}
    if not args:
        return cmd
    cmd["rpc_type"] = args[0].lower()
    raw = " ".join(args[1:]).strip()
    if not raw:
        return cmd
    tokens = re.split(r'(?:(?:^| )([a-zA-Z_]\w*)=)', raw)
    i = 1
    while i < len(tokens) - 1:
        k = tokens[i]
        if not k:
            i += 2
            continue
        v = tokens[i + 1].strip() if tokens[i + 1] else ""
        if k in ("buttons", "button_urls"):
            cmd.setdefault(k, []).append(v)
        else:
            cmd[k] = v
        i += 2
    return cmd


class RPC(Cog, ASCIIMixin):

    def __init__(self, bot):
        super().__init__(bot)
        self._active: dict = persistence.get("rpc", {})
        self._cache: dict = {}
        self._rotation_tasks: dict = {}
        self._keepalive_task = None
        self._status: str = "online"
        self._extra_gws: dict[str, asyncio.Task] = {}
        self._extra_gw_objs: dict[str, _PlatformGateway] = {}
        # presets: name -> {rpc_type: cmd_dict, ...}
        self._presets: dict = persistence.get("rpc_presets", {})
        # stack: pending set of simultaneous activities (list of cmd dicts)
        self._stack: list = persistence.get("rpc_stack", [])
        # named rotation: list of {cmd, interval}
        self._named_rotation: list = persistence.get("rpc_named_rotation", [])
        self._named_rotation_task: Optional[asyncio.Task] = None
        # dashboard queue loop (dashboard_rpc.json written by the site backend)
        self._dash_task: Optional[asyncio.Task] = None

    def _save_rpc(self):
        persistence.set_key("rpc", self._active)

    @listener()
    async def on_ready(self, *_):
        self._cache.clear()
        if self._keepalive_task is None or self._keepalive_task.done():
            self._keepalive_task = asyncio.ensure_future(self._keepalive_loop())
        if self._active:
            asyncio.ensure_future(self._reapply())
        saved_multi = persistence.get("multiplatform", [])
        if saved_multi:
            asyncio.ensure_future(self._restore_multiplatform(saved_multi))
        if self._dash_task is None or self._dash_task.done():
            self._dash_task = asyncio.ensure_future(self._dashboard_queue_loop())

    # ── dashboard queue (dashboard_rpc.json) ─────────────────────────────
    # The site backend drops one-shot action files into this instance's own
    # working directory; this loop applies them live so the RPC Editor /
    # Presets / Rotation / Platform pages control the running bot directly.

    def _dashboard_queue_path(self) -> str:
        return os.path.join(persistence.instance_dir(), "dashboard_rpc.json")

    async def _dashboard_queue_loop(self):
        while True:
            try:
                await self._process_dashboard_queue()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(2.0)

    async def _process_dashboard_queue(self):
        path = self._dashboard_queue_path()
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                payload = json.load(f)
            os.remove(path)
        except (OSError, json.JSONDecodeError):
            try:
                os.remove(path)
            except OSError:
                pass
            return

        action = payload.get("action")

        if action == "apply":
            rpc = payload.get("rpc") or {}
            if not rpc:
                return
            for rt in list(self._rotation_tasks):
                self._stop_rotation(rt)
            self._stop_named_rotation()
            self._active = dict(rpc)
            self._save_rpc()
            acts = [a for a in [await self._build_activity(c) for c in self._active.values()] if a]
            await self._send_payload(acts)

        elif action == "stop":
            for rt in list(self._rotation_tasks):
                self._stop_rotation(rt)
            self._stop_named_rotation()
            await self._send_payload([])
            self._active.clear()
            self._save_rpc()

        elif action == "preset_save":
            name = str(payload.get("name") or "").strip()
            rpc = payload.get("rpc")
            if name and isinstance(rpc, dict):
                self._presets[name] = dict(rpc)
                self._save_presets()

        elif action == "preset_delete":
            name = str(payload.get("name") or "").strip()
            if name and name in self._presets:
                del self._presets[name]
                self._save_presets()

        elif action == "rotation_save":
            entries = payload.get("entries") or []
            if isinstance(entries, list):
                self._named_rotation = list(entries)
                self._save_named_rotation()
                if payload.get("start") and self._named_rotation:
                    # Take over presence cleanly: stop any per-type rotations and
                    # drop the current static RPC, otherwise _build_and_send would
                    # merge each rotation frame with the leftover activities and
                    # the rotation would look like it "didn't apply".
                    for rt in list(self._rotation_tasks):
                        self._stop_rotation(rt)
                    self._active.clear()
                    self._save_rpc()
                    self._stop_named_rotation()
                    self._named_rotation_task = asyncio.ensure_future(self._run_named_rotation())

        elif action == "platform":
            value = str(payload.get("value") or "").strip().lower()
            if value in _PLATFORM_PROPS:
                set_active_platform(value)
                persistence.set_key("platform", value)
                asyncio.ensure_future(self._gw_reconnect())

    async def _restore_multiplatform(self, platforms: list):
        await asyncio.sleep(3)
        token = self.bot._http.token
        for name in platforms:
            if name in _PLATFORM_PROPS and name not in self._extra_gws:
                obj = _PlatformGateway(token, _PLATFORM_PROPS[name])
                task = asyncio.ensure_future(obj.start())
                self._extra_gw_objs[name] = obj
                self._extra_gws[name] = task

    async def _reapply(self):
        await asyncio.sleep(3)
        try:
            acts = [a for a in [await self._build_activity(c) for c in self._active.values()] if a]
            if acts:
                await self._send_payload(acts)
        except Exception:
            pass

    async def _keepalive_loop(self):
        while True:
            await asyncio.sleep(_KEEPALIVE_INTERVAL)
            if not self._active:
                continue
            try:
                acts = [a for a in [await self._build_activity(c) for c in self._active.values()] if a]
                if acts:
                    await self._send_payload(acts)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

    async def _send_payload(self, activities: list, *, retries: int = 6) -> bool:
        # modifyself's send_json silently no-ops when the socket is None or
        # closed, so a presence update issued while the gateway is reconnecting
        # is dropped with no error and nothing retries it until the keepalive
        # fires 25 minutes later. Wait for a live socket instead.
        payload = {
            "op": 3,
            "d": {
                "since": 0,
                "activities": activities,
                "status": self._status,
                "afk": False,
            },
        }
        for attempt in range(retries):
            gw = getattr(self.bot, "_gateway", None)
            if gw is not None and getattr(gw, "_ws", None) is not None:
                try:
                    await gw.send_json(payload)
                    return True
                except Exception:
                    pass
            await asyncio.sleep(min(2 ** attempt, 15))
        return False

    def _get_asset_channel_id(self) -> str:
        # configurable via state.json ("rpc_asset_channel"); falls back to the default
        return persistence.get("rpc_asset_channel", _ASSET_CHANNEL_ID)

    async def _fallback_asset_channel(self) -> Optional[str]:
        """First text channel in the first guild we're in — used when the
        configured asset channel is gone (left server, channel deleted)."""
        try:
            guilds = await self.bot._http.request(Route("GET", "/users/@me/guilds"))
            for g in (guilds or []):
                chans = await self.bot._http.request(
                    Route("GET", f"/guilds/{g.get('id')}/channels")
                )
                for c in (chans or []):
                    if c.get("type") == 0:
                        return str(c["id"])
        except Exception:
            pass
        return None

    async def _refresh_cdn_url(self, url: str) -> str:
        try:
            spoofer = self.bot._http._spoofer
            headers = spoofer.get_headers(skip_context_props=True)
            from wreq import Method
            client = self.bot._http._get_client()
            resp = await client.request(
                Method.POST,
                "https://discord.com/api/v9/attachments/refresh-urls",
                headers=headers,
                json={"attachment_urls": [url]},
            )
            if int(resp.status.as_int()) == 200:
                data = json.loads(await resp.text())
                refreshed = data.get("refreshed_urls", [])
                if refreshed:
                    return refreshed[0].get("refreshed", url)
        except Exception:
            pass
        return url

    async def _upload_n_get_asset_key(self, image_url: str) -> Optional[str]:
        if re.search(r'https?://(?:cdn\.discordapp\.com|media\.discordapp\.net)', image_url) and "?" in image_url:
            image_url = await self._refresh_cdn_url(image_url)

        match = re.search(_CDN_PAT, image_url)
        if match:
            ch, att, fn = match.groups()
            return f"mp:attachments/{ch}/{att}/{fn}"

        try:
            loop = asyncio.get_event_loop()

            def _download():
                req = _ur.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
                with _ur.urlopen(req, timeout=15) as r:
                    return r.read(), r.headers.get("Content-Type", "image/png")

            data, ct = await loop.run_in_executor(None, _download)
            if not data:
                return None

            filename = image_url.split("/")[-1].split("?")[0]
            if "." not in filename or len(filename) > 50:
                filename = "asset.gif" if "gif" in ct else "asset.png"

            boundary = uuid.uuid4().hex
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="payload_json"\r\n'
                f"Content-Type: application/json\r\n\r\n"
                f'{{"content":""}}\r\n'
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"\r\n'
                f"Content-Type: {ct}\r\n\r\n"
            ).encode() + data + f"\r\n--{boundary}--\r\n".encode()

            spoofer = self.bot._http._spoofer
            ch_id = self._get_asset_channel_id()
            headers = spoofer.get_headers(
                referer=f"https://discord.com/channels/@me/{ch_id}",
                context_location="chat_input",
            )
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"

            from wreq import Method
            client = self.bot._http._get_client()
            resp = await client.request(
                Method.POST,
                f"https://discord.com/api/v9/channels/{ch_id}/messages",
                headers=headers,
                body=body,
            )
            if int(resp.status.as_int()) not in (200, 201):
                # configured asset channel is dead — try a live guild channel
                ch_id = await self._fallback_asset_channel()
                if not ch_id:
                    return None
                resp = await client.request(
                    Method.POST,
                    f"https://discord.com/api/v9/channels/{ch_id}/messages",
                    headers=headers,
                    body=body,
                )
                if int(resp.status.as_int()) not in (200, 201):
                    return None

            resp_data = json.loads(await resp.text())
            attachments = resp_data.get("attachments", [])
            if not attachments:
                return None

            msg_id = resp_data.get("id")
            m2 = re.search(_CDN_PAT, attachments[0]["url"])
            if not m2:
                return None
            c2, a2, f2 = m2.groups()
            key = f"mp:attachments/{c2}/{a2}/{f2}"

            if msg_id:
                try:
                    del_headers = spoofer.get_headers(skip_context_props=True)
                    await client.request(
                        Method.DELETE,
                        f"https://discord.com/api/v9/channels/{ch_id}/messages/{msg_id}",
                        headers=del_headers,
                    )
                except Exception:
                    pass

            return key
        except Exception:
            return None

    async def _get_asset_key(self, image_url: str) -> Optional[str]:
        if not image_url or not image_url.startswith("http"):
            return None
        cache_key = image_url.split("?")[0]
        if cache_key in self._cache:
            return self._cache[cache_key]
        key = await self._upload_n_get_asset_key(image_url)
        if key:
            self._cache[cache_key] = key
        return key

    async def _build_activity(self, cmd: dict) -> Optional[dict]:
        rpc_type = cmd.get("rpc_type", "").lower()
        t = int(time.time() * 1000)
        spoof = str(cmd.get("spoof", "")).lower() in ("true", "1", "yes")

        def ts_now():
            return {"start": t}

        def ts_prog(el, tot):
            cur = int(float(el) * 60000)
            return {"start": t - cur, "end": t - cur + int(float(tot) * 60000)}

        def mk_buttons(act):
            btns = cmd.get("buttons") or []
            urls = cmd.get("button_urls") or []
            pairs = [(b, u) for b, u in zip(btns, urls) if b and u][:2]
            if pairs:
                act["buttons"] = [p[0] for p in pairs]
                act.setdefault("metadata", {})["button_urls"] = [p[1] for p in pairs]

        async def img() -> Optional[str]:
            u = cmd.get("imglink") or cmd.get("image_url") or cmd.get("image") or ""
            return await self._get_asset_key(u) if u and u.startswith("http") else None

        async def small_img() -> Optional[str]:
            u = cmd.get("small_imglink") or cmd.get("small_image_url") or cmd.get("small_image") or ""
            return await self._get_asset_key(u) if u and u.startswith("http") else None

        def mk_assets(large_image=None, large_text="", small_image=None, small_text=""):
            a = {}
            if large_image: a["large_image"] = large_image
            if large_text:  a["large_text"]  = large_text[:128]
            if small_image: a["small_image"] = small_image
            if small_text:  a["small_text"]  = small_text[:128]
            return a if a else None

        if rpc_type == "clear":
            return None

        if rpc_type == "custom_status":
            txt = "‎" if str(cmd.get("invisible", "")).lower() in ("true", "1", "yes") else cmd.get("text", "")[:128]
            act: dict = {"type": 4, "name": "Custom Status", "state": txt}
            if cmd.get("emoji"):
                act["emoji"] = {"name": cmd["emoji"], "id": None, "animated": False}
            return act

        if rpc_type == "spotify":
            asset_key = await img()
            small_key = await small_img()
            dur = float(cmd.get("total_minutes", 3.5))
            pos = float(cmd.get("elapsed_minutes", 0))
            cur_ms = int(pos * 60000)
            tot_ms = int(dur * 60000)
            start = t - cur_ms
            tid = "0VjIjW4GlUZAMYd2vXMi3b"
            act = {
                "type": 2, "name": "Spotify",
                "details": cmd.get("details", cmd.get("name", "Unknown"))[:128],
                "state": cmd.get("state", "Unknown")[:128],
                "timestamps": {"start": start, "end": start + tot_ms},
                "application_id": "3201606009684",
                "sync_id": tid, "session_id": f"spotify:{tid}",
                "party": {"id": f"spotify:{tid}", "size": [1, 1]},
                "secrets": {"join": tid, "spectate": tid, "match": tid},
                "instance": True, "flags": 48,
            }
            assets = mk_assets(asset_key, cmd.get("large_text", ""), small_key, cmd.get("small_text", ""))
            if assets: act["assets"] = assets
            mk_buttons(act)
            if spoof: act["type"] = 1; act.setdefault("url", "https://twitch.tv/discord")
            return act

        if rpc_type == "youtube":
            asset_key = await img()
            small_key = await small_img()
            act = {
                "type": 3, "name": "YouTube",
                "details": cmd.get("details", cmd.get("name", "Video"))[:128],
                "state": cmd.get("state", "Channel")[:128],
                "application_id": "111299001912",
                "timestamps": ts_prog(float(cmd.get("elapsed_minutes", 0)), float(cmd.get("total_minutes", 10))),
            }
            assets = mk_assets(asset_key, cmd.get("large_text", ""), small_key, cmd.get("small_text", ""))
            if assets: act["assets"] = assets
            mk_buttons(act)
            if spoof: act["type"] = 1; act.setdefault("url", "https://twitch.tv/discord")
            return act

        if rpc_type == "xbox":
            asset_key = await img()
            act = {
                "type": 0, "name": cmd.get("name", "Game")[:128],
                "application_id": "622174530214821906",
                "platform": "xbox", "timestamps": ts_now(),
            }
            if cmd.get("details"): act["details"] = cmd["details"][:128]
            if cmd.get("state"):   act["state"]   = cmd["state"][:128]
            assets = mk_assets(asset_key)
            if assets: act["assets"] = assets
            pc, pm = cmd.get("party_cur"), cmd.get("party_max")
            if pc and pm: act["party"] = {"id": "xbox-party", "size": [int(pc), int(pm)]}
            mk_buttons(act)
            if spoof: act["type"] = 1; act.setdefault("url", "https://twitch.tv/discord")
            return act

        if rpc_type in ("playstation", "ps4", "ps5"):
            asset_key = await img()
            act = {
                "type": 0, "name": cmd.get("name", "Game")[:128],
                "application_id": "1470539864909943067",
                "platform": cmd.get("platform", "ps5"), "timestamps": ts_now(),
            }
            if cmd.get("details"): act["details"] = cmd["details"][:128]
            if cmd.get("state"):   act["state"]   = cmd["state"][:128]
            assets = mk_assets(asset_key)
            if assets: act["assets"] = assets
            pc, pm = cmd.get("party_cur"), cmd.get("party_max")
            if pc and pm: act["party"] = {"id": "ps-party", "size": [int(pc), int(pm)]}
            mk_buttons(act)
            if spoof: act["type"] = 1; act.setdefault("url", "https://twitch.tv/discord")
            return act

        if rpc_type == "crunchyroll":
            asset_key = await img()
            small_key = await small_img()
            act = {
                "type": 3, "name": "Crunchyroll",
                "details": cmd.get("details", cmd.get("name", "Anime"))[:128],
                "application_id": "981509069309354054",
                "timestamps": ts_prog(float(cmd.get("elapsed_minutes", 0)), float(cmd.get("total_minutes", 24))),
            }
            if cmd.get("state"): act["state"] = cmd["state"][:128]
            assets = mk_assets(asset_key, cmd.get("large_text", ""), small_key, cmd.get("small_text", ""))
            if assets: act["assets"] = assets
            mk_buttons(act)
            if spoof: act["type"] = 1; act.setdefault("url", "https://twitch.tv/discord")
            return act

        if rpc_type == "vrchat":
            asset_key = await img()
            small_key = await small_img()
            act = {
                "type": 0, "name": cmd.get("name", "VRChat")[:128],
                "application_id": cmd.get("app_id") or "1498387526501535835",
                "platform": cmd.get("platform", "meta_quest"),
                "session_id": cmd.get("session_id") or format(int(time.time() * 1000), "x"),
                "timestamps": ts_now(),
                "content_classification": {"loaded": True, "data": None},
            }
            assets = mk_assets(asset_key, cmd.get("large_text", "VRChat"), small_key, cmd.get("small_text", ""))
            if assets: act["assets"] = assets
            act["state"] = cmd.get("state", "")
            if cmd.get("details"): act["details"] = cmd["details"][:128]
            mk_buttons(act)
            if spoof: act["type"] = 1; act.setdefault("url", "https://twitch.tv/discord")
            return act

        if rpc_type == "playing":
            asset_key = await img()
            small_key = await small_img()
            act = {
                "type": 0, "name": cmd.get("name", "Game")[:128],
                "application_id": cmd.get("app_id") or "367827983903490050",
                "timestamps": ts_now(),
            }
            if cmd.get("details"): act["details"] = cmd["details"][:128]
            if cmd.get("state"):   act["state"]   = cmd["state"][:128]
            assets = mk_assets(asset_key, cmd.get("large_text", ""), small_key, cmd.get("small_text", ""))
            if assets: act["assets"] = assets
            pc, pm = cmd.get("party_cur"), cmd.get("party_max")
            if pc and pm: act["party"] = {"id": "game-party", "size": [int(pc), int(pm)]}
            mk_buttons(act)
            if spoof: act["type"] = 1; act.setdefault("url", "https://twitch.tv/discord")
            return act

        if rpc_type == "watching":
            asset_key = await img()
            small_key = await small_img()
            act = {
                "type": 3, "name": cmd.get("name", "Show")[:128],
                "application_id": cmd.get("app_id") or "367827983903490050",
            }
            if cmd.get("details"): act["details"] = cmd["details"][:128]
            if cmd.get("state"):   act["state"]   = cmd["state"][:128]
            tot = float(cmd.get("total_minutes", 0))
            if tot: act["timestamps"] = ts_prog(float(cmd.get("elapsed_minutes", 0)), tot)
            assets = mk_assets(asset_key, cmd.get("large_text", ""), small_key, cmd.get("small_text", ""))
            if assets: act["assets"] = assets
            mk_buttons(act)
            if spoof: act["type"] = 1; act.setdefault("url", "https://twitch.tv/discord")
            return act

        if rpc_type == "listening":
            asset_key = await img()
            small_key = await small_img()
            act = {
                "type": 2, "name": cmd.get("name", "Music")[:128],
                "application_id": cmd.get("app_id") or "534203414247112723",
            }
            if cmd.get("details"): act["details"] = cmd["details"][:128]
            if cmd.get("state"):   act["state"]   = cmd["state"][:128]
            tot = float(cmd.get("total_minutes", 0))
            if tot: act["timestamps"] = ts_prog(float(cmd.get("elapsed_minutes", 0)), tot)
            assets = mk_assets(asset_key, cmd.get("large_text", ""), small_key, cmd.get("small_text", ""))
            if assets: act["assets"] = assets
            mk_buttons(act)
            if spoof: act["type"] = 1; act.setdefault("url", "https://twitch.tv/discord")
            return act

        if rpc_type == "streaming":
            asset_key = await img()
            small_key = await small_img()
            act = {
                "type": 1, "name": cmd.get("name", "Stream")[:128],
                "url": cmd.get("stream_url") or "https://twitch.tv/discord",
                "application_id": cmd.get("app_id") or "111299001912",
                "timestamps": ts_now(),
            }
            if cmd.get("details"): act["details"] = cmd["details"][:128]
            if cmd.get("state"):   act["state"]   = cmd["state"][:128]
            assets = mk_assets(asset_key, cmd.get("large_text", ""), small_key, cmd.get("small_text", ""))
            if assets: act["assets"] = assets
            mk_buttons(act)
            return act

        if rpc_type == "competing":
            asset_key = await img()
            small_key = await small_img()
            act = {
                "type": 5, "name": cmd.get("name", "Tournament")[:128],
                "application_id": cmd.get("app_id") or "367827983903490050",
                "timestamps": ts_now(),
            }
            if cmd.get("details"): act["details"] = cmd["details"][:128]
            if cmd.get("state"):   act["state"]   = cmd["state"][:128]
            assets = mk_assets(asset_key, cmd.get("large_text", ""), small_key, cmd.get("small_text", ""))
            if assets: act["assets"] = assets
            mk_buttons(act)
            if spoof: act["type"] = 1; act.setdefault("url", "https://twitch.tv/discord")
            return act

        if rpc_type == "custom":
            act_type = int(cmd.get("activity_type", 0))
            name = cmd.get("name", "Activity")[:128]
            li_url = cmd.get("large_image", "") or cmd.get("imglink", "")
            si_url = cmd.get("small_image", "") or cmd.get("small_imglink", "")
            li_key = await self._get_asset_key(li_url) if li_url else None
            si_key = await self._get_asset_key(si_url) if si_url else None
            act = {
                "type": act_type, "name": name,
                "application_id": cmd.get("app_id") or "367827983903490050",
            }
            if cmd.get("details"): act["details"] = cmd["details"][:128]
            if cmd.get("state"):   act["state"]   = cmd["state"][:128]
            if act_type == 1 and cmd.get("stream_url"): act["url"] = cmd["stream_url"]
            if li_key or si_key:
                act["assets"] = {}
                if li_key: act["assets"]["large_image"] = li_key; act["assets"]["large_text"] = cmd.get("large_text", name)[:128]
                if si_key: act["assets"]["small_image"] = si_key; act["assets"]["small_text"] = cmd.get("small_text", "")[:128]
            tot_v = cmd.get("total_minutes")
            act["timestamps"] = ts_prog(float(cmd.get("elapsed_minutes", 0)), float(tot_v)) if tot_v else ts_now()
            pc, pm = cmd.get("party_cur"), cmd.get("party_max")
            if pc and pm: act["party"] = {"id": "custom-party", "size": [int(pc), int(pm)]}
            mk_buttons(act)
            if spoof: act["type"] = 1; act.setdefault("url", "https://twitch.tv/discord")
            return act

        return None

    async def _build_and_send(self, cmd: dict):
        rpc_type = cmd.get("rpc_type", "").lower()
        if rpc_type == "clear":
            await self._send_payload([])
            return
        act = await self._build_activity(cmd)
        if act is None:
            return
        merged = []
        for rt, existing_cmd in list(self._active.items()):
            if rt == rpc_type:
                continue
            a = await self._build_activity(existing_cmd)
            if a:
                merged.append(a)
        merged.append(act)
        await self._send_payload(merged)

    def _save_presets(self):
        persistence.set_key("rpc_presets", self._presets)

    def _save_stack(self):
        persistence.set_key("rpc_stack", self._stack)

    def _save_named_rotation(self):
        persistence.set_key("rpc_named_rotation", self._named_rotation)

    def _stop_named_rotation(self):
        if self._named_rotation_task and not self._named_rotation_task.done():
            self._named_rotation_task.cancel()
        self._named_rotation_task = None

    async def _run_named_rotation(self):
        # cycles through entries, each for its own interval
        idx = 0
        try:
            while self._named_rotation:
                entry = self._named_rotation[idx % len(self._named_rotation)]
                cmd = entry["cmd"]
                interval = max(1, int(entry.get("interval", 60)))
                try:
                    await self._build_and_send(cmd)
                except Exception:
                    pass
                await asyncio.sleep(interval)
                idx += 1
        except asyncio.CancelledError:
            pass

    def _stop_rotation(self, rpc_type: str):
        task = self._rotation_tasks.pop(rpc_type, None)
        if task and not task.done():
            task.cancel()

    async def _run_rotation(self, rpc_type: str, variants: list, interval: int):
        idx = 0
        try:
            while True:
                variant = variants[idx % len(variants)]
                self._active[rpc_type] = variant
                try:
                    await self._build_and_send(variant)
                except Exception:
                    pass
                idx += 1
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass

    @command()
    async def rpc(self, ctx):
        rest = " ".join(ctx.message.content.split()[1:])
        args = rest.strip().split()

        if not args:
            await self.aprint(ctx, "RPC", [
                f"types: {', '.join(_RPC_TYPES)}",
                "usage: .rpc <type> [key=value ...]",
                "  imglink=<url>  spoof=true  rotate_interval=20",
                "presets: .rpc preset save/load/list/delete <name>",
                "stack:   .rpc stack add <secs> <type> [kv...] | run | stop | list | clear",
                "rotation:.rpc rotation add <secs> <type> [kv...] | start | stop | list | remove <#> | clear",
            ], delay=15)
            return

        cmd = _parse_kv(args)
        rpc_type = cmd.get("rpc_type", "")

        if rpc_type == "stop":
            for rt in list(self._rotation_tasks):
                self._stop_rotation(rt)
            self._stop_named_rotation()
            await self._send_payload([])
            self._active.clear()
            self._save_rpc()
            await self.asuccess(ctx, "rich presence cleared", delay=8)
            return

        # ── preset subcommand ──────────────────────────────────────────────
        if rpc_type == "preset":
            sub = args[1].lower() if len(args) > 1 else ""
            name = args[2] if len(args) > 2 else ""

            if sub == "save":
                if not name:
                    await self.aerror(ctx, "usage: .rpc preset save <name>", delay=8)
                    return
                self._presets[name] = dict(self._active)
                self._save_presets()
                await self.asuccess(ctx, f"preset '{name}' saved ({len(self._active)} slot(s))", delay=8)

            elif sub == "load":
                if not name or name not in self._presets:
                    known = ", ".join(self._presets) or "none"
                    await self.aerror(ctx, f"preset '{name}' not found — saved: {known}", delay=10)
                    return
                for rt in list(self._rotation_tasks):
                    self._stop_rotation(rt)
                self._active = dict(self._presets[name])
                self._save_rpc()
                acts = [a for a in [await self._build_activity(c) for c in self._active.values()] if a]
                await self._send_payload(acts)
                await self.asuccess(ctx, f"preset '{name}' loaded", delay=8)

            elif sub == "list":
                if not self._presets:
                    await self.aprint(ctx, "Presets", ["no presets saved"], delay=8)
                    return
                lines = [f"{n}: {list(v.keys())}" for n, v in self._presets.items()]
                await self.aprint(ctx, "Presets", lines, delay=12)

            elif sub == "delete":
                if not name or name not in self._presets:
                    await self.aerror(ctx, f"preset '{name}' not found", delay=8)
                    return
                del self._presets[name]
                self._save_presets()
                await self.asuccess(ctx, f"preset '{name}' deleted", delay=8)

            else:
                await self.aprint(ctx, "Preset Usage", [
                    ".rpc preset save <name>",
                    ".rpc preset load <name>",
                    ".rpc preset list",
                    ".rpc preset delete <name>",
                ], delay=10)
            return

        # ── stack subcommand ───────────────────────────────────────────────
        # Stack = a pending set of multiple simultaneous activities.
        # Build up entries of different types, then apply them all at once.
        if rpc_type == "stack":
            sub = args[1].lower() if len(args) > 1 else ""

            if sub == "add":
                # .rpc stack add <type> [key=value...]
                # Supports all types + all keys (imglink, details, state, buttons, etc.)
                if len(args) < 3:
                    await self.aerror(ctx, "usage: .rpc stack add <type> [key=value...]", delay=10)
                    return
                inner_cmd = _parse_kv(args[2:])
                rt = inner_cmd.get("rpc_type", "")
                if rt not in _RPC_TYPES:
                    await self.aerror(ctx, f"unknown type '{rt}' — valid: {', '.join(_RPC_TYPES)}", delay=10)
                    return
                # one entry per rpc_type — overwrite if same type added again
                self._stack = [e for e in self._stack if e.get("rpc_type") != rt]
                self._stack.append(inner_cmd)
                self._save_stack()
                await self.asuccess(ctx, f"stack: {len(self._stack)} slot(s) — added {rt}", delay=8)

            elif sub == "remove":
                rt = args[2].lower() if len(args) > 2 else ""
                before = len(self._stack)
                self._stack = [e for e in self._stack if e.get("rpc_type") != rt]
                self._save_stack()
                if len(self._stack) < before:
                    await self.asuccess(ctx, f"removed {rt} from stack", delay=8)
                else:
                    await self.aerror(ctx, f"'{rt}' not in stack", delay=8)

            elif sub == "apply":
                if not self._stack:
                    await self.aerror(ctx, "stack is empty — add entries first", delay=8)
                    return
                for rt in list(self._rotation_tasks):
                    self._stop_rotation(rt)
                self._active = {e["rpc_type"]: e for e in self._stack}
                self._save_rpc()
                acts = [a for a in [await self._build_activity(e) for e in self._stack] if a]
                await self._send_payload(acts)
                types_str = ", ".join(e["rpc_type"] for e in self._stack)
                await self.asuccess(ctx, f"applied {len(acts)} simultaneous activit(ies): {types_str}", delay=10)

            elif sub == "list":
                if not self._stack:
                    await self.aprint(ctx, "Stack", ["empty — use: .rpc stack add <type> [kv...]"], delay=8)
                    return
                lines = [
                    f"#{i+1} [{e.get('rpc_type','?')}] — {' '.join(f'{k}={v}' for k,v in e.items() if k != 'rpc_type')[:80]}"
                    for i, e in enumerate(self._stack)
                ]
                await self.aprint(ctx, "Stack", lines, delay=12)

            elif sub == "clear":
                self._stack.clear()
                self._save_stack()
                await self.asuccess(ctx, "stack cleared", delay=8)

            else:
                await self.aprint(ctx, "Stack Usage", [
                    ".rpc stack add <type> [key=val ...]   — types: " + ", ".join(_RPC_TYPES),
                    ".rpc stack apply                      — push all slots as simultaneous activities",
                    ".rpc stack remove <type>              — remove one slot",
                    ".rpc stack list                       — show pending slots",
                    ".rpc stack clear                      — wipe all slots",
                    "keys: imglink= details= state= name= large_text= small_text= spoof=true",
                    "      buttons= button_urls= app_id= party_cur= party_max=",
                ], delay=15)
            return

        # ── rotation subcommand ────────────────────────────────────────────
        if rpc_type == "rotation":
            sub = args[1].lower() if len(args) > 1 else ""

            if sub == "add":
                # .rpc rotation add <interval_secs> <rpc_type> [key=value...]
                if len(args) < 4:
                    await self.aerror(ctx, "usage: .rpc rotation add <interval_secs> <type> [key=value...]", delay=10)
                    return
                try:
                    interval = int(args[2])
                except ValueError:
                    await self.aerror(ctx, "interval must be a number (seconds)", delay=8)
                    return
                inner_cmd = _parse_kv(args[3:])
                if inner_cmd.get("rpc_type") not in _RPC_TYPES:
                    await self.aerror(ctx, f"unknown type '{inner_cmd.get('rpc_type')}' — use .rpc for a list", delay=10)
                    return
                self._named_rotation.append({"cmd": inner_cmd, "interval": interval})
                self._save_named_rotation()
                await self.asuccess(ctx, f"rotation: {len(self._named_rotation)} entr(ies) — {inner_cmd['rpc_type']} every {interval}s", delay=8)

            elif sub == "start":
                if not self._named_rotation:
                    await self.aerror(ctx, "rotation is empty — add entries first", delay=8)
                    return
                self._stop_named_rotation()
                self._named_rotation_task = asyncio.ensure_future(self._run_named_rotation())
                await self.asuccess(ctx, f"rotation started — {len(self._named_rotation)} entr(ies)", delay=8)

            elif sub == "stop":
                self._stop_named_rotation()
                await self.asuccess(ctx, "rotation stopped", delay=8)

            elif sub == "list":
                if not self._named_rotation:
                    await self.aprint(ctx, "Rotation", ["empty"], delay=8)
                    return
                lines = [
                    f"#{i+1}: {e['cmd'].get('rpc_type', '?')} — every {e['interval']}s"
                    for i, e in enumerate(self._named_rotation)
                ]
                await self.aprint(ctx, "Rotation", lines, delay=12)

            elif sub == "clear":
                self._stop_named_rotation()
                self._named_rotation.clear()
                self._save_named_rotation()
                await self.asuccess(ctx, "rotation cleared", delay=8)

            elif sub == "remove":
                idx_str = args[2] if len(args) > 2 else ""
                try:
                    idx = int(idx_str) - 1
                    if idx < 0 or idx >= len(self._named_rotation):
                        raise ValueError
                except ValueError:
                    await self.aerror(ctx, f"provide a valid entry number (1-{len(self._named_rotation)})", delay=8)
                    return
                removed = self._named_rotation.pop(idx)
                self._save_named_rotation()
                await self.asuccess(ctx, f"removed #{idx+1}: {removed['cmd'].get('rpc_type', '?')}", delay=8)

            else:
                await self.aprint(ctx, "Rotation Usage", [
                    ".rpc rotation add <secs> <type> [key=value...]",
                    ".rpc rotation start",
                    ".rpc rotation stop",
                    ".rpc rotation list",
                    ".rpc rotation remove <#>",
                    ".rpc rotation clear",
                ], delay=10)
            return

        if rpc_type not in _RPC_TYPES:
            await self.aerror(ctx, f"unknown type '{rpc_type}' — use .rpc for a list", delay=10)
            return

        self._stop_rotation(rpc_type)

        if rpc_type == "clear":
            await self._build_and_send(cmd)
            self._active.clear()
            self._save_rpc()
            await self.asuccess(ctx, "rich presence cleared", delay=8)
            return

        interval = int(cmd.get("rotate_interval", _DEFAULT_ROTATE_INTERVAL))
        variants = _split_rotatable(cmd)
        rotating = len(variants) > 1

        self._active[rpc_type] = variants[0]
        self._save_rpc()
        await self._build_and_send(variants[0])

        active_str = ", ".join(self._active.keys())
        extra = f"rotating {len(variants)} variants every {interval}s" if rotating else ""
        lines = [f"type: {rpc_type}", f"active: {active_str}"]
        if extra:
            lines.append(extra)
        await self.aprint(ctx, "RPC", lines, delay=10)

        if rotating:
            task = asyncio.ensure_future(self._run_rotation(rpc_type, variants, interval))
            self._rotation_tasks[rpc_type] = task
        else:
            await asyncio.sleep(2)
            try:
                await self._build_and_send(variants[0])
            except Exception:
                pass

    @command()
    async def rpcclear(self, ctx):
        for rt in list(self._rotation_tasks):
            self._stop_rotation(rt)
        await self._send_payload([])
        self._active.clear()
        self._save_rpc()
        await self.asuccess(ctx, "rich presence cleared", delay=8)

    async def _gw_reconnect(self):
        """Close and reopen the main gateway so a new IDENTIFY fires."""
        gw = self.bot._gateway
        gw._session_id = None
        gw._reconnect_attempts = 0
        gw._closed_event.set()
        try:
            if gw._ws:
                await gw._ws.close(4000)
        except Exception:
            pass
        await asyncio.sleep(0.15)
        gw._closed_event.clear()

    @command()
    async def platform(self, ctx):
        rest = " ".join(ctx.message.content.split()[1:]).strip().lower()

        if rest not in _PLATFORM_PROPS:
            await self.aerror(ctx, f"valid: {', '.join(_PLATFORM_PROPS)}", delay=8)
            return

        # patch the gateway's IDENTIFY payload (handles "off" → original too)
        set_active_platform(rest)
        persistence.set_key("platform", rest)

        await self.aprint(ctx, "Platform", [f"set to {rest}", "reconnecting..."], delay=8)

        async def _do():
            await asyncio.sleep(0.5)
            await self._gw_reconnect()

        asyncio.ensure_future(_do())

    @command()
    async def multiplatform(self, ctx):
        rest = " ".join(ctx.message.content.split()[1:]).strip().lower()

        # close existing extra gateways first
        for name, task in list(self._extra_gws.items()):
            gw_obj = self._extra_gw_objs.pop(name, None)
            if gw_obj:
                await gw_obj.close()
            task.cancel()
        self._extra_gws.clear()

        if rest in ("off", "stop", "clear", ""):
            persistence.set_key("multiplatform", [])
            await self.asuccess(ctx, "extra platform gateways closed", delay=6)
            return

        parts = [p.strip() for p in rest.split(",") if p.strip()]
        invalid = [p for p in parts if p not in _PLATFORM_PROPS]
        if invalid:
            await self.aerror(ctx, f"unknown: {', '.join(invalid)} — valid: {', '.join(_PLATFORM_PROPS)}", delay=10)
            return

        token = self.bot._http.token

        for name in parts:
            props = _PLATFORM_PROPS[name]
            obj = _PlatformGateway(token, props)
            task = asyncio.ensure_future(obj.start())
            self._extra_gw_objs[name] = obj
            self._extra_gws[name] = task

        persistence.set_key("multiplatform", parts)
        active = ", ".join(parts)
        await self.aprint(ctx, "Multi-Platform", [f"opening: {active}", f"{len(parts)} extra gateway(s)"], delay=10)

    @command()
    async def status(self, ctx):
        rest = " ".join(ctx.message.content.split()[1:]).strip().lower()
        valid = ("online", "idle", "dnd", "invisible")
        if rest not in valid:
            await self.aerror(ctx, f"valid: {', '.join(valid)}", delay=6)
            return
        self._status = rest
        # Rebuild whatever RPC is currently active and resend it alongside
        # the new status — a bare op:3 with activities=[] (the old behavior)
        # wipes any running rich presence every time the status changes.
        merged = [a for a in [await self._build_activity(c) for c in self._active.values()] if a]
        await self._send_payload(merged)
        await self.asuccess(ctx, f"status set to {rest}", delay=5)


def setup(bot):
    bot.add_cog(RPC(bot))
