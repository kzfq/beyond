#!/usr/bin/env python3
"""Run the RPC image-upload path with NO error swallowing, so the real failure
is printed. Run:  python backend\\rpc_imgtest.py"""
import asyncio
import json
import re
import urllib.request as _ur
import uuid

_CDN_PAT = r"https?://(?:cdn\.discordapp\.com|media\.discordapp\.net)/attachments/(\d+)/(\d+)/(.+)"
_ASSET_CHANNEL_ID = "1477758738772525239"


def prompt(label, secret=False):
    if secret:
        try:
            import getpass
            return getpass.getpass(label).strip()
        except Exception:
            pass
    return input(label).strip()


async def fallback_channel(http):
    from modifyself.http.route import Route
    guilds = await http.request(Route("GET", "/users/@me/guilds"))
    print(f"   guilds found: {len(guilds or [])}")
    for g in (guilds or []):
        chans = await http.request(Route("GET", f"/guilds/{g.get('id')}/channels"))
        for c in (chans or []):
            if c.get("type") == 0:
                print(f"   fallback channel: #{c.get('name')} ({c['id']}) in guild {g.get('id')}")
                return str(c["id"])
    return None


async def main():
    token = prompt("Account token (hidden): ", secret=True)
    url = prompt("Image URL to test: ")
    if not token or not url:
        print("need both"); return

    from modifyself import Client
    from wreq import Method
    bot = Client(token=token, command_prefix=".", notifications=False)
    http = bot._http
    spoofer = http._spoofer

    print("\n1) CDN pattern check…")
    if re.search(r'https?://(?:cdn\.discordapp\.com|media\.discordapp\.net)', url) and "?" in url:
        print("   discord CDN link with query -> would refresh-urls")
    m = re.search(_CDN_PAT, url)
    if m:
        ch, att, fn = m.groups()
        print(f"   MATCH -> mp:attachments/{ch}/{att}/{fn}  (no upload needed)")
        print("\nRESULT: this URL becomes an asset key directly. If it still")
        print("doesn't show, the issue is the send, not the upload.")
        return
    print("   not a CDN link -> must download + upload")

    print("\n2) downloading image…")
    def _dl():
        req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _ur.urlopen(req, timeout=15) as r:
            return r.read(), r.headers.get("Content-Type", "image/png")
    data, ct = await asyncio.get_event_loop().run_in_executor(None, _dl)
    print(f"   downloaded {len(data)} bytes, content-type {ct}")

    filename = url.split("/")[-1].split("?")[0]
    if "." not in filename or len(filename) > 50:
        filename = "asset.gif" if "gif" in ct else "asset.png"
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="payload_json"\r\n'
        f"Content-Type: application/json\r\n\r\n"
        f'{{"content":""}}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"\r\n'
        f"Content-Type: {ct}\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()

    client = http._get_client()

    async def try_upload(ch_id, tag):
        headers = spoofer.get_headers(
            referer=f"https://discord.com/channels/@me/{ch_id}",
            context_location="chat_input",
        )
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        print(f"\n   POST to channel {ch_id} ({tag})…")
        resp = await client.request(
            Method.POST,
            f"https://discord.com/api/v9/channels/{ch_id}/messages",
            headers=headers, body=body,
        )
        code = int(resp.status.as_int())
        text = await resp.text()
        print(f"   status {code}")
        if code not in (200, 201):
            print(f"   response: {text[:400]}")
        return code, text

    print("\n3) uploading to configured asset channel…")
    code, text = await try_upload(_ASSET_CHANNEL_ID, "configured/default")
    if code not in (200, 201):
        print("\n4) default channel rejected -> finding a fallback channel you can post in…")
        fb = await fallback_channel(http)
        if not fb:
            print("   NO fallback channel found (not in any guild with a text channel).")
            print("\nRESULT: upload can't post anywhere. Set your own asset channel:")
            print("   put a channel ID you can post in into beyond_state.json as rpc_asset_channel")
            return
        code, text = await try_upload(fb, "fallback")

    if code in (200, 201):
        d = json.loads(text)
        atts = d.get("attachments", [])
        if atts:
            m2 = re.search(_CDN_PAT, atts[0]["url"])
            if m2:
                c2, a2, f2 = m2.groups()
                print(f"\nRESULT: upload OK -> mp:attachments/{c2}/{a2}/{f2}")
                print("Images WILL work. If the UI still shows none, it's the send/mapping.")
                return
        print("\nRESULT: uploaded but no attachment in response:", text[:300])
    else:
        print("\nRESULT: upload failed even on fallback. See status/response above.")


if __name__ == "__main__":
    asyncio.run(main())
