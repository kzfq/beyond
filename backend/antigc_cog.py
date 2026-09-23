"""
Beyond — Anti-GC-Trap cog (modifyself).

Auto-leaves group-DM "traps": when you're added to a group DM you didn't make,
it (optionally) renames it, sets an icon, drops a message, blocks the owner, and
leaves — with an optional webhook alert and a per-user whitelist.

Ported to modifyself: listens on CHANNEL_CREATE, acts through bot._http routes,
replies through the shared ANSI helper (command deletes, reply self-deletes).
"""

from __future__ import annotations

import asyncio
import base64

from modifyself.commands.cog import Cog, listener
from modifyself.commands.core import command
from modifyself.http.route import Route

import ansi
import persistence
from ascii_helper import ASCIIMixin, send_temp

CATEGORY = "Anti-GC"
CATEGORY_DESC = "Auto-leave GC traps"

COMMANDS_INFO = {
    "antigctrap": ("antigctrap <on/off>", "Toggle the anti-GC trap"),
    "agctblock":  ("agctblock <on/off>",  "Auto-block the GC creator on leave"),
    "agctmsg":    ("agctmsg <message>",   "Message sent before leaving"),
    "agctname":   ("agctname <name>",     "Rename the GC before leaving"),
    "agcticon":   ("agcticon <url>",      "Set the GC icon before leaving"),
    "agctwebhook":("agctwebhook <url>",   "Webhook for trap alerts (blank to clear)"),
    "agctwl":     ("agctwl <user>",       "Whitelist a user (their GCs are ignored)"),
    "agctunwl":   ("agctunwl <user>",     "Remove a user from the whitelist"),
    "agctwllist": ("agctwllist",          "List whitelisted users"),
}

_DEFAULT = {
    "enabled": False,
    "block": False,
    "silent": True,
    "leave_msg": "loser",
    "gc_name": "u cant trap a god",
    "gc_icon_url": None,
    "webhook_url": None,
}


def _g(o, key, default=None):
    """Read a field whether the gateway handed us a dict or an object."""
    if isinstance(o, dict):
        return o.get(key, default)
    return getattr(o, key, default)


class AntiGC(Cog, ASCIIMixin):

    def __init__(self, bot):
        super().__init__(bot)
        cfg = persistence.get("agct_cfg", {}) or {}
        self.state = {**_DEFAULT, **(cfg if isinstance(cfg, dict) else {})}
        wl = persistence.get("agct_wl", []) or []
        self.whitelist = set(str(x) for x in wl) if isinstance(wl, list) else set()

    # ── persistence ──────────────────────────────────────────────────────
    def _save(self):
        persistence.set_key("agct_cfg", self.state)

    def _save_wl(self):
        persistence.set_key("agct_wl", list(self.whitelist))

    # ── http helpers ─────────────────────────────────────────────────────
    async def _req(self, method, path, **kw):
        return await self.bot._http.request(Route(method, path), **kw)

    async def _my_id(self) -> str:
        try:
            if getattr(self.bot, "user", None):
                return str(self.bot.user.id)
        except Exception:
            pass
        try:
            me = await self._req("GET", "/users/@me")
            return str((me or {}).get("id", ""))
        except Exception:
            return ""

    async def _gc_owner(self, cid: str) -> str:
        try:
            data = await self._req("GET", f"/channels/{cid}")
            return str((data or {}).get("owner_id") or "")
        except Exception:
            return ""

    async def _rename(self, cid: str, name: str):
        try:
            await self._req("PATCH", f"/channels/{cid}", json={"name": name})
        except Exception:
            pass

    async def _set_icon(self, cid: str, url: str):
        try:
            data, ct = await self._download(url)
            if not data:
                return
            mime = "image/gif" if data[:6] in (b"GIF87a", b"GIF89a") else (ct or "image/png")
            b64 = base64.b64encode(data).decode()
            await self._req("PATCH", f"/channels/{cid}",
                            json={"icon": f"data:{mime};base64,{b64}"})
        except Exception:
            pass

    async def _send(self, cid: str, content: str):
        try:
            await self._req("POST", f"/channels/{cid}/messages", json={"content": content})
        except Exception:
            pass

    async def _block(self, uid: str):
        try:
            await self._req("PUT", f"/users/@me/relationships/{uid}", json={"type": 2})
        except Exception:
            pass

    async def _leave(self, cid: str, silent: bool) -> bool:
        q = "true" if silent else "false"
        for _ in range(3):
            try:
                await self._req("DELETE", f"/channels/{cid}?silent={q}")
                return True
            except Exception:
                await asyncio.sleep(1)
        return False

    async def _download(self, url: str):
        import aiohttp
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status != 200:
                        return None, None
                    return await r.read(), r.headers.get("Content-Type", "")
        except Exception:
            return None, None

    async def _webhook(self, cid: str, owner_id: str, members: list):
        url = self.state.get("webhook_url")
        if not url:
            return
        import aiohttp
        embed = {
            "title": "Anti-GCTrap Alert",
            "description": (f"**Owner ID:** `{owner_id}`\n"
                            f"**Channel ID:** `{cid}`\n"
                            f"**Members:** `{', '.join(members) or 'None'}`"),
            "color": 0xFF0000,
        }
        try:
            async with aiohttp.ClientSession() as s:
                await s.post(url, json={"embeds": [embed]},
                             timeout=aiohttp.ClientTimeout(total=15))
        except Exception:
            pass

    # ── gateway: detect a group-DM trap ──────────────────────────────────
    @listener()
    async def on_channel_create(self, data):
        if not self.state.get("enabled"):
            return
        if _g(data, "type") != 3:  # 3 = GROUP_DM
            return
        cid = str(_g(data, "id", "") or "")
        if not cid:
            return

        recipients = _g(data, "recipients", []) or []
        member_ids = [str(_g(r, "id", "")) for r in recipients if _g(r, "id", "")]

        await asyncio.sleep(0.5)

        owner_id = str(_g(data, "owner_id", "") or "") or await self._gc_owner(cid)
        my_id = await self._my_id()

        if owner_id and owner_id == my_id:
            return  # my own group
        if owner_id and owner_id in self.whitelist:
            return

        if self.state.get("gc_name"):
            await self._rename(cid, self.state["gc_name"])
        if self.state.get("gc_icon_url"):
            await self._set_icon(cid, self.state["gc_icon_url"])
        if self.state.get("leave_msg"):
            await self._send(cid, self.state["leave_msg"])
        if self.state.get("block") and owner_id:
            await self._block(owner_id)
        await self._leave(cid, bool(self.state.get("silent", True)))
        await self._webhook(cid, owner_id, member_ids)

    # ── commands ─────────────────────────────────────────────────────────
    async def _usage(self, ctx, name):
        await send_temp(ctx, ansi.command_usage(name, *COMMANDS_INFO[name], "."), 15)

    @command(name="antigctrap", aliases=["agct"])
    async def antigctrap(self, ctx, *, value: str = ""):
        s = (value or "").strip().lower()
        if not s:
            await self.asuccess(ctx, f"Anti-GCTrap is {'on' if self.state['enabled'] else 'off'}.")
            return
        if s in ("on", "enable"):
            self.state["enabled"] = True; self._save()
            await self.asuccess(ctx, "Anti-GCTrap enabled.")
        elif s in ("off", "disable"):
            self.state["enabled"] = False; self._save()
            await self.asuccess(ctx, "Anti-GCTrap disabled.")
        else:
            await self.aerror(ctx, "Specify on or off.")

    @command(name="agctblock")
    async def agctblock(self, ctx, *, value: str = ""):
        s = (value or "").strip().lower()
        if not s:
            await self._usage(ctx, "agctblock"); return
        if s in ("on", "enable"):
            self.state["block"] = True; self._save()
            await self.asuccess(ctx, "Auto-block enabled.")
        elif s in ("off", "disable"):
            self.state["block"] = False; self._save()
            await self.asuccess(ctx, "Auto-block disabled.")
        else:
            await self.aerror(ctx, "Specify on or off.")

    @command(name="agctmsg")
    async def agctmsg(self, ctx, *, value: str = ""):
        if not value.strip():
            await self._usage(ctx, "agctmsg"); return
        self.state["leave_msg"] = value.strip(); self._save()
        await self.asuccess(ctx, "Leave message set.")

    @command(name="agctname")
    async def agctname(self, ctx, *, value: str = ""):
        if not value.strip():
            await self._usage(ctx, "agctname"); return
        self.state["gc_name"] = value.strip(); self._save()
        await self.asuccess(ctx, f"GC rename set to {self.state['gc_name']}.")

    @command(name="agcticon")
    async def agcticon(self, ctx, *, value: str = ""):
        if not value.strip():
            await self._usage(ctx, "agcticon"); return
        self.state["gc_icon_url"] = value.strip(); self._save()
        await self.asuccess(ctx, "GC icon URL set.")

    @command(name="agctwebhook")
    async def agctwebhook(self, ctx, *, value: str = ""):
        v = value.strip()
        self.state["webhook_url"] = v or None
        self._save()
        await self.asuccess(ctx, "Webhook cleared." if not v else "Webhook URL set.")

    @command(name="agctwl")
    async def agctwl(self, ctx, *, value: str = ""):
        if not value.strip():
            await self._usage(ctx, "agctwl"); return
        uid = value.strip().strip("<@!>")
        if uid in self.whitelist:
            await self.aerror(ctx, f"{uid} already whitelisted."); return
        self.whitelist.add(uid); self._save_wl()
        await self.asuccess(ctx, f"Whitelisted {uid}.")

    @command(name="agctunwl")
    async def agctunwl(self, ctx, *, value: str = ""):
        if not value.strip():
            await self._usage(ctx, "agctunwl"); return
        uid = value.strip().strip("<@!>")
        if uid not in self.whitelist:
            await self.aerror(ctx, f"{uid} is not whitelisted."); return
        self.whitelist.discard(uid); self._save_wl()
        await self.asuccess(ctx, f"Unwhitelisted {uid}.")

    @command(name="agctwllist")
    async def agctwllist(self, ctx, *, value: str = ""):
        if not self.whitelist:
            await self.aerror(ctx, "Whitelist is empty."); return
        pairs = [(uid, "whitelisted") for uid in sorted(self.whitelist)]
        await send_temp(ctx, ansi.header("agct whitelist") + "\n" + ansi.command_list(pairs), 15)


def setup(bot):
    bot.add_cog(AntiGC(bot))
