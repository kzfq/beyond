"""ascii_helper shim for Beyond.

The RPC cog replies through ASCIIMixin (aprint / asuccess / aerror) and asend,
each of which posts a message that auto-deletes after `delay` seconds. This shim
reproduces that behavior using modifyself's Context (ctx.reply / ctx.send).
"""
import asyncio

async def _reply_and_expire(ctx, text, delay):
    m = None
    try:
        m = await ctx.reply(text)
    except Exception:
        try:
            m = await ctx.send(text)
        except Exception:
            return
    if m is None:
        return

    async def _rm():
        await asyncio.sleep(max(1, int(delay or 8)))
        try:
            await m.delete()
        except Exception:
            pass
    asyncio.create_task(_rm())

class ASCIIMixin:
    async def aprint(self, ctx, title, lines, delay=10):
        body = "\n".join(str(x) for x in (lines or []))
        await _reply_and_expire(ctx, f"## {title}\n{body}", delay)

    async def asuccess(self, ctx, msg, delay=8):
        await _reply_and_expire(ctx, f"**{msg}**", delay)

    async def aerror(self, ctx, msg, delay=8):
        await _reply_and_expire(ctx, f"`error` {msg}", delay)

async def asend(ctx, text, delay=8):
    await _reply_and_expire(ctx, str(text), delay)
