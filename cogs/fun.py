import random

from discord.ext import commands

EIGHTBALL = [
    "Obviously.",
    "No. Try asking something interesting.",
    "It already happened. You just haven't noticed.",
    "Ask me when you're alone.",
    "The answer won't help you.",
    "Yes, unfortunately.",
]


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def ping(self, ctx):
        """Check that Vessel is awake."""
        await ctx.send(f"Still here. ({self.bot.latency * 1000:.0f}ms)")

    @commands.command(name="8ball", aliases=["eightball"])
    async def eight_ball(self, ctx, *, question=None):
        """Ask a yes/no question you won't like the answer to."""
        if not question:
            await ctx.send("You have to actually ask something.")
            return
        await ctx.send(random.choice(EIGHTBALL))

    @commands.command()
    async def roll(self, ctx, sides: int = 6):
        """Roll a die."""
        sides = max(2, min(sides, 1000))
        await ctx.send(f"{random.randint(1, sides)}. Out of {sides}.")

    @commands.command()
    async def choose(self, ctx, *, options=None):
        """Pick one. Separate the options with commas."""
        choices = [o.strip() for o in (options or "").split(",") if o.strip()]
        if len(choices) < 2:
            await ctx.send("Give me at least two things, separated by commas.")
            return
        await ctx.send(f"{random.choice(choices)}. You were going to pick it anyway.")


async def setup(bot):
    await bot.add_cog(Fun(bot))
