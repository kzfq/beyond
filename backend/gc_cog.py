"""
Beyond — Group-Chat security cog (modifyself), gateway-driven.

For group DMs you control:
  - lockdown : re-adds members the instant they're removed
  - anti-add : kicks anyone added who wasn't there when you armed it
  - whitelist: exempt specific users from both, per-GC

Reacts to CHANNEL_RECIPIENT_ADD / CHANNEL_RECIPIENT_REMOVE gateway events —
no polling. Logic lives in reusable methods for selfbot + /slash commands.
"""

from __future__ import annotations

from modifyself.commands.cog import Cog, listener
from modifyself.commands.core import command
from modifyself.http.route import Route

import ansi
from ascii_helper import send_temp

CATEGORY = "Group Chat"
CATEGORY_DESC = "GC lockdown & security"

COMMANDS_INFO = {
    "gclockdown":    ("gclockdown <on/off>", "Lock GC membership — re-adds removed users"),
    "gcantiadd":     ("gcantiadd <on/off>", "Kick any user added to the GC"),
    "gcwhitelist":   ("gcwhitelist <user>", "Whitelist a user from GC protection"),
    "gcunwhitelist": ("gcunwhitelist <user>", "Remove a user from the GC whitelist"),
}


def _g(o, k, d=None):
    if isinstance(o, dict):
        return o.get(k, d)
    return getattr(o, k, d)


class GCSecurity(Cog):

    def __init__(self, bot):
        super().__init__(bot)
        self.lockdown: dict = {}    # channel_id -> set(member ids) baseline
        self.antiadd: dict = {}     # channel_id -> set(member ids) baseline
        self.whitelist: dict = {}   # channel_id -> set(uid)

    def stop(self):
        # gateway-driven now; nothing to cancel (kept for teardown compatibility)
        pass

    # ── helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _cid(ctx) -> str:
        v = getattr(ctx, "channel_id", None)
        if v:
            return str(v)
        m = getattr(ctx, "message", None)
        v = getattr(m, "channel_id", None)
        if v:
            return str(v)
        ch = getattr(ctx, "channel", None) or getattr(m, "channel", None)
        return str(getattr(ch, "id", "") or "")

    async def _members(self, cid: str) -> set:
        try:
            data = await self.bot._http.request(Route("GET", f"/channels/{cid}")) or {}
            return {str(r["id"]) for r in data.get("recipients", [])}
        except Exception:
            return set()

    async def _my_id(self) -> str:
        try:
            if getattr(self.bot, "user", None):
                return str(self.bot.user.id)
        except Exception:
            pass
        try:
            me = await self.bot._http.request(Route("GET", "/users/@me"))
            return str((me or {}).get("id", ""))
        except Exception:
            return ""

    async def _add(self, cid, uid):
        try:
            await self.bot._http.request(Route("PUT", f"/channels/{cid}/recipients/{uid}"), json={})
        except Exception:
            pass

    async def _kick(self, cid, uid):
        try:
            await self.bot._http.request(Route("DELETE", f"/channels/{cid}/recipients/{uid}"))
        except Exception:
            pass

    # ── gateway events (instant) ─────────────────────────────────────────
    @listener()
    async def on_channel_recipient_remove(self, data):
        cid = str(_g(data, "channel_id", "") or "")
        if cid not in self.lockdown:
            return
        uid = str(_g(_g(data, "user", {}), "id", "") or "")
        if not uid or uid in self.whitelist.get(cid, set()):
            return
        if uid == await self._my_id():
            return
        if uid not in self.lockdown[cid]:
            return  # only re-add members that were part of the locked set
        await self._add(cid, uid)

    @listener()
    async def on_channel_recipient_add(self, data):
        cid = str(_g(data, "channel_id", "") or "")
        if cid not in self.antiadd:
            return
        uid = str(_g(_g(data, "user", {}), "id", "") or "")
        if not uid or uid in self.whitelist.get(cid, set()):
            return
        if uid == await self._my_id():
            return
        if uid in self.antiadd[cid]:
            return  # an original member
        await self._kick(cid, uid)

    # ── logic (return ANSI strings) ──────────────────────────────────────
    async def set_lockdown(self, cid: str, on: bool) -> str:
        if not cid:
            return ansi.error("Run this inside a group DM.")
        if on:
            self.lockdown[cid] = await self._members(cid)
            return ansi.success(f"GC lockdown enabled — locking {len(self.lockdown[cid])} members.")
        self.lockdown.pop(cid, None)
        return ansi.success("GC lockdown disabled.")

    async def set_antiadd(self, cid: str, on: bool) -> str:
        if not cid:
            return ansi.error("Run this inside a group DM.")
        if on:
            self.antiadd[cid] = await self._members(cid)
            return ansi.success(f"GC anti-add enabled — {len(self.antiadd[cid])} members allowed.")
        self.antiadd.pop(cid, None)
        return ansi.success("GC anti-add disabled.")

    def wl_add(self, cid: str, uid: str) -> str:
        if not cid:
            return ansi.error("Run this inside a group DM.")
        uid = (uid or "").strip().strip("<@!>")
        if not uid:
            return ansi.error("Provide a user id.")
        self.whitelist.setdefault(cid, set()).add(uid)
        return ansi.success(f"Whitelisted {uid} in this GC.")

    def wl_remove(self, cid: str, uid: str) -> str:
        if not cid:
            return ansi.error("Run this inside a group DM.")
        uid = (uid or "").strip().strip("<@!>")
        if uid not in self.whitelist.get(cid, set()):
            return ansi.error(f"{uid} is not whitelisted in this GC.")
        self.whitelist[cid].discard(uid)
        return ansi.success(f"Unwhitelisted {uid} from this GC.")

    # ── selfbot commands ─────────────────────────────────────────────────
    async def _toggle(self, ctx, value, fn, name):
        s = (value or "").strip().lower()
        if s not in ("on", "off"):
            await send_temp(ctx, ansi.command_usage(name, *COMMANDS_INFO[name], "."), 10)
            return
        await send_temp(ctx, await fn(self._cid(ctx), s == "on"), 10)

    @command(name="gclockdown", aliases=["gcld"])
    async def gclockdown(self, ctx, *, value: str = ""):
        await self._toggle(ctx, value, self.set_lockdown, "gclockdown")

    @command(name="gcantiadd", aliases=["gcaa"])
    async def gcantiadd(self, ctx, *, value: str = ""):
        await self._toggle(ctx, value, self.set_antiadd, "gcantiadd")

    @command(name="gcwhitelist", aliases=["gcwl"])
    async def gcwhitelist(self, ctx, *, value: str = ""):
        if not value.strip():
            await send_temp(ctx, ansi.command_usage("gcwhitelist", *COMMANDS_INFO["gcwhitelist"], "."), 10)
            return
        await send_temp(ctx, self.wl_add(self._cid(ctx), value), 10)

    @command(name="gcunwhitelist", aliases=["gcunwl"])
    async def gcunwhitelist(self, ctx, *, value: str = ""):
        if not value.strip():
            await send_temp(ctx, ansi.command_usage("gcunwhitelist", *COMMANDS_INFO["gcunwhitelist"], "."), 10)
            return
        await send_temp(ctx, self.wl_remove(self._cid(ctx), value), 10)


def setup(bot):
    bot.add_cog(GCSecurity(bot))
