"""
Discord Music Bot
A feature-rich music bot for Discord with YouTube support.
"""

import traceback
from keep_alive import keep_alive
import discord
from discord.ext import commands

from config import DISCORD_TOKEN, BOT_COLOR


# ──────────────────────────────────────────────
#  Bot Setup
# ──────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(
    intents=intents,
    activity=discord.Activity(
        type=discord.ActivityType.listening,
        name="/play"
    ),
)


# ──────────────────────────────────────────────
#  Events
# ──────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"{'='*50}")
    print(f"  Discord Music Bot is online!")
    print(f"  Logged in as: {bot.user} (ID: {bot.user.id})")
    print(f"  Servers: {len(bot.guilds)}")
    print(f"  Python discord library: {discord.__version__}")
    print(f"{'='*50}")


@bot.event
async def on_application_command_error(ctx, error):
    """Global error handler for slash commands."""
    # Print the REAL error to console for debugging
    print(f"[ERROR] Command '{ctx.command}' failed:")
    traceback.print_exception(type(error), error, error.__traceback__)

    try:
        if isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title="⏳ Cooldown",
                description=f"Please wait {error.retry_after:.1f}s before using this command again.",
                color=0xF39C12
            )
            await ctx.respond(embed=embed, ephemeral=True)
        elif isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="🔒 Missing Permissions",
                description="You don't have permission to use this command.",
                color=0xE74C3C
            )
            await ctx.respond(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred:\n```{str(error)[:500]}```",
                color=0xE74C3C
            )
            try:
                await ctx.respond(embed=embed, ephemeral=True)
            except discord.errors.NotFound:
                # Interaction expired, try followup
                try:
                    await ctx.followup.send(embed=embed, ephemeral=True)
                except Exception:
                    pass
    except discord.errors.NotFound:
        pass  # Interaction expired
    except Exception as e:
        print(f"[ERROR] Error handler itself failed: {e}")


# ──────────────────────────────────────────────
#  Slash Commands (Info)
# ──────────────────────────────────────────────

@bot.slash_command(name="help", description="Show all available commands")
async def help_command(ctx: discord.ApplicationContext):
    embed = discord.Embed(
        title="🎵 Music Bot - Commands",
        description="Here are all available commands:",
        color=BOT_COLOR
    )

    commands_list = {
        "🎶 Playback": {
            "/play <query>": "Play a song (URL, search, or playlist)",
            "/search <query>": "Search and choose from results",
            "/pause": "Pause the current song",
            "/resume": "Resume playback",
            "/skip": "Skip to next song",
            "/stop": "Stop and disconnect",
        },
        "📋 Queue": {
            "/queue": "View the queue",
            "/nowplaying": "Current song info",
            "/remove <pos>": "Remove from queue",
            "/move <from> <to>": "Reorder queue",
            "/clear": "Clear the queue",
            "/shuffle": "Shuffle the queue",
        },
        "⚙️ Settings": {
            "/volume <0-100>": "Set volume",
            "/loop": "Toggle loop (Off/Single/Queue)",
            "/lyrics [query]": "Get song lyrics",
        },
    }

    for category, cmds in commands_list.items():
        value = "\n".join(f"`{cmd}` - {desc}" for cmd, desc in cmds.items())
        embed.add_field(name=category, value=value, inline=False)

    embed.set_footer(text="Discord Music Bot | Made with Pycord")
    await ctx.respond(embed=embed)


@bot.slash_command(name="ping", description="Check bot latency")
async def ping(ctx: discord.ApplicationContext):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latency: **{latency}ms**",
        color=BOT_COLOR
    )
    await ctx.respond(embed=embed)


# ──────────────────────────────────────────────
#  Load Cogs & Run
# ──────────────────────────────────────────────

bot.load_extension("cogs.music")


if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "your_bot_token_here":
        print("=" * 50)
        print("  ERROR: Discord token not set!")
        print("  1. Copy .env.example to .env")
        print("  2. Add your bot token to .env")
        print("  3. Get a token from:")
        print("     https://discord.com/developers/applications")
        print("=" * 50)
        exit(1)

        keep_alive()
bot.run(DISCORD_TOKEN)
