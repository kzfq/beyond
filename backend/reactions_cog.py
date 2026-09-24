"""
Beyond — Reactions cog (modifyself).

Auto-react to a chosen user's messages: single emoji, a cycling list, or several
at once. Reacts via the gateway (on_message_create), rate-limit aware.
"""


import asyncio
import urllib.parse

from modifyself.commands.cog import Cog, listener
from modifyself.commands.core import command
from modifyself.http.route import Route

import ansi
from ascii_helper import send_temp

CATEGORY = "Reactions"
CATEGORY_DESC = "Reaction automation"

COMMANDS_INFO = {
    "superreact":          ("superreact <user> <emoji>", "Super-react to every message from a user"),
    "superreactstop":      ("superreactstop <user>", "Stop super-reacting to a user"),
    "cyclesuperreact":     ("cyclesuperreact <user> <e1,e2,...>", "Cycle emojis on each message"),
    "cyclesuperreactstop": ("cyclesuperreactstop <user>", "Stop cycle super-react on a user"),
    "multisuperreact":     ("multisuperreact <user> <e1,e2,...>", "React with several emojis on every message"),
    "multisuperreactstop": ("multisuperreactstop <user>", "Stop multi super-react on a user"),
}


def _g(o, k, d=None):
    if isinstance(o, dict):
        return o.get(k, d)
    return getattr(o, k, d)


def _emoji_path(emoji: str) -> str:
    e = emoji.strip()
    if e.startswith("<a:") or e.startswith("<:"):
        parts = e.strip("<>").split(":")
        return f"{parts[1]}:{parts[2]}"  # name:id
    return urllib.parse.quote(e)


def _parse_id(arg: str):
    cleaned = (arg or "").strip().strip("<@!>").replace("&", "")
    return cleaned if cleaned.isdigit() else None


class Reactions(Cog):

    def __init__(self, bot):
        super().__init__(bot)
        self.single: dict = {}   # uid -> emoji
        self.cycle: dict = {}    # uid -> [emojis, idx]
        self.multi: dict = {}    # uid -> [emojis]
        self._tasks: set = set()

    def stop(self):
        for t in list(self._tasks):
            try:
                t.cancel()
            except Exception:
                pass
        self._tasks.clear()

    async def _react(self, cid, mid, emoji):
        path = _emoji_path(emoji)
        # type=1 = super/burst reaction
        route = Route("PUT", f"/channels/{cid}/messages/{mid}/reactions/{path}/@me?type=1")
        for attempt in range(3):
            try:
                await self.bot._http.request(route)
                return
            except Exception as e:
                msg = str(e).lower()
                if "429" in msg or "rate" in msg:
                    await asyncio.sleep(1.5)  # brief only; drop if still limited
                    if attempt >= 1:
                        return
                    continue
                if attempt < 2:
                    await asyncio.sleep(1.0)
                    continue
                return

    def _spawn(self, coro):
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    # ── gateway ──────────────────────────────────────────────────────────
    @listener()
    async def on_message_create(self, message):
        if not (self.single or self.cycle or self.multi):
            return
        author = _g(message, "author")
        aid = str(_g(author, "id", "") or "") if author else ""
        if not aid:
            return
        cid = str(_g(message, "channel_id", "") or "")
        mid = str(_g(message, "id", "") or "")
        if not cid or not mid:
            return

        if aid in self.single:
            self._spawn(self._react(cid, mid, self.single[aid]))
        if aid in self.cycle:
            emojis, idx = self.cycle[aid]
            self._spawn(self._react(cid, mid, emojis[idx]))
            self.cycle[aid] = [emojis, (idx + 1) % len(emojis)]
        if aid in self.multi:
            for e in self.multi[aid]:
                self._spawn(self._react(cid, mid, e))

    # ── commands ─────────────────────────────────────────────────────────
    async def _usage(self, ctx, name):
        await send_temp(ctx, ansi.command_usage(name, *COMMANDS_INFO[name], "."), 10)

    @command(name="superreact", aliases=["sr"])
    async def superreact(self, ctx, *, value: str = ""):
        parts = value.split(maxsplit=1)
        if len(parts) < 2:
            await self._usage(ctx, "superreact"); return
        uid = _parse_id(parts[0])
        if not uid:
            await send_temp(ctx, ansi.error("Invalid user."), 10); return
        self.single[uid] = parts[1].strip()
        await send_temp(ctx, ansi.success(f"Super-reacting to {uid} with {parts[1].strip()}."), 10)

    @command(name="superreactstop", aliases=["srstop"])
    async def superreactstop(self, ctx, *, value: str = ""):
        uid = _parse_id(value)
        if uid and uid in self.single:
            del self.single[uid]
            await send_temp(ctx, ansi.success(f"Stopped super-react on {uid}."), 10)
        else:
            await send_temp(ctx, ansi.error("No active super-react for that user."), 10)

    @command(name="cyclesuperreact", aliases=["csr"])
    async def cyclesuperreact(self, ctx, *, value: str = ""):
        parts = value.split(maxsplit=1)
        if len(parts) < 2:
            await self._usage(ctx, "cyclesuperreact"); return
        uid = _parse_id(parts[0])
        emojis = [e.strip() for e in parts[1].split(",") if e.strip()]
        if not uid or not emojis:
            await send_temp(ctx, ansi.error("Invalid user or emoji list."), 10); return
        self.cycle[uid] = [emojis, 0]
        await send_temp(ctx, ansi.success(f"Cycling {', '.join(emojis)} on {uid}."), 10)

    @command(name="cyclesuperreactstop", aliases=["csrstop"])
    async def cyclesuperreactstop(self, ctx, *, value: str = ""):
        uid = _parse_id(value)
        if uid and uid in self.cycle:
            del self.cycle[uid]
            await send_temp(ctx, ansi.success(f"Stopped cycle react on {uid}."), 10)
        else:
            await send_temp(ctx, ansi.error("No active cycle react for that user."), 10)

    @command(name="multisuperreact", aliases=["msr"])
    async def multisuperreact(self, ctx, *, value: str = ""):
        parts = value.split(maxsplit=1)
        if len(parts) < 2:
            await self._usage(ctx, "multisuperreact"); return
        uid = _parse_id(parts[0])
        emojis = [e.strip() for e in parts[1].split(",") if e.strip()]
        if not uid or not emojis:
            await send_temp(ctx, ansi.error("Invalid user or emoji list."), 10); return
        self.multi[uid] = emojis
        await send_temp(ctx, ansi.success(f"Multi-reacting with {', '.join(emojis)} on {uid}."), 10)

    @command(name="multisuperreactstop", aliases=["msrstop"])
    async def multisuperreactstop(self, ctx, *, value: str = ""):
        uid = _parse_id(value)
        if uid and uid in self.multi:
            del self.multi[uid]
            await send_temp(ctx, ansi.success(f"Stopped multi react on {uid}."), 10)
        else:
            await send_temp(ctx, ansi.error("No active multi react for that user."), 10)

    # ── shared logic for slash ───────────────────────────────────────────
    def set_single(self, uid, emoji):
        u = _parse_id(uid)
        if not u:
            return ansi.error("Invalid user.")
        self.single[u] = (emoji or "").strip()
        return ansi.success(f"Super-reacting to {u} with {emoji}.")

    def set_cycle(self, uid, emojis_str):
        u = _parse_id(uid)
        emojis = [e.strip() for e in (emojis_str or "").split(",") if e.strip()]
        if not u or not emojis:
            return ansi.error("Invalid user or emoji list.")
        self.cycle[u] = [emojis, 0]
        return ansi.success(f"Cycling {', '.join(emojis)} on {u}.")

    def set_multi(self, uid, emojis_str):
        u = _parse_id(uid)
        emojis = [e.strip() for e in (emojis_str or "").split(",") if e.strip()]
        if not u or not emojis:
            return ansi.error("Invalid user or emoji list.")
        self.multi[u] = emojis
        return ansi.success(f"Multi-reacting with {', '.join(emojis)} on {u}.")

    def unset(self, which, uid):
        u = _parse_id(uid)
        d = {"single": self.single, "cycle": self.cycle, "multi": self.multi}[which]
        if u and u in d:
            del d[u]
            return ansi.success(f"Stopped on {u}.")
        return ansi.error("No active reaction for that user.")


def setup(bot):
    bot.add_cog(Reactions(bot))
