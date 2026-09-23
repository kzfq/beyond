"""
Beyond — Profile cog (modifyself).

Edits the logged-in account's profile:
  - display name (global_name)   -> PATCH /users/@me
  - avatar / banner (from URL)   -> PATCH /users/@me  (base64 data URI)
  - accent colour                -> PATCH /users/@me
  - bio ("About Me") / pronouns  -> PATCH /users/@me/profile

Drives the Beyond "Profile" tab via IPC and mirrors every field as a
"." selfbot command (and "/profile" slash, wired in beyond_backend).

Only touches YOUR OWN account through Discord's normal profile endpoints.
"""

from __future__ import annotations

import asyncio
import base64
import re
import urllib.request as _ur
from typing import Optional

from modifyself.commands.cog import Cog
from modifyself.commands.core import command
from modifyself.http.route import Route

EMIT = None

def _emit(obj: dict) -> None:
    if EMIT:
        try:
            EMIT(obj)
        except Exception:
            pass

def _parse_accent(value) -> Optional[int]:
    """Accept '#5b8cff', '5b8cff', '0x5b8cff', or an int -> Discord int colour."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip().lstrip("#")
    if s.lower().startswith("0x"):
        s = s[2:]
    try:
        return int(s, 16)
    except Exception:
        try:
            return int(s)
        except Exception:
            return None

async def _url_to_data_uri(url: str) -> Optional[str]:
    """Download an image URL and return a base64 data URI Discord accepts."""
    url = (url or "").strip()
    if not url:
        return None
    if url.startswith("data:"):
        return url

    loop = asyncio.get_event_loop()

    def _download():
        req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _ur.urlopen(req, timeout=20) as r:
            return r.read(), r.headers.get("Content-Type", "")

    data, ct = await loop.run_in_executor(None, _download)
    if not data:
        return None
    if not ct or not ct.startswith("image"):

        ext = url.split("?")[0].rsplit(".", 1)[-1].lower()
        ct = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
              "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
    b64 = base64.b64encode(data).decode()
    return f"data:{ct};base64,{b64}"

class Profile(Cog):

    def __init__(self, bot):
        super().__init__(bot)

    async def _fetch_me(self) -> dict:
        try:
            return await self.bot._http.request(Route.me()) or {}
        except Exception:
            return {}

    async def _fetch_profile(self, uid) -> dict:
        try:
            data = await self.bot._http.request(Route.profile(int(uid))) or {}
            return data.get("user_profile") or {}
        except Exception:
            return {}

    async def snapshot(self) -> dict:
        me = await self._fetch_me()
        uid = me.get("id")
        prof = await self._fetch_profile(uid) if uid else {}
        avatar_url = None
        if me.get("avatar") and uid:
            ext = "gif" if str(me["avatar"]).startswith("a_") else "png"
            avatar_url = f"https://cdn.discordapp.com/avatars/{uid}/{me['avatar']}.{ext}?size=256"
        banner_url = None
        if me.get("banner") and uid:
            ext = "gif" if str(me["banner"]).startswith("a_") else "png"
            banner_url = f"https://cdn.discordapp.com/banners/{uid}/{me['banner']}.{ext}?size=600"
        accent = me.get("accent_color")
        return {
            "type": "profile_state",
            "profile": {
                "id": uid,
                "username": me.get("username", ""),
                "display_name": me.get("global_name") or "",
                "avatar_url": avatar_url,
                "banner_url": banner_url,
                "accent_color": accent,
                "accent_hex": (f"#{accent:06x}" if isinstance(accent, int) else ""),
                "bio": prof.get("bio", ""),
                "pronouns": prof.get("pronouns", ""),
            },
        }

    async def apply(self, fields: dict) -> dict:
        """Apply any subset of {display_name, avatar, banner, accent, bio, pronouns}.

        Returns {"changed": [...], "errors": [...]}.
        """
        changed: list = []
        errors: list = []
        if not isinstance(fields, dict):
            return {"changed": changed, "errors": ["bad payload"]}

        me_patch: dict = {}
        if "display_name" in fields:
            me_patch["global_name"] = str(fields["display_name"])[:32]
        if "accent" in fields or "accent_color" in fields:
            acc = _parse_accent(fields.get("accent", fields.get("accent_color")))
            if acc is not None:
                me_patch["accent_color"] = acc
            elif str(fields.get("accent", fields.get("accent_color")) or "").strip():
                errors.append("invalid accent colour")
        for key, api_key in (("avatar", "avatar"), ("banner", "banner")):
            if key in fields:
                raw = fields[key]
                if raw in (None, "", "remove", "clear"):
                    me_patch[api_key] = None
                else:
                    try:
                        uri = await _url_to_data_uri(str(raw))
                        if uri:
                            me_patch[api_key] = uri
                        else:
                            errors.append(f"{key}: could not load image")
                    except Exception as e:
                        errors.append(f"{key}: {e}")

        if me_patch:
            try:
                await self.bot._http.edit_profile(**me_patch)
                changed.extend(
                    {"global_name": "display name", "avatar": "avatar",
                     "banner": "banner", "accent_color": "accent"}[k]
                    for k in me_patch
                )
            except Exception as e:
                errors.append(f"account update failed: {e}")

        prof_patch: dict = {}
        if "bio" in fields:
            prof_patch["bio"] = str(fields["bio"])[:190]
        if "pronouns" in fields:
            prof_patch["pronouns"] = str(fields["pronouns"])[:40]
        if prof_patch:
            try:
                await self.bot._http.request(Route("PATCH", "/users/@me/profile"), json=prof_patch)
                if "bio" in prof_patch:
                    changed.append("bio")
                if "pronouns" in prof_patch:
                    changed.append("pronouns")
            except Exception as e:
                errors.append(f"profile update failed: {e}")

        return {"changed": changed, "errors": errors}

    async def _reply(self, ctx, text):
        _emit({"type": "command"})
        try:
            await ctx.message.delete()
        except Exception:
            pass
        m = None
        try:
            m = await ctx.send(text)
        except Exception:
            return
        if m is not None:
            async def _cleanup():
                await asyncio.sleep(15)
                try:
                    await m.delete()
                except Exception:
                    pass
            asyncio.create_task(_cleanup())

    async def _run(self, ctx, field: str, value: str, label: str):
        value = (value or "").strip()
        if not value and field not in ("avatar", "banner"):
            await self._reply(ctx, f"Usage: `{ctx.message.content.split()[0]} <{label}>`")
            return
        result = await self.apply({field: value})
        _emit(await self.snapshot())
        if result.get("errors"):
            await self._reply(ctx, "⚠️ " + "; ".join(result["errors"]))
        else:
            await self._reply(ctx, f"✅ {label.capitalize()} updated.")

    @command(name="setdisplayname", aliases=["setname", "setdisplay"])
    async def setdisplayname(self, ctx, *, value: str = ""):
        await self._run(ctx, "display_name", value, "display name")

    @command(name="setbio", aliases=["setabout"])
    async def setbio(self, ctx, *, value: str = ""):
        await self._run(ctx, "bio", value, "bio")

    @command(name="setpronouns")
    async def setpronouns(self, ctx, *, value: str = ""):
        await self._run(ctx, "pronouns", value, "pronouns")

    @command(name="setaccent", aliases=["setcolor", "setcolour"])
    async def setaccent(self, ctx, *, value: str = ""):
        await self._run(ctx, "accent", value, "accent colour")

    @command(name="setpfp", aliases=["setavatar"])
    async def setpfp(self, ctx, *, value: str = ""):
        await self._run(ctx, "avatar", value, "avatar URL (blank/`remove` to clear)")

    @command(name="setbanner")
    async def setbanner(self, ctx, *, value: str = ""):
        await self._run(ctx, "banner", value, "banner URL (blank/`remove` to clear)")

    @command(name="profile", aliases=["myprofile"])
    async def profile(self, ctx):
        snap = await self.snapshot()
        p = snap["profile"]
        _emit(snap)
        await self._reply(
            ctx,
            f"## {p['display_name'] or p['username']}\n"
            f"-# @{p['username']}\n"
            f"**Bio** {p['bio'] or '—'}\n"
            f"**Pronouns** {p['pronouns'] or '—'}\n"
            f"**Accent** {p['accent_hex'] or '—'}\n"
            "-# `.setpfp` · `.setbanner` · `.setbio` · `.setpronouns` · `.setdisplayname` · `.setaccent`"
        )

def setup(bot):
    bot.add_cog(Profile(bot))
