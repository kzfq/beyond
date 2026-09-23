"""Reply helpers for Beyond selfbot cogs.

The RPC cog replies through ASCIIMixin (aprint / asuccess / aerror / awarn) and
asend. Every reply is rendered with the shared ANSI style (ansi.py), deletes the
invoking command immediately, and self-deletes after `delay` seconds.
"""
import asyncio

import ansi


async def _send_and_expire(ctx, text, delay):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    m = None
    try:
        m = await ctx.send(text)
    except Exception:
        return
    if m is None:
        return

    async def _rm():
        await asyncio.sleep(max(1, int(delay or 15)))
        try:
            await m.delete()
        except Exception:
            pass
    asyncio.create_task(_rm())


class ASCIIMixin:
    async def aprint(self, ctx, title, lines, delay=15):
        body = "\n".join(f"{ansi.WHITE}{str(x)}{ansi.RESET}" for x in (lines or []))
        await _send_and_expire(ctx, ansi.header(str(title)) + "\n" + ansi._block(body), delay)

    async def asuccess(self, ctx, msg, delay=15):
        await _send_and_expire(ctx, ansi.success(str(msg)), delay)

    async def aerror(self, ctx, msg, delay=15):
        await _send_and_expire(ctx, ansi.error(str(msg)), delay)

    async def awarn(self, ctx, msg, delay=15):
        await _send_and_expire(ctx, ansi.warning(str(msg)), delay)


async def asend(ctx, text, delay=15):
    await _send_and_expire(ctx, ansi._block(f"{ansi.WHITE}{text}{ansi.RESET}"), delay)
