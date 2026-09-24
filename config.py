"""Loads settings from a .env file sitting next to this file.

No external dependency: python-dotenv isn't installed and this is all we need.
Real values live in .env, which is gitignored. Never put keys in source files.
"""
import os
from pathlib import Path

ENV_PATH = Path(__file__).with_name(".env")


def _load_env():
    if not ENV_PATH.exists():
        return
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_env()


def _require(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set. Add it to {ENV_PATH} (copy .env.example to .env)."
        )
    return value


DISCORD_TOKEN = _require("DISCORD_TOKEN")
GEMINI_API_KEY = _require("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip()
HAUNT_CHANNEL_ID = int(os.environ.get("HAUNT_CHANNEL_ID", "0") or 0)
COMMAND_PREFIX = os.environ.get("COMMAND_PREFIX", "!").strip() or "!"
