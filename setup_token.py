"""One-time helper: put your bot token into .env and check that it works.

Run:  python setup_token.py

The token is not echoed to the screen and is not stored anywhere except .env.
"""
import asyncio
import getpass
import re
import sys
from pathlib import Path

ENV_PATH = Path(__file__).with_name(".env")
PLACEHOLDER = "paste_your_bot_token_here"

# A Discord bot token is three dot-separated chunks; enough to catch a
# mis-paste (a truncated copy, or the application ID by mistake).
TOKEN_SHAPE = re.compile(r"^[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{20,}$")


def write_token(token):
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    out, replaced = [], False
    for line in lines:
        if line.strip().startswith("DISCORD_TOKEN="):
            out.append(f"DISCORD_TOKEN={token}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"DISCORD_TOKEN={token}")
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


async def check(token):
    """Validate the token without starting the bot."""
    import discord

    client = discord.Client(intents=discord.Intents.none())
    try:
        await client.login(token)
        return True, str(client.user)
    except discord.LoginFailure:
        return False, "Discord rejected that token. Reset it and try again."
    except Exception as exc:
        return False, f"Couldn't reach Discord ({exc})."
    finally:
        await client.close()


def main():
    print("Paste your bot token, then press Enter.")
    print("(It won't appear on screen as you paste - that's normal.)\n")

    token = getpass.getpass("Token: ").strip().strip('"').strip("'")

    if not token or token == PLACEHOLDER:
        print("\nNothing entered. Run this again when you have the token.")
        return 1

    if token.lower().startswith("bot "):
        token = token[4:].strip()

    if not TOKEN_SHAPE.match(token):
        print("\nThat doesn't look like a full bot token.")
        print("It should be three parts separated by dots, roughly 70+ characters.")
        print("Developer Portal -> your app -> Bot -> Reset Token -> Copy.")
        return 1

    print("\nChecking it with Discord...")
    ok, detail = asyncio.run(check(token))

    if not ok:
        print(f"\n{detail}")
        print("Nothing was saved.")
        return 1

    write_token(token)
    print(f"\nWorks. Logged in as {detail}.")
    print(f"Saved to {ENV_PATH.name}.\n")
    print("Two things left, both in the Developer Portal:")
    print("  1. Bot tab -> turn ON 'Message Content Intent'")
    print("  2. Make sure the bot has been invited to your server")
    print("\nThen start it with:  run_vessel.bat   (or: python vessel.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
