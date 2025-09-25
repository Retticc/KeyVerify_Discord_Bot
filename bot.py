"""Main entry point for the KeyVerify Discord bot.

This module is responsible for validating configuration, bootstrapping the
logging system, initialising the database pool, loading cogs and finally
starting the Disnake interaction bot.  The previous version of this file was a
mix of snippets from various guides which introduced duplicate imports,
side‑effects during module import and other reliability issues that caused the
process to appear to "stall" on hosting providers such as Railway.

The new implementation focuses on determinism and observability so that any
misconfiguration is surfaced immediately in the logs instead of silently
hanging during startup.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from typing import Dict

import disnake
from disnake.ext import commands
from dotenv import load_dotenv

import config
from handlers.ticket_handler import TicketButton
from handlers.verification_handler import VerificationButton
from utils.database import get_database_pool, initialize_database
from utils.logging_config import setup_logging

# ---------------------------------------------------------------------------
# Environment handling
# ---------------------------------------------------------------------------

REQUIRED_ENV_VARS: Dict[str, str] = {
    "DISCORD_TOKEN": "Discord bot token",
    "DATABASE_URL": "PostgreSQL connection string",
    "ENCRYPTION_KEY": "Data encryption key",
    "PAYHIP_API_KEY": "Payhip API key",
}

OPTIONAL_ENV_VARS: Dict[str, str] = {
    "LOG_LEVEL": "INFO",
}


def _strip_wrapping_quotes(value: str) -> str:
    """Return *value* without surrounding quotes or whitespace.

    Railway's variable editor sometimes injects wrapping quotes when values are
    pasted.  That results in connection strings such as
    ""postgres://user:pass@host/db"" which make `asyncpg` hang until its
    timeout expires.  By trimming whitespace and a single pair of matching
    quotes we ensure the bot always receives the intended raw value.
    """

    stripped = value.strip()
    if not stripped:
        return stripped

    if (stripped.startswith("\"") and stripped.endswith("\"")) or (
        stripped.startswith("'") and stripped.endswith("'")
    ):
        stripped = stripped[1:-1].strip()
    return stripped


def validate_environment() -> Dict[str, str]:
    """Validate and sanitise required environment variables.

    Returns a dictionary containing the cleaned values.  Missing variables cause
    an immediate exit so the deploy fails fast instead of idling forever.
    """

    print("🔍 Checking environment variables…")

    cleaned: Dict[str, str] = {}
    missing: list[str] = []

    for key, description in REQUIRED_ENV_VARS.items():
        raw_value = os.getenv(key)
        if raw_value is None or raw_value.strip() == "":
            print(f"❌ {key}: MISSING ({description})")
            missing.append(key)
            continue

        value = _strip_wrapping_quotes(raw_value)
        if value != raw_value:
            print(f"⚠️ {key}: removed wrapping quotes from supplied value")

        cleaned[key] = value
        os.environ[key] = value  # Make the sanitised value visible globally

        preview = f"{value[:6]}…{value[-4:]}" if len(value) > 12 else "***"
        print(f"✅ {key}: {preview}")

    if missing:
        print("\n💥 FATAL: missing required environment variables")
        for key in missing:
            print(f"  • {key}")
        sys.exit(1)

    # Populate optional values with defaults after sanitising
    for key, default in OPTIONAL_ENV_VARS.items():
        raw_value = os.getenv(key, default)
        value = _strip_wrapping_quotes(raw_value)
        os.environ[key] = value
        cleaned[key] = value

    print("✅ All required environment variables are present!\n")
    return cleaned


# Load variables from .env files first (useful for local development)
load_dotenv()
ENV = validate_environment()

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

setup_logging(ENV.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bot configuration
# ---------------------------------------------------------------------------

intents = disnake.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True

command_sync_flags = commands.CommandSyncFlags.default()
command_sync_flags.sync_commands_debug = False

bot = commands.InteractionBot(
    intents=intents,
    command_sync_flags=command_sync_flags,
    max_messages=1000,
    chunk_guilds_at_startup=False,
)

COG_MODULES = [
    "add_product",
    "blacklist",
    "bot_settings",
    "enhanced_auto_roles",
    "help",
    "list_products",
    "member_events",
    "message_manager",
    "remove_product",
    "reset_key",
    "role_management",
    "server_log",
    "server_utilities",
    "start_verification",
    "stock_management",
    "ticket_categories",
    "ticket_category_management",
    "ticket_customization",
    "ticket_management",
    "ticket_system",
    "review_system",
    "sales_management",
]


def load_cogs() -> None:
    """Load all bot extensions with logging and graceful failure handling."""

    for module in COG_MODULES:
        module_path = f"cogs.{module}"
        try:
            bot.load_extension(module_path)
            logger.info("✅ Loaded cog: %s", module_path)
        except commands.ExtensionAlreadyLoaded:
            logger.debug("Cog already loaded: %s", module_path)
        except Exception:  # pragma: no cover - log full stack for visibility
            logger.exception("⚠️ Failed to load cog %s", module_path)


async def load_persistent_views() -> None:
    """Restore persistent components from the database once the bot is ready."""

    await bot.wait_until_ready()

    try:
        pool = await get_database_pool()
    except Exception:
        logger.exception("⚠️ Database pool not available; persistent views not loaded")
        return

    logger.info("🔄 Restoring persistent views from database…")

    async with pool.acquire() as conn:
        # Verification messages
        try:
            rows = await conn.fetch(
                "SELECT guild_id, message_id, channel_id FROM verification_message"
            )
            for row in rows:
                guild = bot.get_guild(int(row["guild_id"]))
                if not guild:
                    continue

                channel = guild.get_channel(int(row["channel_id"]))
                if not channel:
                    await conn.execute(
                        "DELETE FROM verification_message WHERE guild_id = $1",
                        row["guild_id"],
                    )
                    continue

                view = VerificationButton(row["guild_id"])
                bot.add_view(view, message_id=int(row["message_id"]))
                logger.info(
                    "✅ Restored verification view for guild %s",
                    row["guild_id"],
                )
        except Exception:
            logger.exception("⚠️ Could not restore verification views")

        # Ticket boxes
        try:
            rows = await conn.fetch(
                "SELECT guild_id, message_id, channel_id FROM ticket_boxes"
            )
            for row in rows:
                guild = bot.get_guild(int(row["guild_id"]))
                if not guild:
                    continue

                channel = guild.get_channel(int(row["channel_id"]))
                if not channel:
                    await conn.execute(
                        "DELETE FROM ticket_boxes WHERE guild_id = $1 AND message_id = $2",
                        row["guild_id"],
                        row["message_id"],
                    )
                    continue

                view = TicketButton(row["guild_id"])
                await view.setup_button(guild)
                bot.add_view(view, message_id=int(row["message_id"]))
                logger.info(
                    "✅ Restored ticket view for guild %s",
                    row["guild_id"],
                )
        except Exception:
            logger.exception("⚠️ Could not restore ticket views")

    logger.info("✅ Persistent views loaded")


@bot.event
async def on_ready() -> None:
    logger.info("🤖 Bot is online as %s", bot.user)
    for guild in bot.guilds:
        logger.info("• %s (ID: %s)", guild.name, guild.id)

    try:
        activity = disnake.Game(name=f"/help | {config.version}")
        await bot.change_presence(activity=activity)
        logger.info("✅ Status set")
    except Exception:
        logger.exception("⚠️ Could not set status")

    asyncio.create_task(load_persistent_views())


async def _shutdown(signum: signal.Signals) -> None:
    logger.info("🛑 Received signal %s – shutting down", signum.name)
    await bot.close()


async def main() -> None:
    logger.info("🚀 Starting KeyVerify Bot…")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(_shutdown(s)))
        except NotImplementedError:
            # add_signal_handler is not available on some platforms (e.g. Windows)
            signal.signal(sig, lambda *_: asyncio.create_task(_shutdown(sig)))

    logger.info("📀 Initialising database…")
    try:
        await asyncio.wait_for(initialize_database(), timeout=60)
        logger.info("✅ Database initialised")
    except asyncio.TimeoutError:
        logger.error("❌ Database initialisation timed out after 60 seconds")
        raise

    logger.info("⚙️ Loading cogs…")
    load_cogs()
    logger.info("✅ All cogs loaded")

    logger.info("🤖 Connecting to Discord…")
    await bot.start(ENV["DISCORD_TOKEN"])


def run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot shutdown requested by keyboard interrupt")
    except Exception as exc:
        logger.exception("💥 Fatal error during startup: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    run()
