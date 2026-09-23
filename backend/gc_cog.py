"""
Beyond — Group-Chat security cog (modifyself).

For group DMs you control:
  - lockdown : re-adds members who get removed
  - anti-add : kicks anyone added who wasn't there when you armed it
  - whitelist: exempt specific users from both, per-GC

Two background pollers read bot._http live each cycle (survives reconnects).
Logic lives in reusable methods so the selfbot and /slash commands share it.
"""

from __future__ import annotations

import asyncio

from modifyself.commands.cog import Cog
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


class GCSecurity(Cog):

    def __init__(self, bot):
        super().__init__(bot)
        self.lockdown: dict = {}    # channel_id -> {uid: member}
        self.antiadd: dict = {}     # channel_id -> {uid: member}
        self.whitelist: dict = {}   # channel_id -> set(uid)
        self._ld_task = None
        self._aa_task = None

    def stop(self):
        for t in (self._ld_task, self._aa_task):
            if t is not None:
                try:
                    t.cancel()
                except Exception:
                    pass
        self._ld_task = self._aa_task = None

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

    async def _members(self, cid: str) -> dict:
        try:
            data = await self.bot._http.request(Route("GET", f"/channels/{cid}")) or {}
            return {str(r["id"]): r for r in data.get("recipients", [])}
        except Exception:
            return {}

    async def _add(self, cid: str, uid: str):
        try:
            await self.bot._http.request(Route("PUT", f"/channels/{cid}/recipients/{uid}"), json={})
        except Exception:
            pass

    async def _kick(self, cid: str, uid: str):
        try:
            await self.bot._http.request(Route("DELETE", f"/channels/{cid}/recipients/{uid}"))
        except Exception:
            pass

    # ── background loops ─────────────────────────────────────────────────
    async def _lockdown_loop(self):
        while True:
            try:
                for cid, tracked in list(self.lockdown.items()):
                    current = await self._members(cid)
                    wl = self.whitelist.get(cid, set())
                    missing = [u for uid, u in tracked.items() if uid not in current and uid not in wl]
                    for u in missing:
                        await self._add(cid, str(u.get("id")))
                    self.lockdown[cid] = current or tracked
                await asyncio.sleep(max(3, len(self.lockdown)))
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(3)

    async def _antiadd_loop(self):
        while True:
            try:
                for cid, tracked in list(self.antiadd.items()):
                    current = await self._members(cid)
                    wl = self.whitelist.get(cid, set())
                    intruders = [u for uid, u in current.items() if uid not in tracked and uid not in wl]
                    for u in intruders:
                        await self._kick(cid, str(u.get("id")))
                await asyncio.sleep(max(3, len(self.antiadd)))
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(3)

    def _ensure_loops(self):
        if self._ld_task is None or self._ld_task.done():
            self._ld_task = asyncio.create_task(self._lockdown_loop())
        if self._aa_task is None or self._aa_task.done():
            self._aa_task = asyncio.create_task(self._antiadd_loop())

    # ── logic (return ANSI strings) ──────────────────────────────────────
    async def set_lockdown(self, cid: str, on: bool) -> str:
        if not cid:
            return ansi.error("Run this inside a group DM.")
        if on:
            self.lockdown[cid] = await self._members(cid)
            self._ensure_loops()
            return ansi.success(f"GC lockdown enabled — tracking {len(self.lockdown[cid])} members.")
        self.lockdown.pop(cid, None)
        return ansi.success("GC lockdown disabled.")

    async def set_antiadd(self, cid: str, on: bool) -> str:
        if not cid:
            return ansi.error("Run this inside a group DM.")
        if on:
            self.antiadd[cid] = await self._members(cid)
            self._ensure_loops()
            return ansi.success(f"GC anti-add enabled — tracking {len(self.antiadd[cid])} members.")
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
