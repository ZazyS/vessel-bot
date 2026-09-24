import logging

import discord
from discord.ext import commands

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("vessel")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents)

EXTENSIONS = ("cogs.fun", "cogs.ai", "cogs.music", "cogs.presence")


@bot.event
async def setup_hook():
    for ext in EXTENSIONS:
        try:
            await bot.load_extension(ext)
            log.info("loaded %s", ext)
        except Exception:
            # One broken cog shouldn't stop the whole bot from starting.
            log.exception("failed to load %s", ext)


@bot.event
async def on_ready():
    log.info("%s is awake.", bot.user)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("You left something out. Try again, properly.")
        return
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Not yet. {error.retry_after:.0f}s.")
        return
    if isinstance(error, commands.NoPrivateMessage):
        await ctx.send("Not here. Somewhere with other people in it.")
        return
    log.exception("command %s failed", ctx.command, exc_info=error)
    await ctx.send("That went wrong somewhere. It usually does.")


if __name__ == "__main__":
    bot.run(config.DISCORD_TOKEN, log_handler=None)
