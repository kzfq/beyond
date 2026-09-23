from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request as _ur
from typing import Optional

from modifyself.commands.cog import Cog, listener
from modifyself.commands.core import command
from modifyself.http.route import Route

from ascii_helper import ASCIIMixin

_SPOTIFY_API  = "https://api.spotify.com/v1"
_LRCLIB       = "https://lrclib.net/api/get"
_TOKEN_TTL    = 50 * 60   # refresh every 50 min
_SYNC_EVERY   = 30.0      # re-poll Spotify every 30s to correct drift

# Beyond hook: beyond_backend sets EMIT = its emit() so this cog can stream
# now-playing + lyric state to the UI. No-op when running as a plain selfbot.
EMIT = None


def _emit(obj: dict) -> None:
    if EMIT is not None:
        try:
            EMIT(obj)
        except Exception:
            pass


# ── blocking helpers ──────────────────────────────────────────────────────────

def _fetch_synced(title: str, artist: str, album: str, duration_s: int) -> list[tuple[int, str]]:
    params = urllib.parse.urlencode({
        "track_name": title, "artist_name": artist,
        "album_name": album, "duration": duration_s,
    })
    try:
        req = _ur.Request(f"{_LRCLIB}?{params}", headers={"User-Agent": "selfbot.fyi/1.0"})
        with _ur.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        raw = data.get("syncedLyrics") or ""
        lines = []
        for line in raw.split("\n"):
            m = re.match(r"\[(\d+):(\d+\.\d+)\]\s*(.*)", line)
            if m:
                mn, sc, text = m.groups()
                ms = int(float(mn) * 60000 + float(sc) * 1000)
                lines.append((ms, text.strip()))
        return sorted(lines, key=lambda x: x[0]) if lines else []
    except Exception as e:
        print(f"[sl] lrclib error: {e}")
        return []


def _spotify_get(token: str, path: str) -> Optional[dict]:
    try:
        req = _ur.Request(f"{_SPOTIFY_API}{path}", headers={"Authorization": f"Bearer {token}"})
        with _ur.urlopen(req, timeout=6) as r:
            return None if r.status == 204 else json.loads(r.read())
    except urllib.error.HTTPError:
        raise
    except Exception as e:
        print(f"[sl] spotify_get error: {e}")
        return None


# ── cog ───────────────────────────────────────────────────────────────────────

class SpotifyLyrics(Cog, ASCIIMixin):

    def __init__(self, bot):
        super().__init__(bot)
        self._task: Optional[asyncio.Task] = None
        self._discord_activity: Optional[dict] = None
        self._lyrics: list[tuple[int, str]] = []
        self._last_line = ""
        self._enabled = False

    # ── listeners ─────────────────────────────────────────────────────────

    @listener()
    async def on_sessions_replace(self, data):
        for session in data or []:
            for act in session.get("activities", []):
                if act.get("type") == 2 and act.get("name") == "Spotify":
                    self._discord_activity = act
                    return
        self._discord_activity = None

    @listener()
    async def on_presence_update(self, data):
        if not data:
            return
        try:
            if str((data.get("user") or {}).get("id")) != str(self.bot.user.id):
                return
        except Exception:
            return
        act = next(
            (a for a in (data.get("activities") or [])
             if a.get("type") == 2 and a.get("name") == "Spotify"),
            None,
        )
        self._discord_activity = act

    # ── Discord → Spotify token ───────────────────────────────────────────

    async def _get_token(self) -> Optional[str]:
        import traceback
        try:
            conns = await self.bot._http.request(Route("GET", "/users/@me/connections"))
            sp = next((c for c in (conns or []) if c.get("type") == "spotify"), None)
            if not sp:
                print("[sl] no spotify connection found")
                return None
            print(f"[sl] spotify connection keys: {list(sp.keys())}")

            if sp.get("access_token"):
                print("[sl] token from connection object")
                return sp["access_token"]

            for path in (
                f"/connections/spotify/{sp['id']}/access-token",
                f"/users/@me/connections/spotify/{sp['id']}/access-token",
                f"/users/@me/connections/spotify/access-token",
            ):
                try:
                    data = await self.bot._http.request(Route("GET", path))
                    tok = (data or {}).get("access_token")
                    if tok:
                        print(f"[sl] token obtained via {path}")
                        return tok
                    print(f"[sl] {path} → no access_token: {data}")
                except Exception as e:
                    print(f"[sl] {path} → {e}")
            return None
        except Exception as e:
            print(f"[sl] _get_token error: {e}")
            traceback.print_exc()
            return None

    # ── status ────────────────────────────────────────────────────────────
    # 1:1 with the reference cog — PATCH /users/@me/settings custom_status.
    # (Adds a visible notif on failure so silent HTTP errors surface in the UI.)

    async def _set_status(self, text: str):
        import json as _json, traceback
        try:
            from wreq import Method
            client  = self.bot._http._get_client()
            spoofer = self.bot._http._spoofer
            headers = spoofer.get_headers(context_location="user_settings")
            headers["Content-Type"] = "application/json"
            body = _json.dumps({
                "custom_status": {
                    "text": text[:128] if text else "",
                    "emoji_name": None,
                    "expires_at": None,
                }
            }).encode("utf-8")
            resp = await client.request(
                Method.PATCH,
                "https://discord.com/api/v9/users/@me/settings",
                headers=headers,
                body=body,
            )
            status = int(resp.status.as_int())
            if status == 200:
                print(f"[sl] custom status set → {text!r}")
            else:
                detail = ""
                try:
                    detail = (await resp.text())[:200]
                except Exception:
                    pass
                print(f"[sl] set_status HTTP {status} {detail}")
                _emit({"type": "notif", "kind": "warn",
                       "msg": f"Status update failed (HTTP {status}) {detail}"})
        except Exception as e:
            print(f"[sl] set_status error: {e}")
            traceback.print_exc()
            _emit({"type": "notif", "kind": "err", "msg": f"Status update error: {e}"})

    # ── UI helpers ────────────────────────────────────────────────────────

    def _emit_np(self, *, source, title, artist, album, cover, duration_ms,
                 anchor_pos_ms, anchor_wall):
        _emit({
            "type": "spotify_np", "playing": True, "source": source,
            "title": title, "artist": artist, "album": album, "cover": cover,
            "duration_ms": int(duration_ms or 0),
            "anchorPosMs": int(anchor_pos_ms or 0),
            "anchorWallMs": int(anchor_wall * 1000),
            "hasLyrics": bool(self._lyrics),
            "lyrics": [[ms, txt] for ms, txt in self._lyrics],
        })

    # ── sync loop ─────────────────────────────────────────────────────────

    async def _sync_loop(self):
        loop = asyncio.get_event_loop()

        token     = await self._get_token()
        use_api   = bool(token)
        token_ts  = time.time()
        fetched_id: Optional[str] = None

        anchor_pos_ms  = 0
        anchor_wall    = 0.0
        next_sync_wall = 0.0

        print(f"[sl] loop started — use_api={use_api}")

        while self._enabled:
            now = time.time()

            if use_api and now - token_ts > _TOKEN_TTL:
                new_tok = await self._get_token()
                if new_tok:
                    token, token_ts = new_tok, now

            if use_api and token and now >= next_sync_wall:
                try:
                    t0 = time.time()
                    pb = await loop.run_in_executor(None, _spotify_get, token, "/me/player")
                    t1 = time.time()

                    if not (pb and pb.get("is_playing")):
                        print(f"[sl] not playing")
                        _emit({"type": "spotify_np", "playing": False})
                        await asyncio.sleep(5)
                        continue

                    item        = pb.get("item") or {}
                    track_id    = item.get("id") or ""
                    title       = item.get("name") or ""
                    artist      = ", ".join(a["name"] for a in item.get("artists", []))
                    album       = (item.get("album") or {}).get("name") or ""
                    duration_ms = item.get("duration_ms") or 0
                    imgs        = (item.get("album") or {}).get("images") or []
                    cover       = imgs[0]["url"] if imgs else ""

                    latency_ms     = int((t1 - t0) * 500)
                    anchor_pos_ms  = (pb.get("progress_ms") or 0) + latency_ms
                    anchor_wall    = t1
                    next_sync_wall = t1 + _SYNC_EVERY
                    print(f"[sl] synced @ {anchor_pos_ms}ms (latency ~{latency_ms}ms)")

                    if track_id != fetched_id:
                        fetched_id = track_id
                        self._last_line = ""
                        dur_s = max(0, duration_ms // 1000)
                        print(f"[sl] fetching lyrics: '{title}' by {artist}")
                        self._lyrics = await loop.run_in_executor(
                            None, _fetch_synced, title, artist, album, dur_s
                        )
                        print(f"[sl] {len(self._lyrics)} lines found")
                        self._emit_np(source="api", title=title, artist=artist, album=album,
                                      cover=cover, duration_ms=duration_ms,
                                      anchor_pos_ms=anchor_pos_ms, anchor_wall=anchor_wall)
                        if not self._lyrics:
                            await self._set_status(f"♪ {title}" if title else "♪")
                    else:
                        _emit({"type": "spotify_sync", "anchorPosMs": int(anchor_pos_ms),
                               "anchorWallMs": int(anchor_wall * 1000)})

                except urllib.error.HTTPError as e:
                    print(f"[sl] api HTTP {e.code}")
                    if e.code == 401:
                        token = await self._get_token()
                        token_ts = time.time()
                    elif e.code == 403:
                        print("[sl] 403 — no premium, falling back to discord activity")
                        use_api = False
                    await asyncio.sleep(3)
                    continue
                except Exception as e:
                    import traceback
                    print(f"[sl] api error: {e}")
                    traceback.print_exc()
                    await asyncio.sleep(5)
                    continue

            elif not use_api:
                act = self._discord_activity
                if not act:
                    print("[sl] waiting for discord spotify activity...")
                    _emit({"type": "spotify_np", "playing": False})
                    await asyncio.sleep(2)
                    continue

                ts    = act.get("timestamps") or {}
                start = ts.get("start") or 0
                end   = ts.get("end")   or 0
                track_id = act.get("sync_id") or ""

                anchor_pos_ms = int(time.time() * 1000) - start
                anchor_wall   = time.time()

                if track_id != fetched_id:
                    fetched_id = track_id
                    self._last_line = ""
                    title  = act.get("details") or ""
                    artist = (act.get("state") or "").split(";")[0].strip()
                    album  = (act.get("assets") or {}).get("large_text") or ""
                    dur_s  = max(0, (end - start) // 1000)
                    li     = (act.get("assets") or {}).get("large_image") or ""
                    cover  = ("https://i.scdn.co/image/" + li.split(":", 1)[1]) if li.startswith("spotify:") else ""
                    print(f"[sl] fallback fetching lyrics: '{title}'")
                    self._lyrics = await loop.run_in_executor(
                        None, _fetch_synced, title, artist, album, dur_s
                    )
                    print(f"[sl] {len(self._lyrics)} lines found")
                    self._emit_np(source="discord", title=title, artist=artist, album=album,
                                  cover=cover, duration_ms=(end - start),
                                  anchor_pos_ms=anchor_pos_ms, anchor_wall=anchor_wall)
                    if not self._lyrics:
                        await self._set_status(f"♪ {title}" if title else "♪")

            if not self._lyrics:
                await asyncio.sleep(5)
                continue

            pos_ms  = anchor_pos_ms + int((time.time() - anchor_wall) * 1000)
            current = ""
            next_ms: Optional[int] = None

            for i, (ms, text) in enumerate(self._lyrics):
                if ms <= pos_ms:
                    current = text
                    next_ms = self._lyrics[i + 1][0] if i + 1 < len(self._lyrics) else None
                else:
                    if next_ms is None:
                        next_ms = ms
                    break

            if current and current != self._last_line:
                self._last_line = current
                print(f"[sl] → {current!r}")
                _emit({"type": "spotify_lyric", "line": current, "pos": pos_ms})
                try:
                    await self._set_status(current)
                except Exception as e:
                    print(f"[sl] set_status error: {e}")

            if next_ms is not None:
                pos_now  = anchor_pos_ms + int((time.time() - anchor_wall) * 1000)
                sleep_s  = (next_ms - pos_now) / 1000
                if use_api:
                    sleep_s = min(sleep_s, next_sync_wall - time.time())
                sleep_s = max(0.02, sleep_s)
            elif use_api:
                sleep_s = max(0.5, next_sync_wall - time.time())
            else:
                sleep_s = 2.0

            await asyncio.sleep(sleep_s)

    # ── control (called by beyond_backend + the .spotifylyrics command) ───

    def start(self):
        if self._enabled and self._task and not self._task.done():
            return False
        self._enabled = True
        self._task = asyncio.ensure_future(self._sync_loop())
        return True

    def stop(self):
        self._enabled = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self._lyrics = []
        self._last_line = ""
        _emit({"type": "spotify_np", "playing": False})
        asyncio.ensure_future(self._set_status(""))

    # ── command ───────────────────────────────────────────────────────────

    @command()
    async def spotifylyrics(self, ctx):
        rest = " ".join(ctx.message.content.split()[1:]).strip().lower()

        if rest == "off":
            self.stop()
            await self.asuccess(ctx, "spotify lyrics stopped", delay=6)
            return

        if self._enabled and self._task and not self._task.done():
            await self.aerror(ctx, "already running — .spotifylyrics off to stop", delay=6)
            return

        self.start()
        await self.aprint(ctx, "Spotify Lyrics", ["syncing to custom status"], delay=8)


def setup(bot):
    bot.add_cog(SpotifyLyrics(bot))
