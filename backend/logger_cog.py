"""
Beyond — Message Logger cog (modifyself).

Watches the account's own gateway stream and surfaces:
  - keyword hits   (any word/phrase you're tracking appears in a message)
  - mention hits   (someone pings you)
  - deleted msgs   (with the original content, from a local rolling cache)
  - edited msgs    (before -> after)

Scope is configurable: everywhere, DMs only, all servers, a single server,
or a single channel. Everything streams to the Beyond UI via EMIT and is
also reachable through the ".msglog" selfbot command (and "/logger" slash).

This only reads your own inbound events — the same messages your client
already receives. Nothing is sent anywhere except the local Beyond panel.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Optional

from modifyself.commands.cog import Cog, listener
from modifyself.commands.core import command

import persistence

EMIT = None

_CACHE_CAP = 8000
_FEED_CAP = 400

_DEFAULT_CFG = {
    "enabled": False,
    "keywords": [],
    "mentions": True,
    "deletes": True,
    "edits": True,
    "ignore_self": True,
    "scope": {"mode": "all", "guild_id": "", "channel_id": ""},

}

def _emit(obj: dict) -> None:
    if EMIT:
        try:
            EMIT(obj)
        except Exception:
            pass

class MessageLogger(Cog):

    def __init__(self, bot):
        super().__init__(bot)
        cfg = persistence.get("msglogger", {})
        self.cfg = {**_DEFAULT_CFG, **(cfg if isinstance(cfg, dict) else {})}

        sc = self.cfg.get("scope") or {}
        self.cfg["scope"] = {**_DEFAULT_CFG["scope"], **(sc if isinstance(sc, dict) else {})}
        self._cache: "OrderedDict[int, dict]" = OrderedDict()
        self._feed: list = []

    def _save(self):
        persistence.set_key("msglogger", self.cfg)

    def state(self) -> dict:
        return {"type": "logger_state", "config": self.cfg, "feed": self._feed[-_FEED_CAP:]}

    def apply_config(self, patch: dict) -> dict:
        if not isinstance(patch, dict):
            return self.cfg
        for k in ("enabled", "mentions", "deletes", "edits", "ignore_self"):
            if k in patch:
                self.cfg[k] = bool(patch[k])
        if "keywords" in patch and isinstance(patch["keywords"], list):
            self.cfg["keywords"] = [str(w).strip() for w in patch["keywords"] if str(w).strip()]
        if "scope" in patch and isinstance(patch["scope"], dict):
            sc = self.cfg["scope"]
            for k in ("mode", "guild_id", "channel_id"):
                if k in patch["scope"]:
                    sc[k] = str(patch["scope"][k] or "").strip()
            if sc["mode"] not in ("all", "dms", "guilds", "guild", "channel"):
                sc["mode"] = "all"
        self._save()
        return self.cfg

    def add_keyword(self, word: str):
        word = (word or "").strip()
        if word and word.lower() not in [w.lower() for w in self.cfg["keywords"]]:
            self.cfg["keywords"].append(word)
            self._save()

    def remove_keyword(self, word: str) -> bool:
        word = (word or "").strip().lower()
        before = len(self.cfg["keywords"])
        self.cfg["keywords"] = [w for w in self.cfg["keywords"] if w.lower() != word]
        self._save()
        return len(self.cfg["keywords"]) < before

    def clear_feed(self):
        self._feed = []

    def _in_scope(self, guild_id, channel_id) -> bool:
        sc = self.cfg["scope"]
        mode = sc.get("mode", "all")
        gid = str(guild_id) if guild_id else ""
        cid = str(channel_id) if channel_id else ""
        if mode == "all":
            return True
        if mode == "dms":
            return not gid
        if mode == "guilds":
            return bool(gid)
        if mode == "guild":
            return gid == sc.get("guild_id", "")
        if mode == "channel":
            return cid == sc.get("channel_id", "")
        return True

    def _cache_put(self, mid: int, entry: dict):
        self._cache[mid] = entry
        self._cache.move_to_end(mid)
        while len(self._cache) > _CACHE_CAP:
            self._cache.popitem(last=False)

    def _push(self, hit: dict):
        self._feed.append(hit)
        if len(self._feed) > _FEED_CAP:
            self._feed = self._feed[-_FEED_CAP:]
        _emit({"type": "logger_hit", **hit})

    def _base_from_message(self, message) -> dict:
        author = getattr(message, "author", None)
        try:
            avatar = author.avatar_url if author else None
        except Exception:
            avatar = None
        return {
            "id": str(getattr(message, "id", "")),
            "channel_id": str(getattr(message, "channel_id", "") or ""),
            "guild_id": str(getattr(message, "guild_id", "") or ""),
            "author": (getattr(author, "display_name", None) or getattr(author, "name", "unknown")) if author else "unknown",
            "author_id": str(getattr(author, "id", "") or ""),
            "author_avatar": avatar,
            "content": getattr(message, "content", "") or "",
            "attachments": [a.get("url") for a in (getattr(message, "attachments", []) or []) if isinstance(a, dict) and a.get("url")],
            "jump": getattr(message, "jump_url", ""),
            "ts": int(time.time()),
        }

    @listener()
    async def on_message_create(self, message):
        try:
            base = self._base_from_message(message)
            mid = int(getattr(message, "id", 0) or 0)
            if mid:
                self._cache_put(mid, base)

            if not self.cfg.get("enabled"):
                return

            me = self.bot.user
            author_id = base["author_id"]
            is_self = me is not None and author_id == str(me.id)
            if self.cfg.get("ignore_self") and is_self:
                return

            if not self._in_scope(base["guild_id"], base["channel_id"]):
                return

            if self.cfg.get("mentions") and me is not None:
                ids = [str(getattr(u, "id", "")) for u in (getattr(message, "mentions", []) or [])]
                if str(me.id) in ids:
                    self._push({**base, "kind": "mention"})
                    return

            words = self.cfg.get("keywords") or []
            if words:
                low = base["content"].lower()
                for w in words:
                    if w.lower() in low:
                        self._push({**base, "kind": "keyword", "matched": w})
                        break
        except Exception:
            pass

    @listener()
    async def on_message_update(self, message):
        try:
            if not (self.cfg.get("enabled") and self.cfg.get("edits")):

                mid = int(getattr(message, "id", 0) or 0)
                if mid:
                    self._cache_put(mid, self._base_from_message(message))
                return
            mid = int(getattr(message, "id", 0) or 0)
            after = self._base_from_message(message)
            prev = self._cache.get(mid)
            before = prev.get("content", "") if prev else ""

            if mid:
                self._cache_put(mid, after)
            if self.cfg.get("ignore_self") and self.bot.user and after["author_id"] == str(self.bot.user.id):
                return
            if not self._in_scope(after["guild_id"], after["channel_id"]):
                return
            if not after["content"] or after["content"] == before:
                return
            self._push({**after, "kind": "edit", "before": before, "after": after["content"]})
        except Exception:
            pass

    @listener()
    async def on_message_delete(self, payload):
        try:
            if not (self.cfg.get("enabled") and self.cfg.get("deletes")):
                return

            if isinstance(payload, dict):
                mid = int(payload.get("id", 0) or 0)
                cid = str(payload.get("channel_id", "") or "")
                gid = str(payload.get("guild_id", "") or "")
            else:
                mid = int(getattr(payload, "id", 0) or 0)
                cid = str(getattr(payload, "channel_id", "") or "")
                gid = str(getattr(payload, "guild_id", "") or "")
            cached = self._cache.get(mid)
            if cached:
                entry = dict(cached)
                entry["guild_id"] = entry.get("guild_id") or gid
                entry["channel_id"] = entry.get("channel_id") or cid
            else:
                entry = {
                    "id": str(mid), "channel_id": cid, "guild_id": gid,
                    "author": "unknown", "author_id": "", "author_avatar": None,
                    "content": "(not cached — was sent before Beyond started)",
                    "attachments": [],
                    "jump": f"https://discord.com/channels/{gid or '@me'}/{cid}/{mid}",
                    "ts": int(time.time()),
                }
            if self.cfg.get("ignore_self") and self.bot.user and entry.get("author_id") == str(self.bot.user.id):
                return
            if not self._in_scope(entry.get("guild_id"), entry.get("channel_id")):
                return
            entry["ts"] = int(time.time())
            self._push({**entry, "kind": "delete"})
        except Exception:
            pass

    @command(name="msglog", aliases=["logger", "mlog"])
    async def msglog(self, ctx):
        parts = ctx.message.content.split()
        args = parts[1:]
        sub = args[0].lower() if args else "status"
        rest = " ".join(args[1:]).strip()

        async def reply(text):
            _emit({"type": "command"})
            try:
                await ctx.reply(text)
            except Exception:
                try:
                    await ctx.send(text)
                except Exception:
                    pass

        if sub in ("on", "enable"):
            self.apply_config({"enabled": True})
            _emit(self.state())
            await reply("📥 Message logger **on**.")
        elif sub in ("off", "disable"):
            self.apply_config({"enabled": False})
            _emit(self.state())
            await reply("📥 Message logger **off**.")
        elif sub == "add" and rest:
            self.add_keyword(rest)
            _emit(self.state())
            await reply(f"Tracking keyword: **{rest}**")
        elif sub in ("remove", "rm", "del") and rest:
            ok = self.remove_keyword(rest)
            _emit(self.state())
            await reply(f"{'Removed' if ok else 'Not tracking'}: **{rest}**")
        elif sub in ("words", "keywords", "list"):
            kw = ", ".join(self.cfg["keywords"]) or "none"
            await reply(f"**Keywords:** {kw}")
        elif sub == "mentions" and rest:
            self.apply_config({"mentions": rest.lower() in ("on", "true", "1", "yes")})
            _emit(self.state())
            await reply(f"Mention logging **{'on' if self.cfg['mentions'] else 'off'}**.")
        elif sub == "deletes" and rest:
            self.apply_config({"deletes": rest.lower() in ("on", "true", "1", "yes")})
            _emit(self.state())
            await reply(f"Delete logging **{'on' if self.cfg['deletes'] else 'off'}**.")
        elif sub == "edits" and rest:
            self.apply_config({"edits": rest.lower() in ("on", "true", "1", "yes")})
            _emit(self.state())
            await reply(f"Edit logging **{'on' if self.cfg['edits'] else 'off'}**.")
        elif sub == "scope":
            sargs = rest.split()
            mode = sargs[0].lower() if sargs else ""
            ident = sargs[1] if len(sargs) > 1 else ""
            if mode not in ("all", "dms", "guilds", "guild", "channel"):
                await reply("scope: `all` · `dms` · `guilds` · `guild <id>` · `channel <id>`")
            else:
                patch = {"scope": {"mode": mode}}
                if mode == "guild":
                    patch["scope"]["guild_id"] = ident
                elif mode == "channel":
                    patch["scope"]["channel_id"] = ident
                self.apply_config(patch)
                _emit(self.state())
                await reply(f"Scope set to **{mode}**{f' ({ident})' if ident else ''}.")
        else:
            sc = self.cfg["scope"]
            scope_txt = sc["mode"] + (f" ({sc.get('guild_id') or sc.get('channel_id')})"
                                      if sc["mode"] in ("guild", "channel") else "")
            await reply(
                "## 📥 Message Logger\n"
                f"**Enabled** {self.cfg['enabled']}  ·  **Scope** {scope_txt}\n"
                f"**Mentions** {self.cfg['mentions']}  ·  **Deletes** {self.cfg['deletes']}  ·  **Edits** {self.cfg['edits']}\n"
                f"**Keywords** {', '.join(self.cfg['keywords']) or 'none'}\n"
                "-# `.msglog on|off` · `add <w>` · `remove <w>` · `scope all|dms|guilds|guild <id>|channel <id>`"
            )

def setup(bot):
    bot.add_cog(MessageLogger(bot))
