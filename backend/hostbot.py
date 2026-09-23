
"""
Beyond — standalone slash-bot host.

Runs your real Discord bot (discord.py) so its "/" slash commands work while
this window is open. Prints live status so you can see exactly what's happening.

Run:
    python backend\\hostbot.py

It will ask for:
  - Application (client) ID   [Developer Portal -> General Information]
  - Bot token                 [Developer Portal -> Bot -> Reset Token]
  - (optional) a Server ID    -> if given, commands sync to THAT server
                                 INSTANTLY (great for testing). Leave blank to
                                 sync globally (can take up to ~1 hour to show).

The commands are marked USER-INSTALLABLE, so once your app is added to your
account (the "Add to my apps" authorize page), /help /ping /stats work in DMs
and any server for you.
"""

import asyncio
import sys

try:
    import discord
    from discord import app_commands
except Exception as e:
    import traceback
    print("=" * 60)
    print("Could not import discord.py. The REAL error is:")
    print("  ", repr(e))
    print("-" * 60)
    traceback.print_exc()
    print("-" * 60)
    print("Python running this script:")
    print("  ", sys.executable)
    print("  version:", sys.version.split()[0])
    print("If discord.py is installed in a DIFFERENT python than the one above,")
    print("run the script with that python explicitly, e.g.:")
    print('   & "C:\\Users\\nox\\AppData\\Local\\Programs\\Python\\Python312\\python.exe" backend\\hostbot.py')
    sys.exit(1)

BANNER = [
    "██████  ███████ ██    ██  ██████  ███    ██ ██████",
    "██   ██ ██       ██  ██  ██    ██ ████   ██ ██   ██",
    "██████  █████     ████   ██    ██ ██ ██  ██ ██   ██",
    "██   ██ ██         ██    ██    ██ ██  ██ ██ ██   ██",
    "██████  ███████    ██     ██████  ██   ████ ██████",
]

def help_text() -> str:
    return "```\n" + "\n".join(BANNER) + "\n\n  commands:  help   ping   stats\n```"

def prompt(label: str, secret: bool = False) -> str:
    if secret:
        try:
            import getpass
            return getpass.getpass(label).strip()
        except Exception:
            pass
    return input(label).strip()

def main():
    print("=" * 52)
    print(" Beyond — slash-bot host")
    print("=" * 52)
    app_id = prompt("Application (client) ID: ")
    token = prompt("Bot token (input hidden): ", secret=True)
    guild_id = prompt("Server ID for INSTANT sync (blank = global): ")

    if not app_id or not token:
        print("Need both an App ID and a Bot token. Exiting.")
        return

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    def user_installable(func):
        try:
            func = app_commands.allowed_installs(guilds=True, users=True)(func)
            func = app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)(func)
        except Exception as e:
            print(f"  (note: could not set user-install context: {e})")
        return func

    @tree.command(name="ping", description="Show gateway latency")
    @user_installable
    async def _ping(interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Pong — {round(client.latency * 1000)}ms", ephemeral=False)

    @tree.command(name="help", description="Show Beyond commands")
    @user_installable
    async def _help(interaction: discord.Interaction):
        await interaction.response.send_message(help_text(), ephemeral=False)

    @tree.command(name="stats", description="Show bot stats")
    @user_installable
    async def _stats(interaction: discord.Interaction):
        g = len(client.guilds)
        await interaction.response.send_message(
            f"**{client.user}** — latency: {round(client.latency*1000)}ms · servers: {g}",
            ephemeral=False)

    @client.event
    async def on_ready():
        print("\n" + "-" * 52)
        print(f"  ONLINE as {client.user}  (id {client.user.id})")
        print("-" * 52)
        try:
            if guild_id:
                guild = discord.Object(id=int(guild_id))
                tree.copy_global_to(guild=guild)
                synced = await tree.sync(guild=guild)
                print(f"  Synced {len(synced)} commands to server {guild_id} "
                      f"(should appear INSTANTLY).")
            else:
                synced = await tree.sync()
                print(f"  Synced {len(synced)} GLOBAL commands "
                      f"(can take up to ~1 hour to appear).")
            for c in synced:
                print(f"     /{c.name}")
        except Exception as e:
            print(f"  Slash sync FAILED: {e}")
        print("\n  Bot is hosted. Keep this window OPEN to keep it online.")
        print("  Press Ctrl+C to stop.\n")

    try:
        client.run(token)
    except discord.LoginFailure:
        print("\nLogin failed: that Bot token is wrong.")
        print("Get it from Developer Portal -> Bot -> Reset Token (NOT the App ID).")
    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    main()
