
"""
Beyond backend — hosts BOTH:
  - the selfbot  (modifyself, your account)   -> "." prefix commands + RPC cog
  - a real bot   (discord.py, its own token)  -> "/" slash commands (Components V2)

RPC is driven by rpc_cog.RPC (loaded as a modifyself cog) — the full engine:
image upload, presets, stack, rotation, platform / multi-platform spoofing.
The UI RPC tab drives the same cog instance.

stdio protocol (newline JSON):
  in : {"cmd":"login","token":...}
       {"cmd":"config","private":bool,"discoverable":bool,"botToken":...,"botAppId":...,"botGuild":...}
       {"cmd":"rpc","activity":{...},"status":"online"}  {"cmd":"rpcclear"}  {"cmd":"platform","value":"vr"}
       {"cmd":"refresh"} {"cmd":"logout"}
  out: {"type":"ready"|"stats"|"botinvite"|"botready"|"notif"|"latency"|"command"|"rpcok"|"log", ...}
"""

import asyncio
import json
import os
import sys
import traceback

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PREFIX = os.environ.get("BEYOND_PREFIX", ".")
NITRO = {0: "None", 1: "Nitro Classic", 2: "Nitro", 3: "Nitro Basic"}
ACCENT = 0x5B8CFF

CFG = {"private": False, "discoverable": True}
LAST_STATS = {}
OWNER_ID = None
BADGE_BITS = [1 << 0, 1 << 1, 1 << 2, 1 << 6, 1 << 7, 1 << 8, 1 << 9,
              1 << 3, 1 << 14, 1 << 17, 1 << 18, 1 << 22]

RPC_TYPES = ["playing", "listening", "watching", "streaming", "competing",
             "spotify", "youtube", "xbox", "playstation", "crunchyroll",
             "vrchat", "custom", "custom_status"]

_bot = None
_bot_task = None
_rpc_cog = None
_realbot = None
_realbot_task = None
_bot_app_id = None
_userapp_watch_task = None
_spotify_cog = None
_logger_cog = None
_profile_cog = None
_DISCOVER_RPC_KEY = "beyond_promo"

def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

def log(msg: str) -> None:
    emit({"type": "log", "msg": str(msg)})

def help_lines():
    return [
        ("Core", "`help` · `ping` · `stats`"),
        ("Presence", "`rpc <type> …` · `status <online|idle|dnd|invisible>` · `platform <vr|phone|…>`"),
        ("RPC extras", "`rpc preset` · `rpc rotation` · `rpc stack` · `multiplatform`"),
    ]

def help_text() -> str:
    out = ["## ⬜ Beyond", "-# selfbot + slash · v0.1.0"]
    for title, body in help_lines():
        out.append(f"**{title}**\n{body}")
    return "\n".join(out)

def ping_text(latency_s) -> str:
    return f"Pong — **{round((latency_s or 0) * 1000)}ms**"

def _presence_line() -> str:
    try:
        st = _rpc_cog._status if _rpc_cog else "online"
        act = list(_rpc_cog._active.keys()) if _rpc_cog else []
    except Exception:
        st, act = "online", []
    line = f"**Status** {st}"
    if act:
        line += f" · **RPC** {', '.join(act)}"
    return line

def stats_text() -> str:
    s = LAST_STATS
    if not s:
        return "No stats yet."
    handle = f"{s.get('username','')}#{s['discriminator']}" if s.get("discriminator") else f"@{s.get('username','')}"
    return (
        f"## {s.get('globalName','?')}\n"
        f"-# {handle}\n"
        f"**User ID** `{s.get('id','')}`\n"
        f"**Created** {s.get('created','?')}\n"
        f"**Servers** {s.get('servers',0)}  ·  **Friends** {s.get('friends',0)}\n"
        f"**Nitro** {s.get('nitro','None')}  ·  **Badges** {s.get('badges',0)}\n"
        f"{_presence_line()}"
    )

async def _api(bot, path: str):
    from modifyself.http.route import Route
    return await bot._http.request(Route("GET", path))

def _created_date(uid: str) -> str:
    try:
        import datetime
        ms = (int(uid) >> 22) + 1420070400000
        return datetime.datetime.utcfromtimestamp(ms / 1000).strftime("%b %d, %Y")
    except Exception:
        return "?"

def _avatar_url(u: dict) -> str:
    if u.get("avatar"):
        ext = "gif" if u["avatar"].startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{u['id']}/{u['avatar']}.{ext}?size=256"
    return f"https://cdn.discordapp.com/embed/avatars/{(int(u['id']) >> 22) % 6}.png"

async def ensure_asset_channel(bot):
    """Make sure the RPC cog has a channel it can actually post images to.

    The cog reads persistence['rpc_asset_channel']; its default is the dev's
    channel (which other accounts 404 on). We pick a channel in a server the
    logged-in account OWNS — owners can always post — and cache it.
    """
    try:
        import persistence
    except Exception:
        return None
    cur = persistence.get("rpc_asset_channel")
    if cur and cur != "1477758738772525239":
        return cur
    try:
        guilds = await _api(bot, "/users/@me/guilds") or []
    except Exception as e:
        log(f"asset channel: guild fetch failed: {e}")
        return None

    ordered = [g for g in guilds if g.get("owner")] + [g for g in guilds if not g.get("owner")]
    for g in ordered:
        try:
            chans = await _api(bot, f"/guilds/{g['id']}/channels") or []
        except Exception:
            continue
        for ch in chans:
            if ch.get("type") == 0:
                cid = str(ch["id"])
                persistence.set_key("rpc_asset_channel", cid)
                log(f"asset channel -> #{ch.get('name')} ({cid}) in "
                    f"{g.get('name')}{' [owned]' if g.get('owner') else ''}")
                return cid
    log("asset channel: no postable channel found — set one in the RPC tab")
    return None

async def build_stats(bot) -> dict:
    u = await _api(bot, "/users/@me")
    if not isinstance(u, dict) or "id" not in u:
        raise RuntimeError("Invalid token")
    servers = friends = 0
    try:
        g = await _api(bot, "/users/@me/guilds")
        if isinstance(g, list):
            servers = len(g)
    except Exception:
        pass
    try:
        rels = await _api(bot, "/users/@me/relationships")
        if isinstance(rels, list):
            friends = sum(1 for x in rels if x.get("type") == 1)
    except Exception:
        pass
    disc = u.get("discriminator")
    stats = {
        "id": u["id"], "username": u.get("username", ""),
        "globalName": u.get("global_name") or u.get("username", ""),
        "discriminator": disc if disc and disc != "0" else None,
        "avatarUrl": _avatar_url(u), "publicFlags": u.get("public_flags", 0),
        "nitro": NITRO.get(u.get("premium_type", 0), "None"),
        "nitroActive": (u.get("premium_type", 0) or 0) > 0,
        "servers": servers, "friends": friends,
        "created": _created_date(u["id"]),
        "badges": sum(1 for b in BADGE_BITS if (u.get("public_flags", 0) & b)),
    }
    LAST_STATS.clear(); LAST_STATS.update(stats)
    return stats

def ui_to_cmd(ui: dict) -> dict:
    c = dict(ui)
    li = ui.get("large_image")
    if li:
        c["image"] = li
        c["imglink"] = li

    b, bu = [], []
    if ui.get("button1") and ui.get("button1_url"):
        b.append(ui["button1"]); bu.append(ui["button1_url"])
    if ui.get("button2") and ui.get("button2_url"):
        b.append(ui["button2"]); bu.append(ui["button2_url"])
    if b:
        c["buttons"] = b
        c["button_urls"] = bu
    return c

async def _respond(ctx, text):
    emit({"type": "command"})
    try:
        m = await ctx.reply(text)
    except Exception as e:
        log(f"reply failed: {e}")
        try:
            m = await ctx.send(text)
        except Exception as e2:
            log(f"send fallback failed: {e2}")
            return
    if CFG.get("private") and m is not None:
        async def _cleanup():
            await asyncio.sleep(8)
            try:
                await m.delete()
            except Exception:
                pass
        asyncio.create_task(_cleanup())

def register_commands(bot):
    @bot.command(name="help", aliases=["cmds", "commands"])
    async def _help(ctx):
        await _respond(ctx, help_text())

    @bot.command(name="ping")
    async def _ping(ctx):
        await _respond(ctx, ping_text(bot.latency))

    @bot.command(name="stats")
    async def _stats(ctx):
        await _respond(ctx, stats_text())

async def run_selfbot(bot):
    register_commands(bot)

    @bot.event
    async def on_ready(user=None):
        name = None
        try:
            name = str(bot.user) if bot.user else None
        except Exception:
            pass
        emit({"type": "notif", "kind": "ok",
              "msg": f"Gateway connected{f' as {name}' if name else ''}"})
        log(f"READY (user={name}) — commands live with prefix '{PREFIX}'")

        async def heartbeat():
            while True:
                await asyncio.sleep(20)
                try:
                    emit({"type": "latency", "ms": round((bot.latency or 0) * 1000)})
                except Exception:
                    pass
        asyncio.create_task(heartbeat())

    @bot.event
    async def on_message(message):
        try:
            me = bot.user
            if not me:
                return
            content = message.content or ""
            author_id = getattr(message.author, "id", None)
            if author_id == me.id:
                return
            ids = [getattr(x, "id", None) for x in (message.mentions or [])]
            if me.id in ids:
                who = (getattr(message.author, "display_name", None)
                       or getattr(message.author, "name", "someone"))
                emit({"type": "notif", "kind": "info",
                      "msg": f"You got pinged by {who} | {content[:80]}"})
        except Exception as e:
            log(f"on_message error: {e}")

    try:
        log("selfbot: connecting gateway...")
        await bot.start()
    except Exception as e:
        emit({"type": "notif", "kind": "err", "msg": f"Gateway error: {e}"})
        log("gateway traceback:\n" + traceback.format_exc())

def build_v2_view(discord, kind: str):
    ui = discord.ui
    try:
        view = ui.LayoutView()
        container = ui.Container(accent_colour=discord.Colour(ACCENT))
        if kind == "help":
            container.add_item(ui.TextDisplay("## ⬜  Beyond"))
            container.add_item(ui.TextDisplay("-# selfbot + slash · v0.1.0"))
            container.add_item(ui.Separator())
            for title, body in help_lines():
                container.add_item(ui.TextDisplay(f"**{title}**\n{body}"))
        elif kind == "ping":
            container.add_item(ui.TextDisplay("## \U0001f4e1  Pong"))
            container.add_item(ui.Separator())
            container.add_item(ui.TextDisplay(ping_text(_realbot.latency if _realbot else 0)))
        elif kind == "stats":
            s = LAST_STATS
            handle = (f"{s.get('username','')}#{s['discriminator']}"
                      if s.get("discriminator") else f"@{s.get('username','')}")
            head = f"## {s.get('globalName','?')}\n-# {handle}"
            av = s.get("avatarUrl")
            if av:
                section = ui.Section(accessory=ui.Thumbnail(media=av))
                section.add_item(ui.TextDisplay(head))
                container.add_item(section)
            else:
                container.add_item(ui.TextDisplay(head))
            container.add_item(ui.Separator())
            container.add_item(ui.TextDisplay(
                f"**User ID**\n`{s.get('id','')}`\n\n"
                f"**Created**  {s.get('created','?')}\n"
                f"**Servers**  {s.get('servers',0)}    **Friends**  {s.get('friends',0)}\n"
                f"**Nitro**  {s.get('nitro','None')}    **Badges**  {s.get('badges',0)}"))
            container.add_item(ui.Separator())
            container.add_item(ui.TextDisplay(_presence_line()))
        else:
            return None
        view.add_item(container)
        return view
    except Exception as e:
        log(f"v2 view build failed ({kind}): {e}")
        return None

async def start_realbot(token: str, app_id: str, guild_id: str = ""):
    global _realbot
    try:
        import discord
        from discord import app_commands
    except Exception as e:
        emit({"type": "notif", "kind": "warn", "msg": f"discord.py import failed: {e}"})
        log("discord import traceback:\n" + traceback.format_exc())
        return

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)
    _realbot = client

    async def _owner_only(interaction):
        if OWNER_ID is not None and interaction.user.id == OWNER_ID:
            return True
        try:
            await interaction.response.send_message(
                "\U0001f6e0️  **Beyond** is still in development — it'll be downloadable soon.",
                ephemeral=True)
        except Exception:
            pass
        return False
    tree.interaction_check = _owner_only

    @tree.error
    async def _tree_error(interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            return
        log(f"slash command error: {error}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("Something went wrong.", ephemeral=True)
        except Exception:
            pass

    def user_installable(func):
        try:
            func = app_commands.allowed_installs(guilds=True, users=True)(func)
            func = app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)(func)
        except Exception:
            pass
        return func

    async def _reply_v2(interaction, kind, fallback_text):
        emit({"type": "command"})
        eph = bool(CFG.get("private"))
        view = build_v2_view(discord, kind)
        try:
            if view is not None:
                await interaction.response.send_message(view=view, ephemeral=eph)
            else:
                await interaction.response.send_message(fallback_text, ephemeral=eph)
        except Exception as e:
            log(f"slash reply failed ({kind}): {e}")
            try:
                await interaction.response.send_message(fallback_text, ephemeral=eph)
            except Exception:
                pass

    @tree.command(name="ping", description="Show gateway latency")
    @user_installable
    async def _ping(interaction):
        await _reply_v2(interaction, "ping", ping_text(client.latency))

    @tree.command(name="help", description="Show Beyond commands")
    @user_installable
    async def _help(interaction):
        await _reply_v2(interaction, "help", help_text())

    @tree.command(name="stats", description="Show account stats")
    @user_installable
    async def _stats(interaction):
        await _reply_v2(interaction, "stats", stats_text())

    from typing import Literal, Optional as _Opt

    async def _rpc_reply(interaction, text):
        emit({"type": "command"})
        try:
            await interaction.response.send_message(text, ephemeral=bool(CFG.get("private")))
        except Exception:
            pass

    def _need_selfbot():
        return _rpc_cog is None or _bot is None

    @tree.command(name="rpc", description="Set your account's rich presence")
    @user_installable
    @app_commands.describe(
        type="Activity type", name="Activity name", details="Line 1", state="Line 2",
        large_image="Large image URL (any URL or Discord CDN)", large_text="Large image hover text",
        small_image="Small image URL", small_text="Small image hover text",
        elapsed="Elapsed minutes", total="Total minutes (blank = count up)",
        button1="Button 1 label", button1_url="Button 1 URL",
        button2="Button 2 label", button2_url="Button 2 URL",
        stream_url="Stream URL (streaming type)", text="Text (custom_status)", emoji="Emoji (custom_status)")
    async def _rpc(interaction,
                   type: Literal["playing", "listening", "watching", "streaming", "competing",
                                 "spotify", "youtube", "xbox", "playstation", "crunchyroll",
                                 "vrchat", "custom", "custom_status"],
                   name: _Opt[str] = None, details: _Opt[str] = None, state: _Opt[str] = None,
                   large_image: _Opt[str] = None, large_text: _Opt[str] = None,
                   small_image: _Opt[str] = None, small_text: _Opt[str] = None,
                   elapsed: _Opt[float] = None, total: _Opt[float] = None,
                   button1: _Opt[str] = None, button1_url: _Opt[str] = None,
                   button2: _Opt[str] = None, button2_url: _Opt[str] = None,
                   stream_url: _Opt[str] = None, text: _Opt[str] = None, emoji: _Opt[str] = None):
        if _need_selfbot():
            await _rpc_reply(interaction, "Log into your account in Beyond first — presence runs through the selfbot.")
            return
        ui = {"rpc_type": type}
        for k, v in (("name", name), ("details", details), ("state", state),
                     ("large_image", large_image), ("large_text", large_text),
                     ("small_image", small_image), ("small_text", small_text),
                     ("button1", button1), ("button1_url", button1_url),
                     ("button2", button2), ("button2_url", button2_url),
                     ("stream_url", stream_url), ("text", text), ("emoji", emoji)):
            if v:
                ui[k] = v
        if elapsed is not None:
            ui["elapsed_minutes"] = elapsed
        if total is not None:
            ui["total_minutes"] = total
        try:
            if ui.get("large_image") or ui.get("small_image"):
                await ensure_asset_channel(_bot)
            c2 = ui_to_cmd(ui)
            _rpc_cog._stop_rotation(type)
            _rpc_cog._active[type] = c2
            _rpc_cog._save_rpc()
            await _rpc_cog._build_and_send(c2)
            emit({"type": "rpcok", "ok": True, "active": list(_rpc_cog._active.keys()), "status": _rpc_cog._status})
            await _rpc_reply(interaction, f"Rich presence applied: **{type}**")
        except Exception as e:
            await _rpc_reply(interaction, f"RPC failed: {e}")
            log("slash rpc traceback:\n" + traceback.format_exc())

    @tree.command(name="rpcclear", description="Clear your rich presence")
    @user_installable
    async def _rpcclear(interaction):
        if _need_selfbot():
            await _rpc_reply(interaction, "Log into your account in Beyond first.")
            return
        try:
            for r in list(_rpc_cog._rotation_tasks):
                _rpc_cog._stop_rotation(r)
            _rpc_cog._active.clear()
            _rpc_cog._save_rpc()
            await _rpc_cog._send_payload([])
            emit({"type": "rpcok", "ok": True, "active": [], "status": _rpc_cog._status})
            await _rpc_reply(interaction, "Rich presence cleared.")
        except Exception as e:
            await _rpc_reply(interaction, f"Failed: {e}")

    @tree.command(name="status", description="Set your presence status")
    @user_installable
    async def _status(interaction, status: Literal["online", "idle", "dnd", "invisible"]):
        if _need_selfbot():
            await _rpc_reply(interaction, "Log into your account in Beyond first.")
            return
        try:
            _rpc_cog._status = status
            acts = [a for a in [await _rpc_cog._build_activity(cc) for cc in _rpc_cog._active.values()] if a]
            await _rpc_cog._send_payload(acts)
            emit({"type": "rpcok", "ok": True, "active": list(_rpc_cog._active.keys()), "status": status})
            await _rpc_reply(interaction, f"Status set to **{status}**.")
        except Exception as e:
            await _rpc_reply(interaction, f"Failed: {e}")

    @tree.command(name="platform", description="Spoof the platform your account appears on")
    @user_installable
    async def _platform(interaction,
                        platform: Literal["desktop", "web", "phone", "android",
                                          "xbox", "console", "vr", "off"]):
        if _need_selfbot():
            await _rpc_reply(interaction, "Log into your account in Beyond first.")
            return
        try:
            import rpc_cog
            rpc_cog.set_active_platform(platform)
            try:
                import persistence
                persistence.set_key("platform", platform)
            except Exception:
                pass
            await _rpc_cog._gw_reconnect()
            await _rpc_reply(interaction, f"Platform set to **{platform}** — reconnecting gateway.")
        except Exception as e:
            await _rpc_reply(interaction, f"Failed: {e}")

    @tree.command(name="multiplatform", description="Appear on several platforms at once (comma-separated, or 'off')")
    @user_installable
    @app_commands.describe(platforms="e.g. desktop,phone,vr  — or 'off' to stop")
    async def _multiplatform(interaction, platforms: str):
        if _need_selfbot():
            await _rpc_reply(interaction, "Log into your account in Beyond first.")
            return
        try:
            import rpc_cog
            rest = (platforms or "").strip().lower()
            for nm, task in list(_rpc_cog._extra_gws.items()):
                obj = _rpc_cog._extra_gw_objs.pop(nm, None)
                if obj:
                    await obj.close()
                task.cancel()
            _rpc_cog._extra_gws.clear()
            if rest in ("off", "stop", "clear", ""):
                try:
                    import persistence
                    persistence.set_key("multiplatform", [])
                except Exception:
                    pass
                await _rpc_reply(interaction, "Extra platform gateways closed.")
                return
            parts = [p.strip() for p in rest.split(",") if p.strip()]
            bad = [p for p in parts if p not in rpc_cog._PLATFORM_PROPS]
            if bad:
                await _rpc_reply(interaction, f"Unknown: {', '.join(bad)} — valid: {', '.join(rpc_cog._PLATFORM_PROPS)}")
                return
            token = _bot._http.token
            for nm in parts:
                obj = rpc_cog._PlatformGateway(token, rpc_cog._PLATFORM_PROPS[nm])
                task = asyncio.ensure_future(obj.start())
                _rpc_cog._extra_gw_objs[nm] = obj
                _rpc_cog._extra_gws[nm] = task
            try:
                import persistence
                persistence.set_key("multiplatform", parts)
            except Exception:
                pass
            await _rpc_reply(interaction, f"Now appearing on: **{', '.join(parts)}** ({len(parts)} gateways).")
        except Exception as e:
            await _rpc_reply(interaction, f"Failed: {e}")

    @tree.command(name="spotifylyrics", description="Sync Spotify lyrics to your status")
    @user_installable
    async def _spotifylyrics(interaction, enabled: Literal["on", "off"]):
        if _spotify_cog is None:
            await _rpc_reply(interaction, "Log into your account in Beyond first.")
            return
        try:
            if enabled == "on":
                _spotify_cog.start()
                emit({"type": "spotify_state", "enabled": True})
                await _rpc_reply(interaction, "Spotify lyrics **on** — play a song.")
            else:
                _spotify_cog.stop()
                emit({"type": "spotify_state", "enabled": False})
                await _rpc_reply(interaction, "Spotify lyrics **off**.")
        except Exception as e:
            await _rpc_reply(interaction, f"Failed: {e}")

    @tree.command(name="logger", description="Control the Beyond message logger")
    @user_installable
    @app_commands.describe(
        action="What to do", value="keyword to add/remove, or scope id (guild/channel)",
        scope="Where to watch (only for action=scope)")
    async def _logger(interaction,
                      action: Literal["on", "off", "status", "add", "remove", "scope"],
                      value: _Opt[str] = None,
                      scope: _Opt[Literal["all", "dms", "guilds", "guild", "channel"]] = None):
        if _logger_cog is None:
            await _rpc_reply(interaction, "Log into your account in Beyond first.")
            return
        try:
            if action == "on":
                _logger_cog.apply_config({"enabled": True})
                emit(_logger_cog.state())
                await _rpc_reply(interaction, "📥 Message logger **on**.")
            elif action == "off":
                _logger_cog.apply_config({"enabled": False})
                emit(_logger_cog.state())
                await _rpc_reply(interaction, "📥 Message logger **off**.")
            elif action == "add" and value:
                _logger_cog.add_keyword(value)
                emit(_logger_cog.state())
                await _rpc_reply(interaction, f"Tracking keyword: **{value}**")
            elif action == "remove" and value:
                ok = _logger_cog.remove_keyword(value)
                emit(_logger_cog.state())
                await _rpc_reply(interaction, f"{'Removed' if ok else 'Not tracking'}: **{value}**")
            elif action == "scope":
                mode = scope or "all"
                patch = {"scope": {"mode": mode}}
                if mode == "guild":
                    patch["scope"]["guild_id"] = value or ""
                elif mode == "channel":
                    patch["scope"]["channel_id"] = value or ""
                _logger_cog.apply_config(patch)
                emit(_logger_cog.state())
                await _rpc_reply(interaction, f"Scope set to **{mode}**{f' ({value})' if value else ''}.")
            else:
                cfg = _logger_cog.cfg
                kw = ", ".join(cfg["keywords"]) or "none"
                await _rpc_reply(
                    interaction,
                    f"📥 **Logger** {'on' if cfg['enabled'] else 'off'} · scope **{cfg['scope']['mode']}**\n"
                    f"mentions {cfg['mentions']} · deletes {cfg['deletes']} · edits {cfg['edits']}\n"
                    f"keywords: {kw}")
        except Exception as e:
            await _rpc_reply(interaction, f"Failed: {e}")

    @tree.command(name="profile", description="Update your account profile")
    @user_installable
    @app_commands.describe(
        display_name="New display name", bio="About Me", pronouns="Pronouns",
        avatar="Avatar image URL", banner="Banner image URL",
        accent="Accent colour hex (e.g. #5b8cff)")
    async def _profile(interaction,
                       display_name: _Opt[str] = None, bio: _Opt[str] = None,
                       pronouns: _Opt[str] = None, avatar: _Opt[str] = None,
                       banner: _Opt[str] = None, accent: _Opt[str] = None):
        if _profile_cog is None:
            await _rpc_reply(interaction, "Log into your account in Beyond first.")
            return
        fields = {}
        for k, v in (("display_name", display_name), ("bio", bio), ("pronouns", pronouns),
                     ("avatar", avatar), ("banner", banner), ("accent", accent)):
            if v is not None:
                fields[k] = v
        if not fields:
            await _rpc_reply(interaction, "Pass at least one field to change.")
            return
        try:
            result = await _profile_cog.apply(fields)
            emit(await _profile_cog.snapshot())
            if result.get("errors"):
                await _rpc_reply(interaction, "⚠️ " + "; ".join(result["errors"]))
            else:
                await _rpc_reply(interaction, "✅ Profile updated: " + ", ".join(result.get("changed") or ["nothing"]))
        except Exception as e:
            await _rpc_reply(interaction, f"Failed: {e}")

    @client.event
    async def on_ready():

        try:
            g = await tree.sync()
            emit({"type": "notif", "kind": "ok",
                  "msg": f"Slash commands synced globally ({len(g)}) — work in DMs & anywhere (up to ~1h to propagate)"})
        except Exception as e:
            emit({"type": "notif", "kind": "warn", "msg": f"Global slash sync failed: {e}"})

        gid = (guild_id or "").strip()
        if gid:
            try:
                guild = discord.Object(id=int(gid))
                tree.clear_commands(guild=guild)
                await tree.sync(guild=guild)
                emit({"type": "notif", "kind": "info",
                      "msg": f"Cleared guild-scoped command copies in {gid} (removes duplicates)"})
            except Exception as e:
                emit({"type": "notif", "kind": "warn", "msg": f"Guild cleanup failed: {e}"})
        emit({"type": "botready", "name": str(client.user)})
        emit({"type": "notif", "kind": "ok", "msg": f"Real bot online as {client.user}"})

    try:
        await client.start(token)
    except Exception as e:
        emit({"type": "notif", "kind": "err", "msg": f"Bot login failed: {e}"})
        log("realbot traceback:\n" + traceback.format_exc())

def invite_url(app_id: str) -> str:
    return (f"https://discord.com/oauth2/authorize?client_id={app_id}"
            f"&integration_type=1&scope=applications.commands")

async def watch_userapp(app_id: str):
    """Poll the account's authorized apps and alert if the Beyond user-app is
    removed (so / commands would stop working). Discord has no reliable gateway
    event for user-app removal, so this checks /oauth2/tokens periodically."""
    prev_present = None
    while True:
        await asyncio.sleep(60)
        if _bot is None:
            continue
        try:
            toks = await _api(_bot, "/oauth2/tokens")
            present = any(
                str((t.get("application") or {}).get("id")) == str(app_id)
                for t in (toks or [])
            )
        except Exception as e:
            log(f"userapp watch failed: {e}")
            continue
        if prev_present is None:
            prev_present = present
            continue
        if prev_present and not present:
            emit({"type": "notif", "kind": "warn",
                  "msg": "Your Beyond user-app was removed from your account — "
                         "re-add it to keep / commands working."})
            emit({"type": "botinvite", "invite": invite_url(app_id)})
        prev_present = present

def _promo_cmd() -> dict:
    """The VRChat-spoof presence applied while 'discoverable' is ON."""
    return {
        "rpc_type": "vrchat",
        "name": "VRChat",
        "state": "Using Beyond Selfbot",
        "large_image": "https://media.discordapp.net/attachments/1549058469775147058/1552277021751640104/IMG_2414.jpg?ex=6ab50621&is=6ab3b4a1&hm=3642875e57eee0268db249ba571f944a4d370ae1226ae315e2116ef882380c6f&=&format=webp",
        "large_text": "Beyond Selfbot",
        "buttons": ["get it now"],
        "button_urls": ["https://github.com/kzfq/beyond"],
    }

async def apply_discoverable(on: bool) -> None:
    """Turn the Beyond promo presence on/off through the RPC cog.

    ON  -> stack a VRChat activity ("Using Beyond Selfbot" + a 'get it now'
           button linking the repo) alongside whatever else is active.
    OFF -> remove just that promo activity, leaving other RPC untouched.
    """
    if _rpc_cog is None:
        return
    try:
        if on:
            c2 = ui_to_cmd(_promo_cmd())
            _rpc_cog._active[_DISCOVER_RPC_KEY] = c2
            _rpc_cog._save_rpc()
            acts = [a for a in [await _rpc_cog._build_activity(x)
                                for x in _rpc_cog._active.values()] if a]
            await _rpc_cog._send_payload(acts)
        else:
            if _DISCOVER_RPC_KEY in _rpc_cog._active:
                _rpc_cog._active.pop(_DISCOVER_RPC_KEY, None)
                _rpc_cog._save_rpc()
                acts = [a for a in [await _rpc_cog._build_activity(x)
                                    for x in _rpc_cog._active.values()] if a]
                await _rpc_cog._send_payload(acts)
        emit({"type": "rpcok", "ok": True,
              "active": list(_rpc_cog._active.keys()), "status": _rpc_cog._status})
    except Exception as e:
        log(f"discoverable apply failed: {e}\n" + traceback.format_exc())

async def handle(cmd: dict, state: dict):
    global _bot, _bot_task, _rpc_cog, _realbot_task, OWNER_ID, _bot_app_id, _userapp_watch_task, _spotify_cog
    global _logger_cog, _profile_cog
    c = cmd.get("cmd")

    if c == "login":
        token = (cmd.get("token") or "").strip()
        state["token"] = token
        try:
            import modifyself
            log(f"modifyself version: {getattr(modifyself, '__version__', 'unknown')}")
            from modifyself import Client
        except Exception:
            emit({"type": "login_error", "msg": "modifyself not installed — run: pip install modifyself"})
            return
        try:
            if _bot is None:
                _bot = Client(token=token, command_prefix=PREFIX, notifications=False)

                try:
                    import rpc_cog
                    _rpc_cog = rpc_cog.RPC(_bot)
                    _bot.add_cog(_rpc_cog)
                    log("RPC cog loaded (rpc/status/platform/multiplatform + presets/rotation/stack)")
                except Exception as e:
                    _rpc_cog = None
                    emit({"type": "notif", "kind": "warn", "msg": f"RPC engine failed to load: {e}"})
                    log("rpc cog traceback:\n" + traceback.format_exc())

                try:
                    import spotify_cog
                    spotify_cog.EMIT = emit
                    _spotify_cog = spotify_cog.SpotifyLyrics(_bot)
                    _bot.add_cog(_spotify_cog)
                    log("Spotify lyrics cog loaded")
                except Exception as e:
                    _spotify_cog = None
                    log(f"spotify cog failed to load: {e}\n" + traceback.format_exc())

                try:
                    import logger_cog
                    logger_cog.EMIT = emit
                    _logger_cog = logger_cog.MessageLogger(_bot)
                    _bot.add_cog(_logger_cog)
                    log("Message logger cog loaded")
                except Exception as e:
                    _logger_cog = None
                    log(f"logger cog failed to load: {e}\n" + traceback.format_exc())

                try:
                    import profile_cog
                    profile_cog.EMIT = emit
                    _profile_cog = profile_cog.Profile(_bot)
                    _bot.add_cog(_profile_cog)
                    log("Profile cog loaded")
                except Exception as e:
                    _profile_cog = None
                    log(f"profile cog failed to load: {e}\n" + traceback.format_exc())
            stats = await build_stats(_bot)
        except Exception as e:
            emit({"type": "login_error", "msg": str(e)})
            log("login traceback:\n" + traceback.format_exc())
            _bot = None
            return
        try:
            OWNER_ID = int(stats["id"])
        except Exception:
            OWNER_ID = None
        emit({"type": "ready", "data": stats})

        if _logger_cog is not None:
            try:
                emit(_logger_cog.state())
            except Exception:
                pass

        if _profile_cog is not None:
            try:
                emit(await _profile_cog.snapshot())
            except Exception:
                pass
        if _bot_task is None:
            _bot_task = asyncio.create_task(run_selfbot(_bot))

    elif c in ("refresh", "snapshot"):

        if _bot is not None:
            try:
                stats = await build_stats(_bot)
                emit({"type": "ready", "data": stats})
                emit({"type": "stats", "data": stats})
            except Exception as e:
                log(f"refresh failed: {e}")
            if _logger_cog is not None:
                try:
                    emit(_logger_cog.state())
                except Exception:
                    pass
            if _profile_cog is not None:
                try:
                    emit(await _profile_cog.snapshot())
                except Exception:
                    pass
            if _rpc_cog is not None:
                try:
                    emit({"type": "rpcok", "ok": True,
                          "active": list(_rpc_cog._active.keys()), "status": _rpc_cog._status})
                except Exception:
                    pass

    elif c == "rpc":
        if _rpc_cog is None:
            emit({"type": "notif", "kind": "warn", "msg": "RPC engine not loaded — log in first."})
            return
        ui = cmd.get("activity") or {}
        status = cmd.get("status")
        rt = (ui.get("rpc_type") or "").lower()
        if status:
            _rpc_cog._status = status

        ac = (cmd.get("assetChannel") or "").strip()
        if ac:
            try:
                import persistence
                persistence.set_key("rpc_asset_channel", ac)
            except Exception:
                pass
        elif ui.get("large_image") or ui.get("small_image"):
            await ensure_asset_channel(_bot)
        try:
            if rt == "__status_only__":
                acts = [a for a in [await _rpc_cog._build_activity(x) for x in _rpc_cog._active.values()] if a]
                await _rpc_cog._send_payload(acts)
            elif rt == "clear":
                for r in list(_rpc_cog._rotation_tasks):
                    _rpc_cog._stop_rotation(r)
                _rpc_cog._active.clear()
                _rpc_cog._save_rpc()
                await _rpc_cog._send_payload([])
            else:
                c2 = ui_to_cmd(ui)
                _rpc_cog._stop_rotation(rt)
                _rpc_cog._active[rt] = c2
                _rpc_cog._save_rpc()
                await _rpc_cog._build_and_send(c2)
            emit({"type": "rpcok", "ok": True,
                  "active": list(_rpc_cog._active.keys()), "status": _rpc_cog._status})
            if rt not in ("__status_only__",):
                emit({"type": "notif", "kind": "ok",
                      "msg": f"RPC {'cleared' if rt == 'clear' else 'applied: ' + rt}"})
        except Exception as e:
            emit({"type": "notif", "kind": "err", "msg": f"RPC error: {e}"})
            log("rpc traceback:\n" + traceback.format_exc())

    elif c == "rpcclear":
        if _rpc_cog is not None:
            try:
                for r in list(_rpc_cog._rotation_tasks):
                    _rpc_cog._stop_rotation(r)
                _rpc_cog._active.clear()
                _rpc_cog._save_rpc()
                await _rpc_cog._send_payload([])
                emit({"type": "rpcok", "ok": True, "active": [], "status": _rpc_cog._status})
                emit({"type": "notif", "kind": "ok", "msg": "Rich presence cleared."})
            except Exception as e:
                log(f"rpcclear failed: {e}")

    elif c == "platform":
        val = (cmd.get("value") or "").strip().lower()
        if _rpc_cog is None:
            emit({"type": "notif", "kind": "warn", "msg": "Log in first to set platform."})
            return
        try:
            import rpc_cog
            if val in rpc_cog._PLATFORM_PROPS:
                rpc_cog.set_active_platform(val)
                try:
                    import persistence
                    persistence.set_key("platform", val)
                except Exception:
                    pass
                await _rpc_cog._gw_reconnect()
                emit({"type": "notif", "kind": "ok", "msg": f"Platform set to {val} — reconnecting gateway"})
            else:
                emit({"type": "notif", "kind": "warn",
                      "msg": f"Unknown platform '{val}' — valid: {', '.join(rpc_cog._PLATFORM_PROPS)}"})
        except Exception as e:
            emit({"type": "notif", "kind": "err", "msg": f"Platform error: {e}"})
            log("platform traceback:\n" + traceback.format_exc())

    elif c == "config":
        CFG["private"] = bool(cmd.get("private", CFG["private"]))
        prev_disc = CFG["discoverable"]
        CFG["discoverable"] = bool(cmd.get("discoverable", CFG["discoverable"]))

        if "discoverable" in cmd and CFG["discoverable"] != prev_disc:
            await apply_discoverable(CFG["discoverable"])
            emit({"type": "notif", "kind": "ok",
                  "msg": ("Discoverable on — showing 'Using Beyond Selfbot'"
                          if CFG["discoverable"] else "Discoverable off — promo presence removed")})
        bt = (cmd.get("botToken") or "").strip()
        ba = (cmd.get("botAppId") or "").strip()
        bg = (cmd.get("botGuild") or "").strip()

        if ba and cmd.get("openInvite"):
            emit({"type": "botinvite", "invite": invite_url(ba)})
        if ba:
            _bot_app_id = ba
        task_dead = (_realbot_task is None) or _realbot_task.done()
        if bt and ba and task_dead:
            emit({"type": "notif", "kind": "info", "msg": "Connecting real bot..."})
            _realbot_task = asyncio.create_task(start_realbot(bt, ba, bg))

            if _userapp_watch_task is None or _userapp_watch_task.done():
                _userapp_watch_task = asyncio.create_task(watch_userapp(ba))
        elif bt and ba and not task_dead:
            emit({"type": "notif", "kind": "info",
                  "msg": "Real bot already connecting/online — if stuck, close any hostbot.py and relaunch Beyond."})

    elif c == "spotify":
        if _spotify_cog is None:
            emit({"type": "notif", "kind": "warn", "msg": "Spotify engine not loaded — log in first."})
            return
        if cmd.get("on"):
            _spotify_cog.start()
            emit({"type": "spotify_state", "enabled": True})
            emit({"type": "notif", "kind": "ok", "msg": "Spotify lyrics on — play a song."})
        else:
            _spotify_cog.stop()
            emit({"type": "spotify_state", "enabled": False})
            emit({"type": "notif", "kind": "info", "msg": "Spotify lyrics off."})

    elif c == "logger":
        if _logger_cog is None:
            emit({"type": "notif", "kind": "warn", "msg": "Message logger not loaded — log in first."})
            return
        action = cmd.get("action") or "get"
        try:
            if action == "get":
                pass
            elif action == "config":
                _logger_cog.apply_config(cmd.get("config") or {})
            elif action == "add":
                _logger_cog.add_keyword(cmd.get("word") or "")
            elif action == "remove":
                _logger_cog.remove_keyword(cmd.get("word") or "")
            elif action == "clear":
                _logger_cog.clear_feed()
            emit(_logger_cog.state())
        except Exception as e:
            emit({"type": "notif", "kind": "err", "msg": f"Logger error: {e}"})
            log("logger traceback:\n" + traceback.format_exc())

    elif c == "profile":
        if _profile_cog is None:
            emit({"type": "notif", "kind": "warn", "msg": "Profile engine not loaded — log in first."})
            return
        action = cmd.get("action") or "get"
        try:
            if action == "get":
                emit(await _profile_cog.snapshot())
            else:
                result = await _profile_cog.apply(cmd.get("fields") or {})
                emit(await _profile_cog.snapshot())
                if result.get("errors"):
                    emit({"type": "notif", "kind": "warn",
                          "msg": "Profile: " + "; ".join(result["errors"])})
                if result.get("changed"):
                    emit({"type": "notif", "kind": "ok",
                          "msg": "Profile updated: " + ", ".join(result["changed"])})
                elif not result.get("errors"):
                    emit({"type": "notif", "kind": "info", "msg": "Profile: nothing to change."})
        except Exception as e:
            emit({"type": "notif", "kind": "err", "msg": f"Profile error: {e}"})
            log("profile traceback:\n" + traceback.format_exc())

    elif c == "admin":
        rid = cmd.get("_rid")
        base = (cmd.get("baseUrl") or "").rstrip("/")
        key = cmd.get("key") or ""
        path = cmd.get("path") or ""
        query = cmd.get("query") or ""
        if not base or not key:
            emit({"type": "admin_result", "id": rid, "ok": False, "status": 0,
                  "error": "Set the Base URL and Admin key first."})
            return
        url = base + path + query
        try:
            import aiohttp
            async with aiohttp.ClientSession() as _s:
                async with _s.get(url, headers={"X-API-Key": key, "Accept": "application/json"}) as r:
                    text = await r.text()
                    try:
                        data = json.loads(text)
                    except Exception:
                        data = text
                    emit({"type": "admin_result", "id": rid, "ok": r.status < 400,
                          "status": r.status, "data": data})
        except Exception as e:
            emit({"type": "admin_result", "id": rid, "ok": False, "status": 0, "error": str(e)})

    elif c == "logout":
        os._exit(0)

async def main():
    state = {}
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except Exception:
            cmd = {"cmd": "login", "token": line}
        try:
            await handle(cmd, state)
        except Exception as e:
            emit({"type": "log", "msg": f"handler error: {e}"})
            log(traceback.format_exc())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
