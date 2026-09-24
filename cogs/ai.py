import asyncio
import base64
import json
import logging
import random
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands

import config

log = logging.getLogger("vessel.ai")

API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{config.GEMINI_MODEL}:generateContent"
)

PERSONA = """You are Vessel. a presence living in a discord server.
You are dry, unsettling, and slightly amused by the poeple here.
You answer questions sarcastically and never warmly.
The person who created you is Zazy.
Keep every reply under 3 sentences. Never use bullet points or headers."""

MEMORY_PATH = Path(__file__).resolve().parent.parent / "vessel_memory.json"

MAX_TURNS = 10              # user+model messages kept per channel
REQUEST_TIMEOUT = 60        # seconds
MAX_IMAGE_BYTES = 4_000_000
INTERJECT_CHANCE = 1 / 300  # per eligible message
INTERJECT_COOLDOWN = 1800   # seconds between uninvited remarks in a channel


class GeminiError(RuntimeError):
    """Raised with a human-readable reason when the API doesn't give us text."""


class AI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.history = {}
        self.session = None
        self._lock = asyncio.Lock()
        self._last_interjection = {}

    async def cog_load(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        )
        self.history = await asyncio.to_thread(self._load_memory)
        if self.history:
            log.info("recalled %d channel(s) from memory", len(self.history))

    async def cog_unload(self):
        await asyncio.to_thread(self._save_memory)
        if self.session is not None:
            await self.session.close()

    # ----------------------------------------------------------- persistence

    @staticmethod
    def _load_memory():
        if not MEMORY_PATH.exists():
            return {}
        try:
            raw = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            return {int(k): v for k, v in raw.items()}
        except (OSError, ValueError):
            log.warning("memory file unreadable - starting fresh")
            return {}

    def _save_memory(self):
        try:
            MEMORY_PATH.write_text(
                json.dumps({str(k): v for k, v in self.history.items()}),
                encoding="utf-8",
            )
        except OSError as exc:
            log.warning("could not save memory: %s", exc)

    # ------------------------------------------------------------------- api

    async def ask_gemini(self, prompt, channel_id=None, remember=True, images=()):
        """Ask Gemini. With remember=False nothing is kept in history."""
        parts = [{"text": prompt}]
        for mime, data in images:
            parts.append({
                "inline_data": {
                    "mime_type": mime,
                    "data": base64.b64encode(data).decode(),
                }
            })
        turn = {"role": "user", "parts": parts}

        # One-off prompts (summaries, ambient lines) see no history and leave
        # none behind - otherwise a 50-message transcript would ride along on
        # every later reply in the channel.
        if remember:
            history = self.history.setdefault(channel_id, [])
            contents = history + [turn]
        else:
            history = None
            contents = [turn]

        payload = {
            "system_instruction": {"parts": [{"text": PERSONA}]},
            "contents": contents,
        }
        headers = {
            "x-goog-api-key": config.GEMINI_API_KEY,
            "Content-Type": "application/json",
        }

        # Serialise calls so two of them can't interleave into one history.
        async with self._lock:
            try:
                async with self.session.post(
                    API_URL, headers=headers, json=payload
                ) as response:
                    result = await response.json(content_type=None)
                    if response.status != 200:
                        message = (
                            result.get("error", {}).get("message")
                            if isinstance(result, dict)
                            else None
                        )
                        raise GeminiError(message or f"HTTP {response.status}")
            except asyncio.TimeoutError:
                raise GeminiError("the API took too long to answer")
            except aiohttp.ClientError as exc:
                raise GeminiError(f"could not reach the API ({exc})")

            answer = self._extract_text(result)

            if remember:
                # Store only text - image bytes would bloat the memory file.
                stored = dict(turn)
                if images:
                    stored = {
                        "role": "user",
                        "parts": [{"text": f"{prompt} [attached an image]"}],
                    }
                history.append(stored)
                history.append({"role": "model", "parts": [{"text": answer}]})
                self.history[channel_id] = history[-MAX_TURNS:]
                await asyncio.to_thread(self._save_memory)

        return answer

    @staticmethod
    def _extract_text(result):
        candidates = result.get("candidates") or []
        if not candidates:
            reason = (result.get("promptFeedback") or {}).get("blockReason")
            raise GeminiError(f"the prompt was blocked ({reason})" if reason
                              else "the API returned no answer")

        candidate = candidates[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts).strip()

        if not text:
            finish = candidate.get("finishReason")
            raise GeminiError(f"the answer was cut off ({finish})" if finish
                              else "the API returned an empty answer")
        return text

    # -------------------------------------------------------------- helpers

    async def _reply(self, ctx, prompt, remember=True, images=()):
        async with ctx.typing():
            try:
                answer = await self.ask_gemini(
                    prompt, ctx.channel.id, remember, images
                )
            except GeminiError as exc:
                log.warning("gemini failed: %s", exc)
                await ctx.send(f"Nothing came back - {exc}.")
                return
        await ctx.send(answer[:1900])

    @staticmethod
    async def _collect_images(message):
        """Download image attachments so Gemini can look at them."""
        images = []
        for attachment in message.attachments:
            content_type = (attachment.content_type or "").split(";")[0]
            if not content_type.startswith("image/"):
                continue
            if attachment.size > MAX_IMAGE_BYTES:
                continue
            try:
                images.append((content_type, await attachment.read()))
            except discord.HTTPException:
                log.warning("could not download %s", attachment.filename)
            if len(images) >= 3:
                break
        return images

    def _strip_mention(self, message):
        text = message.content
        for mention in (f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>"):
            text = text.replace(mention, "")
        return text.strip()

    async def _is_reply_to_me(self, message):
        ref = message.reference
        if ref is None:
            return False
        resolved = ref.resolved
        if isinstance(resolved, discord.Message):
            return resolved.author.id == self.bot.user.id
        if ref.message_id is None:
            return False
        try:
            original = await message.channel.fetch_message(ref.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return False
        return original.author.id == self.bot.user.id

    async def recent_context(self, channel, limit=15):
        """Plain-text transcript of the last few human messages."""
        messages = []
        async for message in channel.history(limit=limit):
            if message.author.bot or not message.content:
                continue
            messages.append(f"{message.author.display_name}: {message.content}")
        messages.reverse()
        return "\n".join(messages)

    # ------------------------------------------------------------ listeners

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or self.bot.user is None:
            return
        # Commands are handled by the command system, not here.
        if message.content.startswith(config.COMMAND_PREFIX):
            return

        mentioned = self.bot.user in message.mentions
        replied = await self._is_reply_to_me(message)

        if mentioned or replied:
            await self._respond_to(message)
            return

        await self._maybe_interject(message)

    async def _respond_to(self, message):
        prompt = self._strip_mention(message)
        images = await self._collect_images(message)

        if not prompt and images:
            prompt = "Say something about this image."
        elif not prompt:
            prompt = "Someone is trying to get your attention but said nothing."

        prompt = f"{message.author.display_name} says: {prompt}"

        async with message.channel.typing():
            try:
                answer = await self.ask_gemini(
                    prompt, message.channel.id, remember=True, images=images
                )
            except GeminiError as exc:
                log.warning("gemini failed: %s", exc)
                return
        await message.reply(answer[:1900], mention_author=False)

    async def _maybe_interject(self, message):
        """Very occasionally, say something nobody asked for."""
        if random.random() >= INTERJECT_CHANCE:
            return

        now = message.created_at.timestamp()
        last = self._last_interjection.get(message.channel.id, 0)
        if now - last < INTERJECT_COOLDOWN:
            return
        self._last_interjection[message.channel.id] = now

        context = await self.recent_context(message.channel, limit=10)
        if not context:
            return

        prompt = (
            "You are quietly watching this conversation. Say one short, "
            "unsettling line about it, unprompted. Do not greet anyone or "
            "offer help.\n\n" + context
        )
        try:
            answer = await self.ask_gemini(prompt, remember=False)
        except GeminiError as exc:
            log.debug("interjection skipped: %s", exc)
            return
        await message.channel.send(answer[:1900])

    # ------------------------------------------------------------- commands

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def ask(self, ctx, *, question):
        """Ask Vessel something."""
        images = await self._collect_images(ctx.message)
        await self._reply(ctx, question, images=images)

    @commands.command(aliases=["see"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def look(self, ctx, *, note=None):
        """Show Vessel an image. Attach one, or reply to a message with one."""
        images = await self._collect_images(ctx.message)

        if not images and ctx.message.reference:
            ref = ctx.message.reference.resolved
            if isinstance(ref, discord.Message):
                images = await self._collect_images(ref)

        if not images:
            await ctx.send("There's nothing to look at.")
            return

        await self._reply(ctx, note or "Describe what you see.", images=images)

    @commands.command()
    @commands.cooldown(1, 30, commands.BucketType.channel)
    async def summarize(self, ctx, limit: int = 50):
        """Summarise the recent conversation in this channel."""
        limit = max(1, min(limit, 200))
        conversation = await self.recent_context(ctx.channel, limit=limit)

        if not conversation:
            await ctx.send("Nothing worth remembering.")
            return

        prompt = f"Summarise what happened in this conversation. Be brief.\n\n{conversation}"
        await self._reply(ctx, prompt, remember=False)

    @commands.command()
    async def forget(self, ctx):
        """Clear what Vessel remembers in this channel."""
        self.history.pop(ctx.channel.id, None)
        await asyncio.to_thread(self._save_memory)
        await ctx.send("Gone. As if none of you said anything.")


async def setup(bot):
    await bot.add_cog(AI(bot))
