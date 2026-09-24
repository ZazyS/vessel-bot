# Vessel

A Discord bot with a persona, a Gemini-backed chat cog, music playback, and
ambient behaviour that makes it feel present rather than summoned.

## Setup

1. Install dependencies (already installed on this machine):

   ```
   pip install -r requirements.txt
   ```

   Music playback also needs FFmpeg on your PATH.

2. Put your bot token in `.env` — double-click `setup_token.bat`, or copy
   `.env.example` to `.env` and fill it in by hand:

   | Key | What it is |
   | --- | --- |
   | `DISCORD_TOKEN` | Bot token from the Discord Developer Portal |
   | `GEMINI_API_KEY` | Google AI Studio API key |
   | `GEMINI_MODEL` | Defaults to `gemini-3.6-flash` |
   | `HAUNT_CHANNEL_ID` | Channel the ambient line is posted to (0 disables it) |
   | `COMMAND_PREFIX` | Defaults to `!` |

3. In the Developer Portal, under Bot, enable **Message Content Intent**.
   Invite the bot with the `bot` scope and the Send Messages, Read Message
   History, Connect and Speak permissions.

4. Run it: double-click `run_vessel.bat`, or `python vessel.py`. The bot is
   online only while that window is open.

## Talking to it

You don't need a command. Mention it, or reply to something it said, and it
answers in character:

```
@Vessel why is it so cold in here
```

It remembers the last 10 turns per channel, and that memory now survives a
restart (stored in `vessel_memory.json`). Each channel remembers separately.

`!ask <question>` still works if you prefer.

## Ambient behaviour

- **The haunt.** Every 4 hours it posts one unprompted line to the channel in
  `HAUNT_CHANNEL_ID`. The line is written from whatever people were actually
  just talking about, so it references real conversation. If the API fails or
  the channel has been silent, it falls back to a fixed line.
- **Interjections.** Roughly 1 message in 300 gets an uninvited remark, and
  never more than once every 30 minutes per channel.
- **Status.** Rotates every 20 minutes — "watching the message box", and so on.

## Commands

**AI** — `!ask <question>`, `!look` (show it an image), `!summarize [count]`,
`!forget`

`!look` reads an image you attach, or one in the message you're replying to.
You can also just attach an image and mention the bot.

**Music** — `!play <url or search>` (`!p`), `!skip`, `!queue` (`!q`),
`!nowplaying` (`!np`), `!pause`, `!resume`, `!volume 0-100`, `!stop` (`!leave`)

Leaves after 3 minutes idle, or 30 seconds after the last human leaves.

**Fun** — `!ping`, `!8ball <question>`, `!roll [sides]`, `!choose a, b, c`

## Layout

```
vessel.py         entry point and error handling
config.py         reads .env (no external dependency)
setup_token.bat   one-time token setup
run_vessel.bat    start the bot
cogs/ai.py        Gemini chat, mentions, images, memory
cogs/presence.py  the haunt loop and rotating status
cogs/music.py     yt-dlp + FFmpeg voice playback
cogs/fun.py       small commands
```

## Notes

Secrets live in `.env`, which `.gitignore` excludes. Don't paste keys into
source files — if one ends up somewhere it shouldn't, rotate it rather than
just deleting the line.

`vessel_memory.json` holds what the bot remembers people saying. If other
people use your server, it's worth telling them the bot keeps a short memory
of the conversation.
