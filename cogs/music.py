"""Voice playback: search or stream audio with yt-dlp + FFmpeg.

Requires FFmpeg on PATH and PyNaCl installed (both already present here).
"""
import asyncio
import logging
from dataclasses import dataclass, field

import discord
import yt_dlp
from discord.ext import commands

log = logging.getLogger("vessel.music")

YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "ignoreerrors": False,
    "skip_download": True,
}

FFMPEG_OPTS = {
    # Streams drop; tell ffmpeg to reconnect instead of ending the track early.
    "before_options": (
        "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
        "-loglevel error"
    ),
    "options": "-vn",
}

IDLE_TIMEOUT = 180  # seconds idle before leaving the channel

_ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)


@dataclass
class Track:
    title: str
    url: str          # page URL - the stream URL is resolved just before playing
    duration: int
    requester: str

    def pretty(self):
        if not self.duration:
            return self.title
        minutes, seconds = divmod(int(self.duration), 60)
        return f"{self.title} [{minutes}:{seconds:02d}]"


@dataclass
class GuildPlayer:
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    current: Track = None
    idle_task: asyncio.Task = None


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}

    def player_for(self, guild_id):
        return self.players.setdefault(guild_id, GuildPlayer())

    async def cog_unload(self):
        for guild in list(self.bot.guilds):
            if guild.voice_client:
                await guild.voice_client.disconnect(force=True)

    # ------------------------------------------------------------------ utils

    @staticmethod
    async def _extract(query):
        """Run the blocking yt-dlp call off the event loop."""
        def work():
            info = _ytdl.extract_info(query, download=False)
            if info and "entries" in info:
                entries = [e for e in info["entries"] if e]
                if not entries:
                    return None
                info = entries[0]
            return info

        return await asyncio.to_thread(work)

    async def _ensure_voice(self, ctx):
        """Connect to the caller's voice channel, moving if needed."""
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await ctx.send("Join a voice channel first.")
            return None

        channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            try:
                return await channel.connect()
            except asyncio.TimeoutError:
                await ctx.send("I couldn't get into that channel.")
                return None
        if ctx.voice_client.channel != channel:
            await ctx.voice_client.move_to(channel)
        return ctx.voice_client

    def _play_next(self, ctx, error=None):
        """`after` callback - runs on a worker thread, so bounce to the loop."""
        if error:
            log.warning("playback error: %s", error)
        asyncio.run_coroutine_threadsafe(self._advance(ctx), self.bot.loop)

    async def _advance(self, ctx):
        player = self.player_for(ctx.guild.id)
        voice = ctx.guild.voice_client
        if voice is None:
            player.current = None
            return

        try:
            track = player.queue.get_nowait()
        except asyncio.QueueEmpty:
            player.current = None
            self._start_idle_timer(ctx)
            return

        # Resolve the stream URL now - these links expire within a few hours,
        # so resolving at queue time would break anything but a short queue.
        try:
            info = await self._extract(track.url)
            source_url = info["url"] if info else None
        except Exception as exc:
            log.warning("could not resolve %s: %s", track.url, exc)
            source_url = None

        if not source_url:
            await ctx.send(f"Couldn't play **{track.title}**. Moving on.")
            await self._advance(ctx)
            return

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(source_url, **FFMPEG_OPTS), volume=0.5
        )
        player.current = track
        voice.play(source, after=lambda e: self._play_next(ctx, e))
        await ctx.send(f"Playing **{track.pretty()}**")

    def _start_idle_timer(self, ctx):
        player = self.player_for(ctx.guild.id)
        if player.idle_task and not player.idle_task.done():
            player.idle_task.cancel()

        async def leave_when_idle():
            await asyncio.sleep(IDLE_TIMEOUT)
            voice = ctx.guild.voice_client
            if voice and not voice.is_playing() and player.queue.empty():
                await voice.disconnect()
                player.current = None

        player.idle_task = self.bot.loop.create_task(leave_when_idle())

    # --------------------------------------------------------------- commands

    @commands.command(aliases=["p"])
    @commands.guild_only()
    async def play(self, ctx, *, query):
        """Play a track, or add it to the queue. Accepts a URL or search text."""
        voice = await self._ensure_voice(ctx)
        if voice is None:
            return

        async with ctx.typing():
            try:
                info = await self._extract(query)
            except Exception as exc:
                log.warning("search failed for %r: %s", query, exc)
                await ctx.send("I couldn't find that.")
                return

        if not info:
            await ctx.send("I couldn't find that.")
            return

        track = Track(
            title=info.get("title") or "unknown",
            url=info.get("webpage_url") or info.get("original_url") or query,
            duration=info.get("duration") or 0,
            requester=ctx.author.display_name,
        )

        player = self.player_for(ctx.guild.id)
        if player.idle_task and not player.idle_task.done():
            player.idle_task.cancel()

        await player.queue.put(track)

        if voice.is_playing() or voice.is_paused():
            await ctx.send(f"Queued **{track.pretty()}** (#{player.queue.qsize()})")
        else:
            await self._advance(ctx)

    @commands.command()
    @commands.guild_only()
    async def skip(self, ctx):
        """Skip the current track."""
        voice = ctx.voice_client
        if voice is None or not (voice.is_playing() or voice.is_paused()):
            await ctx.send("Nothing is playing.")
            return
        voice.stop()  # fires the after callback, which starts the next track
        await ctx.send("Skipped.")

    @commands.command(name="queue", aliases=["q"])
    @commands.guild_only()
    async def show_queue(self, ctx):
        """Show what is lined up."""
        player = self.player_for(ctx.guild.id)
        upcoming = list(player.queue._queue)

        if player.current is None and not upcoming:
            await ctx.send("The queue is empty.")
            return

        lines = []
        if player.current:
            lines.append(f"Now: **{player.current.pretty()}**")
        for index, track in enumerate(upcoming[:10], start=1):
            lines.append(f"{index}. {track.pretty()} - {track.requester}")
        if len(upcoming) > 10:
            lines.append(f"...and {len(upcoming) - 10} more.")
        await ctx.send("\n".join(lines)[:1900])

    @commands.command(aliases=["np"])
    @commands.guild_only()
    async def nowplaying(self, ctx):
        """Show the current track."""
        player = self.player_for(ctx.guild.id)
        if player.current is None:
            await ctx.send("Nothing is playing.")
            return
        await ctx.send(
            f"**{player.current.pretty()}** - asked for by {player.current.requester}"
        )

    @commands.command()
    @commands.guild_only()
    async def pause(self, ctx):
        """Pause playback."""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("Paused.")
        else:
            await ctx.send("Nothing is playing.")

    @commands.command()
    @commands.guild_only()
    async def resume(self, ctx):
        """Resume playback."""
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Go on then.")
        else:
            await ctx.send("Nothing is paused.")

    @commands.command()
    @commands.guild_only()
    async def volume(self, ctx, percent: int):
        """Set playback volume, 0-100."""
        if ctx.voice_client is None or ctx.voice_client.source is None:
            await ctx.send("Nothing is playing.")
            return
        percent = max(0, min(percent, 100))
        ctx.voice_client.source.volume = percent / 100
        await ctx.send(f"Volume {percent}%.")

    @commands.command(aliases=["leave", "disconnect"])
    @commands.guild_only()
    async def stop(self, ctx):
        """Clear the queue and leave the voice channel."""
        player = self.player_for(ctx.guild.id)
        while not player.queue.empty():
            player.queue.get_nowait()
        player.current = None
        if player.idle_task and not player.idle_task.done():
            player.idle_task.cancel()

        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("Leaving. You were getting boring.")
        else:
            await ctx.send("I'm not in a channel.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Leave once the humans have all gone."""
        if member.bot:
            return
        voice = member.guild.voice_client
        if voice is None or before.channel != voice.channel:
            return
        if any(not m.bot for m in voice.channel.members):
            return
        await asyncio.sleep(30)
        if voice.is_connected() and not any(
            not m.bot for m in voice.channel.members
        ):
            await voice.disconnect()


async def setup(bot):
    await bot.add_cog(Music(bot))
