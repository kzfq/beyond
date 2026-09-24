"""
Beyond — Group-Chat Extra cog (modifyself).

GC tools for group DMs you're in: get/set icon, add/remove members by username,
remove everyone, leave every group chat, and generate a friend-invite link.

Logic lives in reusable methods so the selfbot and /slash commands share it.
"""

from __future__ import annotations

import asyncio
import base64
import random

from modifyself.commands.cog import Cog
from modifyself.commands.core import command
from modifyself.http.route import Route

import ansi
from ascii_helper import send_temp

CATEGORY = "Group Chat Extra"
CATEGORY_DESC = "GC tools & members"

COMMANDS_INFO = {
    "gcicon":      ("gcicon", "Get the current GC's icon URL"),
    "setgcicon":   ("setgcicon <url>", "Set the GC icon from a URL"),
    "gcadd":       ("gcadd <username>", "Add a friend to this GC by username"),
    "gcremove":    ("gcremove <username>", "Remove a user from this GC by username"),
    "gcremoveall": ("gcremoveall", "Remove all members from this GC"),
    "massgcleave": ("massgcleave", "Leave all private group chats"),
    "friendlink":  ("friendlink [days] [max_uses]", "Generate a friend invite link"),
}


class GCExtra(Cog):

    def __init__(self, bot):
        super().__init__(bot)

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

    async def _fetch(self, cid: str):
        try:
            return await self.bot._http.request(Route("GET", f"/channels/{cid}"))
        except Exception:
            return None

    async def _gc_or_err(self, cid: str):
        """Return (data, None) if cid is a group DM, else (None, error_string)."""
        if not cid:
            return None, ansi.error("This command only works in a group chat.")
        data = await self._fetch(cid)
        if not data:
            return None, ansi.error("Failed to fetch GC info.")
        if data.get("type") != 3:
            return None, ansi.error("This command only works in a group chat.")
        return data, None

    async def _download(self, url: str):
        import aiohttp
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status != 200:
                        return None
                    return await r.read()
        except Exception:
            return None

    @staticmethod
    def _data_uri(data: bytes) -> str:
        if data[:4] == b"\x89PNG":
            mime = "image/png"
        elif data[:3] == b"GIF":
            mime = "image/gif"
        else:
            mime = "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"

    # ── logic (return ANSI strings) ──────────────────────────────────────
    async def get_icon(self, cid: str) -> str:
        data, err = await self._gc_or_err(cid)
        if err:
            return err
        icon = data.get("icon")
        if not icon:
            return ansi.error("This GC has no icon set.")
        return ansi.success(
            f"GC Icon: https://cdn.discordapp.com/channel-icons/{cid}/{icon}.png?size=4096")

    async def set_icon(self, cid: str, url: str) -> str:
        data, err = await self._gc_or_err(cid)
        if err:
            return err
        if not url:
            return ansi.error("Provide an image URL.")
        img = await self._download(url)
        if not img:
            return ansi.error("Failed to download image.")
        try:
            await self.bot._http.request(Route("PATCH", f"/channels/{cid}"),
                                         json={"icon": self._data_uri(img)})
            return ansi.success("GC icon updated.")
        except Exception as e:
            return ansi.error(f"Failed: {e}")

    async def add_member(self, cid: str, username: str) -> str:
        data, err = await self._gc_or_err(cid)
        if err:
            return err
        username = (username or "").strip().lower()
        if not username:
            return ansi.error("Provide a friend's username.")
        try:
            rels = await self.bot._http.request(Route("GET", "/users/@me/relationships")) or []
        except Exception as e:
            return ansi.error(f"Failed to fetch relationships: {e}")
        target = next((r.get("user") for r in rels
                       if r.get("type") == 1 and r.get("user", {}).get("username", "").lower() == username), None)
        if not target:
            return ansi.error(f"No friend found with username {username}.")
        try:
            await self.bot._http.request(
                Route("PUT", f"/channels/{cid}/recipients/{target['id']}"), json={})
            return ansi.success(f"Added {target['username']} to the GC.")
        except Exception as e:
            return ansi.error(f"Failed to add: {e}")

    async def remove_member(self, cid: str, username: str) -> str:
        data, err = await self._gc_or_err(cid)
        if err:
            return err
        username = (username or "").strip().lower()
        if not username:
            return ansi.error("Provide a username.")
        target = next((u for u in data.get("recipients", [])
                       if u.get("username", "").lower() == username), None)
        if not target:
            return ansi.error(f"User {username} not found in this GC.")
        try:
            await self.bot._http.request(Route("DELETE", f"/channels/{cid}/recipients/{target['id']}"))
            return ansi.success(f"Removed {target['username']}.")
        except Exception as e:
            return ansi.error(f"Failed: {e}")

    async def remove_all(self, cid: str) -> str:
        data, err = await self._gc_or_err(cid)
        if err:
            return err
        me = await self._my_id()
        members = [u for u in data.get("recipients", []) if str(u.get("id")) != me]
        if not members:
            return ansi.error("No members to remove.")
        removed = failed = 0
        for u in members:
            try:
                await self.bot._http.request(Route("DELETE", f"/channels/{cid}/recipients/{u['id']}"))
                removed += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.5)
        return (ansi.header("gc remove all") + "\n"
                + ansi.command_list([("Removed", str(removed)), ("Failed", str(failed))]))

    async def mass_leave(self) -> str:
        try:
            chans = await self.bot._http.request(Route("GET", "/users/@me/channels")) or []
        except Exception as e:
            return ansi.error(f"Failed to fetch channels: {e}")
        gcs = [c for c in chans if c.get("type") == 3]
        if not gcs:
            return ansi.error("You are not in any group chats.")
        left = failed = 0
        for gc in gcs:
            try:
                await self.bot._http.request(Route("DELETE", f"/channels/{gc['id']}"))
                left += 1
            except Exception:
                failed += 1
            await asyncio.sleep(random.uniform(0.8, 1.5))
        return (ansi.header("mass gc leave") + "\n"
                + ansi.command_list([("Left", str(left)), ("Failed", str(failed))]))

    async def friend_link(self, days: int = 7, max_uses: int = 10) -> str:
        try:
            data = await self.bot._http.request(
                Route("POST", "/users/@me/invites"),
                json={"max_age": days * 86400, "max_uses": max_uses,
                      "temporary": False, "target_type": 2})
            code = (data or {}).get("code", "?")
            return (ansi.header("friend invite") + "\n"
                    + ansi.command_list([("Link", f"discord.gg/{code}"),
                                         ("Expires", f"{days}d"),
                                         ("Max uses", str(max_uses))]))
        except Exception as e:
            return ansi.error(f"Failed to create invite: {e}")

    # ── selfbot commands ─────────────────────────────────────────────────
    @command(name="gcicon")
    async def gcicon(self, ctx, *, value: str = ""):
        await send_temp(ctx, await self.get_icon(self._cid(ctx)), 20)

    @command(name="setgcicon")
    async def setgcicon(self, ctx, *, value: str = ""):
        if not value.strip():
            await send_temp(ctx, ansi.command_usage("setgcicon", *COMMANDS_INFO["setgcicon"], "."), 10)
            return
        await send_temp(ctx, await self.set_icon(self._cid(ctx), value.strip()), 10)

    @command(name="gcadd")
    async def gcadd(self, ctx, *, value: str = ""):
        if not value.strip():
            await send_temp(ctx, ansi.command_usage("gcadd", *COMMANDS_INFO["gcadd"], "."), 10)
            return
        await send_temp(ctx, await self.add_member(self._cid(ctx), value), 10)

    @command(name="gcremove")
    async def gcremove(self, ctx, *, value: str = ""):
        if not value.strip():
            await send_temp(ctx, ansi.command_usage("gcremove", *COMMANDS_INFO["gcremove"], "."), 10)
            return
        await send_temp(ctx, await self.remove_member(self._cid(ctx), value), 10)

    @command(name="gcremoveall")
    async def gcremoveall(self, ctx, *, value: str = ""):
        await send_temp(ctx, await self.remove_all(self._cid(ctx)), 15)

    @command(name="massgcleave", aliases=["gcleaveall"])
    async def massgcleave(self, ctx, *, value: str = ""):
        await send_temp(ctx, await self.mass_leave(), 15)

    @command(name="friendlink", aliases=["finvite"])
    async def friendlink(self, ctx, *, value: str = ""):
        parts = value.split()
        try:
            days = int(parts[0]) if len(parts) > 0 else 7
            max_uses = int(parts[1]) if len(parts) > 1 else 10
        except ValueError:
            await send_temp(ctx, ansi.command_usage("friendlink", *COMMANDS_INFO["friendlink"], "."), 10)
            return
        await send_temp(ctx, await self.friend_link(days, max_uses), 20)


def setup(bot):
    bot.add_cog(GCExtra(bot))
