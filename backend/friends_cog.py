"""
Beyond — Friends cog (modifyself).

Friends-list tools for your own account: counts, add/remove, pending/outgoing/
blocked lists, block/unblock, mass-unfriend, close DMs, and per-user auto-reply.

Logic lives in reusable async methods (do_* / *_block) so the selfbot commands
and the /slash commands in beyond_backend share one implementation.
"""

from __future__ import annotations

import asyncio
import datetime
import random

from modifyself.commands.cog import Cog, listener
from modifyself.commands.core import command
from modifyself.http.route import Route

import ansi
from ascii_helper import ASCIIMixin, send_temp

CATEGORY = "Friends"
CATEGORY_DESC = "Friends list tools"

COMMANDS_INFO = {
    "friendcount":   ("friendcount", "Show your friend/block/pending counts"),
    "friend":        ("friend <user|id>", "Send a friend request"),
    "unfriend":      ("unfriend <@user|id>", "Remove a friend"),
    "pending":       ("pending", "Show incoming friend requests"),
    "outgoing":      ("outgoing", "Show outgoing friend requests"),
    "blocked":       ("blocked", "Show blocked users"),
    "block":         ("block <@user|id>", "Block a user"),
    "unblock":       ("unblock <@user|id>", "Unblock a user"),
    "massunfriend":  ("massunfriend", "Remove all friends one by one"),
    "closedms":      ("closedms", "Close all open DM channels"),
    "autoreply":     ("autoreply <@user> <message>", "Auto-reply to a user's messages"),
    "autoreplystop": ("autoreplystop [@user]", "Stop auto-reply for a user or all"),
}


def _g(o, k, d=None):
    if isinstance(o, dict):
        return o.get(k, d)
    return getattr(o, k, d)


class Friends(Cog, ASCIIMixin):

    def __init__(self, bot):
        super().__init__(bot)
        self.autoreply: dict = {}  # user_id -> message

    # ── helpers ──────────────────────────────────────────────────────────
    async def _rels(self) -> list:
        try:
            return await self.bot._http.request(Route("GET", "/users/@me/relationships")) or []
        except Exception:
            return []

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

    @staticmethod
    def _tag(user: dict) -> str:
        uname = user.get("username", "?")
        g = user.get("global_name")
        return f"{g} (@{uname})" if g else uname

    @staticmethod
    def _ago(since) -> str:
        if not since:
            return ""
        try:
            past = datetime.datetime.fromisoformat(str(since).replace("Z", "+00:00"))
            diff = datetime.datetime.now(datetime.timezone.utc) - past
            if diff.days > 0:
                return f"{diff.days}d ago"
            h = diff.seconds // 3600
            return f"{h}h ago" if h > 0 else "just now"
        except Exception:
            return ""

    # ── read-only displays (return ANSI strings) ─────────────────────────
    async def stats_block(self) -> str:
        rels = await self._rels()
        pairs = [
            ("Friends", str(sum(1 for r in rels if r.get("type") == 1))),
            ("Blocked", str(sum(1 for r in rels if r.get("type") == 2))),
            ("Incoming", str(sum(1 for r in rels if r.get("type") == 3))),
            ("Outgoing", str(sum(1 for r in rels if r.get("type") == 4))),
        ]
        return ansi.header("friends") + "\n" + ansi.command_list(pairs)

    async def list_block(self, rtype: int, title: str) -> str:
        rels = await self._rels()
        items = []
        for r in rels:
            if r.get("type") == rtype:
                items.append((self._tag(r.get("user", {})), self._ago(r.get("since")) or "—"))
        if not items:
            return ansi.header(title) + "\n" + ansi._block(f"{ansi.DARK}None{ansi.RESET}")
        return ansi.header(f"{title} [{len(items)}]") + "\n" + ansi.command_list(items)

    # ── mutations (return ANSI strings) ──────────────────────────────────
    async def do_friend(self, target: str) -> str:
        target = (target or "").strip().strip("<@!>")
        if not target:
            return ansi.error("Provide a username or id.")
        try:
            if target.isdigit():
                await self.bot._http.request(
                    Route("PUT", f"/users/@me/relationships/{target}"), json={"type": 1})
                return ansi.success(f"Friend request sent to {target}.")
            payload = {"username": target, "discriminator": None}
            if "#" in target:
                name, tag = target.split("#", 1)
                payload = {"username": name, "discriminator": int(tag)}
            await self.bot._http.request(
                Route("POST", "/users/@me/relationships"), json=payload)
            return ansi.success(f"Friend request sent to {target}.")
        except Exception as e:
            return ansi.error(f"Failed to add friend: {e}")

    async def do_rel_delete(self, uid: str, label: str) -> str:
        uid = (uid or "").strip().strip("<@!>")
        if not uid:
            return ansi.error("Provide a user id.")
        try:
            await self.bot._http.request(Route("DELETE", f"/users/@me/relationships/{uid}"))
            return ansi.success(f"{label} {uid}.")
        except Exception as e:
            return ansi.error(f"Failed: {e}")

    async def do_block(self, uid: str) -> str:
        uid = (uid or "").strip().strip("<@!>")
        if not uid:
            return ansi.error("Provide a user id.")
        try:
            await self.bot._http.request(
                Route("PUT", f"/users/@me/relationships/{uid}"), json={"type": 2})
            return ansi.success(f"Blocked {uid}.")
        except Exception as e:
            return ansi.error(f"Failed to block: {e}")

    async def do_massunfriend(self) -> str:
        friends = [r for r in await self._rels() if r.get("type") == 1]
        if not friends:
            return ansi.error("You have no friends to remove.")
        removed = failed = 0
        for r in friends:
            uid = str(r.get("user", {}).get("id", ""))
            if not uid:
                continue
            try:
                await self.bot._http.request(Route("DELETE", f"/users/@me/relationships/{uid}"))
                removed += 1
            except Exception:
                failed += 1
            await asyncio.sleep(random.uniform(0.6, 1.2))
        return (ansi.header("mass unfriend") + "\n"
                + ansi.command_list([("Removed", str(removed)), ("Failed", str(failed))]))

    async def do_closedms(self) -> str:
        try:
            chans = await self.bot._http.request(Route("GET", "/users/@me/channels")) or []
        except Exception as e:
            return ansi.error(f"Failed to fetch DMs: {e}")
        dms = [c for c in chans if c.get("type") == 1]
        if not dms:
            return ansi.error("No open DM channels.")
        closed = failed = 0
        for c in dms:
            cid = str(c.get("id", ""))
            try:
                await self.bot._http.request(Route("DELETE", f"/channels/{cid}"))
                closed += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.3)
        return (ansi.header("close dms") + "\n"
                + ansi.command_list([("Closed", str(closed)), ("Failed", str(failed))]))

    def set_autoreply(self, uid: str, msg: str) -> str:
        uid = (uid or "").strip().strip("<@!>")
        if not uid.isdigit():
            return ansi.error("Invalid user mention or id.")
        if not msg:
            return ansi.error("Provide a message.")
        self.autoreply[uid] = msg
        return ansi.success(f"Auto-reply set for {uid}.")

    def stop_autoreply(self, uid: str = "") -> str:
        uid = (uid or "").strip().strip("<@!>")
        if not uid:
            n = len(self.autoreply)
            self.autoreply.clear()
            return ansi.success(f"Auto-reply cleared for all {n} user(s).")
        if uid in self.autoreply:
            del self.autoreply[uid]
            return ansi.success(f"Auto-reply stopped for {uid}.")
        return ansi.error("No auto-reply active for that user.")

    # ── auto-reply listener ──────────────────────────────────────────────
    @listener()
    async def on_message_create(self, message):
        if not self.autoreply:
            return
        author = _g(message, "author")
        aid = str(_g(author, "id", "") or "") if author else ""
        if not aid or aid not in self.autoreply:
            return
        if _g(author, "bot", False):
            return
        if aid == await self._my_id():
            return
        content = _g(message, "content", "") or ""
        if not content:
            return
        cid = str(_g(message, "channel_id", "") or "")
        if not cid:
            ch = _g(message, "channel")
            cid = str(_g(ch, "id", "") or "")
        if not cid:
            return
        try:
            await self.bot._http.request(
                Route("POST", f"/channels/{cid}/messages"),
                json={"content": self.autoreply[aid]})
        except Exception:
            pass

    # ── selfbot commands ─────────────────────────────────────────────────
    async def _usage(self, ctx, name):
        await send_temp(ctx, ansi.command_usage(name, *COMMANDS_INFO[name], "."), 12)

    @command(name="friendcount", aliases=["fc"])
    async def friendcount(self, ctx, *, value: str = ""):
        await send_temp(ctx, await self.stats_block(), 15)

    @command(name="pending", aliases=["incoming"])
    async def pending(self, ctx, *, value: str = ""):
        await send_temp(ctx, await self.list_block(3, "incoming requests"), 30)

    @command(name="outgoing")
    async def outgoing(self, ctx, *, value: str = ""):
        await send_temp(ctx, await self.list_block(4, "outgoing requests"), 30)

    @command(name="blocked")
    async def blocked(self, ctx, *, value: str = ""):
        await send_temp(ctx, await self.list_block(2, "blocked users"), 30)

    @command(name="friend", aliases=["add", "addfriend"])
    async def friend(self, ctx, *, value: str = ""):
        if not value.strip():
            await self._usage(ctx, "friend"); return
        await send_temp(ctx, await self.do_friend(value), 10)

    @command(name="unfriend", aliases=["unadd", "removefriend"])
    async def unfriend(self, ctx, *, value: str = ""):
        if not value.strip():
            await self._usage(ctx, "unfriend"); return
        await send_temp(ctx, await self.do_rel_delete(value, "Unfriended"), 10)

    @command(name="block")
    async def block(self, ctx, *, value: str = ""):
        if not value.strip():
            await self._usage(ctx, "block"); return
        await send_temp(ctx, await self.do_block(value), 10)

    @command(name="unblock")
    async def unblock(self, ctx, *, value: str = ""):
        if not value.strip():
            await self._usage(ctx, "unblock"); return
        await send_temp(ctx, await self.do_rel_delete(value, "Unblocked"), 10)

    @command(name="massunfriend", aliases=["unfriendall"])
    async def massunfriend(self, ctx, *, value: str = ""):
        await send_temp(ctx, await self.do_massunfriend(), 15)

    @command(name="closedms", aliases=["cleardms"])
    async def closedms(self, ctx, *, value: str = ""):
        await send_temp(ctx, await self.do_closedms(), 12)

    @command(name="autoreply")
    async def autoreply(self, ctx, *, value: str = ""):
        parts = value.split(maxsplit=1)
        if len(parts) < 2:
            await self._usage(ctx, "autoreply"); return
        await send_temp(ctx, self.set_autoreply(parts[0], parts[1]), 10)

    @command(name="autoreplystop")
    async def autoreplystop(self, ctx, *, value: str = ""):
        await send_temp(ctx, self.stop_autoreply(value), 10)


def setup(bot):
    bot.add_cog(Friends(bot))
