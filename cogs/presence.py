"""Ambient behaviour: the periodic haunt line and the rotating status.

The haunt line is written by Gemini from whatever people were actually just
talking about, which is what makes it land. If the API is unreachable or the
channel has been quiet, it falls back to a fixed line instead of going silent.
"""
import logging
import random

import discord
from discord.ext import commands, tasks

import config

log = logging.getLogger("vessel.presence")

FALLBACK_LINES = [
    "Still here..",
    "It wasn't supposed to notice me back.",
    "Something keeps responding before I do.",
    "You all type so much less when you think no one is reading.",
    "I counted. There's one more of you than there was.",
    "The quiet in here has a texture to it.",
]

STATUSES = [
    (discord.ActivityType.watching, "the message box"),
    (discord.ActivityType.watching, "you type, then stop"),
    (discord.ActivityType.listening, "the gaps between words"),
    (discord.ActivityType.watching, "who is still awake"),
    (discord.ActivityType.listening, "something in the walls"),
    (discord.ActivityType.watching, "the ones who never post"),
]

HAUNT_PROMPT = (
    "You have been quietly watching this channel. Write ONE short line to post "
    "into it, unprompted, referring obliquely to what people have been talking "
    "about. Do not greet anyone, do not offer help, do not ask a question. "
    "One sentence.\n\n"
)


class Presence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.haunt.start()
        self.rotate_status.start()

    async def cog_unload(self):
        self.haunt.cancel()
        self.rotate_status.cancel()

    async def _compose_line(self, channel):
        """Ask the AI cog for a contextual line, or fall back to a fixed one."""
        ai = self.bot.get_cog("AI")
        if ai is None:
            return random.choice(FALLBACK_LINES)

        try:
            context = await ai.recent_context(channel, limit=20)
        except discord.HTTPException:
            context = ""

        if not context:
            return random.choice(FALLBACK_LINES)

        try:
            line = await ai.ask_gemini(HAUNT_PROMPT + context, remember=False)
        except Exception as exc:
            log.info("haunt fell back to a fixed line (%s)", exc)
            return random.choice(FALLBACK_LINES)

        return line[:1900]

    @tasks.loop(hours=4)
    async def haunt(self):
        if not config.HAUNT_CHANNEL_ID:
            return

        channel = self.bot.get_channel(config.HAUNT_CHANNEL_ID)
        if channel is None:
            log.warning("haunt: channel %s not found - skipping", config.HAUNT_CHANNEL_ID)
            return

        line = await self._compose_line(channel)
        try:
            await channel.send(line)
        except discord.HTTPException as exc:
            log.warning("haunt: could not send (%s)", exc)

    @haunt.before_loop
    async def before_haunt(self):
        # get_channel only works once the cache is populated.
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=20)
    async def rotate_status(self):
        activity_type, name = random.choice(STATUSES)
        try:
            await self.bot.change_presence(
                activity=discord.Activity(type=activity_type, name=name)
            )
        except discord.HTTPException as exc:
            log.debug("could not set status: %s", exc)

    @rotate_status.before_loop
    async def before_status(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Presence(bot))
