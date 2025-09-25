diff --git a/bot.py b/bot.py
index 915111ae170dfdfb615afa167f3ba4dd4b32dbf9..2c9679aee294562e8dff4b07b35ecc59fcb60fe8 100644
--- a/bot.py
+++ b/bot.py
@@ -1,272 +1,319 @@
-# Add this to the very top of your bot.py file, right after the imports
+"""Main entry point for the KeyVerify Discord bot.
 
-import os
-import sys
-from dotenv import load_dotenv
+This module is responsible for validating configuration, bootstrapping the
+logging system, initialising the database pool, loading cogs and finally
+starting the Disnake interaction bot.  The previous version of this file was a
+mix of snippets from various guides which introduced duplicate imports,
+side‑effects during module import and other reliability issues that caused the
+process to appear to "stall" on hosting providers such as Railway.
 
-# Load environment variables first
-load_dotenv()
+The new implementation focuses on determinism and observability so that any
+misconfiguration is surfaced immediately in the logs instead of silently
+hanging during startup.
+"""
 
-def validate_environment():
-    """Validate all required environment variables"""
-    print("🔍 Checking environment variables...")
-    
-    required_vars = {
-        'DISCORD_TOKEN': 'Discord bot token',
-        'DATABASE_URL': 'PostgreSQL connection string',
-        'ENCRYPTION_KEY': 'Data encryption key',
-        'PAYHIP_API_KEY': 'Payhip API key'
-    }
-    
-    missing_vars = []
-    
-    for var, description in required_vars.items():
-        value = os.getenv(var)
-        if value:
-            # Show partial value for security
-            display_value = f"{value[:8]}..." if len(value) > 8 else "***"
-            print(f"✅ {var}: {display_value}")
-        else:
-            print(f"❌ {var}: MISSING ({description})")
-            missing_vars.append(var)
-    
-    if missing_vars:
-        print(f"\n💥 FATAL: Missing {len(missing_vars)} required environment variables!")
-        print("Go to Railway Dashboard → Your Project → Variables tab")
-        print("Add these variables:")
-        for var in missing_vars:
-            print(f"  • {var}")
-        sys.exit(1)
-    
-    print("✅ All environment variables are present!")
-    return True
+from __future__ import annotations
 
-# Call this immediately
-validate_environment()
-import disnake
-from disnake.ext import commands
-import os
-import sys
 import asyncio
+import logging
+import os
 import signal
+import sys
+from typing import Dict
+
+import disnake
+from disnake.ext import commands
 from dotenv import load_dotenv
-from utils.database import initialize_database, get_database_pool
-from utils.logging_config import setup_logging
-from handlers.verification_handler import VerificationButton
-from handlers.ticket_handler import TicketButton
+
 import config
+from handlers.ticket_handler import TicketButton
+from handlers.verification_handler import VerificationButton
+from utils.database import get_database_pool, initialize_database
+from utils.logging_config import setup_logging
+
+# ---------------------------------------------------------------------------
+# Environment handling
+# ---------------------------------------------------------------------------
+
+REQUIRED_ENV_VARS: Dict[str, str] = {
+    "DISCORD_TOKEN": "Discord bot token",
+    "DATABASE_URL": "PostgreSQL connection string",
+    "ENCRYPTION_KEY": "Data encryption key",
+    "PAYHIP_API_KEY": "Payhip API key",
+}
+
+OPTIONAL_ENV_VARS: Dict[str, str] = {
+    "LOG_LEVEL": "INFO",
+}
+
+
+def _strip_wrapping_quotes(value: str) -> str:
+    """Return *value* without surrounding quotes or whitespace.
+
+    Railway's variable editor sometimes injects wrapping quotes when values are
+    pasted.  That results in connection strings such as
+    ""postgres://user:pass@host/db"" which make `asyncpg` hang until its
+    timeout expires.  By trimming whitespace and a single pair of matching
+    quotes we ensure the bot always receives the intended raw value.
+    """
+
+    stripped = value.strip()
+    if not stripped:
+        return stripped
+
+    if (stripped.startswith("\"") and stripped.endswith("\"")) or (
+        stripped.startswith("'") and stripped.endswith("'")
+    ):
+        stripped = stripped[1:-1].strip()
+    return stripped
+
+
+def validate_environment() -> Dict[str, str]:
+    """Validate and sanitise required environment variables.
+
+    Returns a dictionary containing the cleaned values.  Missing variables cause
+    an immediate exit so the deploy fails fast instead of idling forever.
+    """
+
+    print("🔍 Checking environment variables…")
+
+    cleaned: Dict[str, str] = {}
+    missing: list[str] = []
+
+    for key, description in REQUIRED_ENV_VARS.items():
+        raw_value = os.getenv(key)
+        if raw_value is None or raw_value.strip() == "":
+            print(f"❌ {key}: MISSING ({description})")
+            missing.append(key)
+            continue
+
+        value = _strip_wrapping_quotes(raw_value)
+        if value != raw_value:
+            print(f"⚠️ {key}: removed wrapping quotes from supplied value")
+
+        cleaned[key] = value
+        os.environ[key] = value  # Make the sanitised value visible globally
+
+        preview = f"{value[:6]}…{value[-4:]}" if len(value) > 12 else "***"
+        print(f"✅ {key}: {preview}")
+
+    if missing:
+        print("\n💥 FATAL: missing required environment variables")
+        for key in missing:
+            print(f"  • {key}")
+        sys.exit(1)
+
+    # Populate optional values with defaults after sanitising
+    for key, default in OPTIONAL_ENV_VARS.items():
+        raw_value = os.getenv(key, default)
+        value = _strip_wrapping_quotes(raw_value)
+        os.environ[key] = value
+        cleaned[key] = value
+
+    print("✅ All required environment variables are present!\n")
+    return cleaned
 
-# Load environment variables
+
+# Load variables from .env files first (useful for local development)
 load_dotenv()
+ENV = validate_environment()
 
-DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
-LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
+# ---------------------------------------------------------------------------
+# Logging setup
+# ---------------------------------------------------------------------------
 
-if not DISCORD_TOKEN:
-    print("❌ DISCORD_TOKEN not found in environment variables")
-    sys.exit(1)
+setup_logging(ENV.get("LOG_LEVEL", "INFO"))
+logger = logging.getLogger(__name__)
 
-# Initialize logging
-setup_logging(LOG_LEVEL)
+# ---------------------------------------------------------------------------
+# Bot configuration
+# ---------------------------------------------------------------------------
 
-# Bot setup
 intents = disnake.Intents.default()
-intents.messages = True
 intents.guilds = True
 intents.members = True
+intents.messages = True
 
 command_sync_flags = commands.CommandSyncFlags.default()
 command_sync_flags.sync_commands_debug = False
 
 bot = commands.InteractionBot(
     intents=intents,
     command_sync_flags=command_sync_flags,
     max_messages=1000,
-    chunk_guilds_at_startup=False
+    chunk_guilds_at_startup=False,
 )
 
-# Load cogs with error handling
-COG_DIR = "cogs"
-cog_files = [
-    "add_product.py",
-    "blacklist.py", 
-    "bot_settings.py",
-    "enhanced_auto_roles.py",
-    "help.py",
-    "list_products.py",
-    "member_events.py",
-    "message_manager.py",
-    "remove_product.py",
-    "reset_key.py",
-    "role_management.py",
-    "server_log.py",
-    "server_utilities.py",
-    "start_verification.py",
-    "stock_management.py",
-    "ticket_categories.py",
-    "ticket_customization.py",
-    "ticket_management.py",
-    "ticket_system.py"
+COG_MODULES = [
+    "add_product",
+    "blacklist",
+    "bot_settings",
+    "enhanced_auto_roles",
+    "help",
+    "list_products",
+    "member_events",
+    "message_manager",
+    "remove_product",
+    "reset_key",
+    "role_management",
+    "server_log",
+    "server_utilities",
+    "start_verification",
+    "stock_management",
+    "ticket_categories",
+    "ticket_category_management",
+    "ticket_customization",
+    "ticket_management",
+    "ticket_system",
+    "review_system",
+    "sales_management",
 ]
 
-def load_cogs():
-    for filename in cog_files:
-        if os.path.exists(os.path.join(COG_DIR, filename)):
-            try:
-                bot.load_extension(f"{COG_DIR}.{filename[:-3]}")
-                print(f"✅ Loaded cog: {filename[:-3]}")
-            except Exception as e:
-                print(f"⚠️ Failed to load cog {filename[:-3]}: {e}")
-
-# Create ticket category management cog
-try:
-    ticket_category_management_content = '''import disnake
-from disnake.ext import commands
-from utils.database import get_database_pool
-from utils.permissions import owner_or_permission
-import config
-import logging
 
-logger = logging.getLogger(__name__)
+def load_cogs() -> None:
+    """Load all bot extensions with logging and graceful failure handling."""
+
+    for module in COG_MODULES:
+        module_path = f"cogs.{module}"
+        try:
+            bot.load_extension(module_path)
+            logger.info("✅ Loaded cog: %s", module_path)
+        except commands.ExtensionAlreadyLoaded:
+            logger.debug("Cog already loaded: %s", module_path)
+        except Exception:  # pragma: no cover - log full stack for visibility
+            logger.exception("⚠️ Failed to load cog %s", module_path)
+
+
+async def load_persistent_views() -> None:
+    """Restore persistent components from the database once the bot is ready."""
+
+    await bot.wait_until_ready()
+
+    try:
+        pool = await get_database_pool()
+    except Exception:
+        logger.exception("⚠️ Database pool not available; persistent views not loaded")
+        return
+
+    logger.info("🔄 Restoring persistent views from database…")
+
+    async with pool.acquire() as conn:
+        # Verification messages
+        try:
+            rows = await conn.fetch(
+                "SELECT guild_id, message_id, channel_id FROM verification_message"
+            )
+            for row in rows:
+                guild = bot.get_guild(int(row["guild_id"]))
+                if not guild:
+                    continue
+
+                channel = guild.get_channel(int(row["channel_id"]))
+                if not channel:
+                    await conn.execute(
+                        "DELETE FROM verification_message WHERE guild_id = $1",
+                        row["guild_id"],
+                    )
+                    continue
+
+                view = VerificationButton(row["guild_id"])
+                bot.add_view(view, message_id=int(row["message_id"]))
+                logger.info(
+                    "✅ Restored verification view for guild %s",
+                    row["guild_id"],
+                )
+        except Exception:
+            logger.exception("⚠️ Could not restore verification views")
+
+        # Ticket boxes
+        try:
+            rows = await conn.fetch(
+                "SELECT guild_id, message_id, channel_id FROM ticket_boxes"
+            )
+            for row in rows:
+                guild = bot.get_guild(int(row["guild_id"]))
+                if not guild:
+                    continue
+
+                channel = guild.get_channel(int(row["channel_id"]))
+                if not channel:
+                    await conn.execute(
+                        "DELETE FROM ticket_boxes WHERE guild_id = $1 AND message_id = $2",
+                        row["guild_id"],
+                        row["message_id"],
+                    )
+                    continue
+
+                view = TicketButton(row["guild_id"])
+                await view.setup_button(guild)
+                bot.add_view(view, message_id=int(row["message_id"]))
+                logger.info(
+                    "✅ Restored ticket view for guild %s",
+                    row["guild_id"],
+                )
+        except Exception:
+            logger.exception("⚠️ Could not restore ticket views")
+
+    logger.info("✅ Persistent views loaded")
 
-class TicketCategoryManagement(commands.Cog):
-    def __init__(self, bot):
-        self.bot = bot
-        self.bot.loop.create_task(self.setup_table())
-        
-    async def setup_table(self):
-        """Creates table for storing Discord category assignments"""
-        await self.bot.wait_until_ready()
-        async with (await get_database_pool()).acquire() as conn:
-            await conn.execute("""
-                CREATE TABLE IF NOT EXISTS ticket_discord_categories (
-                    guild_id TEXT NOT NULL,
-                    ticket_type TEXT NOT NULL,
-                    category_name TEXT,
-                    discord_category_id TEXT NOT NULL,
-                    PRIMARY KEY (guild_id, ticket_type, COALESCE(category_name, ''))
-                );
-            """)
-
-def setup(bot):
-    bot.add_cog(TicketCategoryManagement(bot))
-'''
-    
-    category_management_path = os.path.join(COG_DIR, "ticket_category_management.py")
-    if not os.path.exists(category_management_path):
-        with open(category_management_path, 'w') as f:
-            f.write(ticket_category_management_content)
-    
-    bot.load_extension("cogs.ticket_category_management")
-    print("✅ Loaded cog: ticket_category_management")
-except Exception as e:
-    print(f"⚠️ Failed to load ticket_category_management: {e}")
 
 @bot.event
-async def on_ready():
-    print(f"🤖 Bot is online as {bot.user}!")
+async def on_ready() -> None:
+    logger.info("🤖 Bot is online as %s", bot.user)
     for guild in bot.guilds:
-        print(f"• {guild.name} (ID: {guild.id})")
-    
-    # Set default status
-    try:
-        version = config.version
-        default_activity = disnake.Game(name=f"/help | {version}")
-        await bot.change_presence(activity=default_activity)
-        print("✅ Status set")
-    except Exception as e:
-        print(f"⚠️ Could not set status: {e}")
-
-    # Load persistent views asynchronously
-    asyncio.create_task(load_views())
-
-async def load_views():
-    """Load persistent views without blocking"""
+        logger.info("• %s (ID: %s)", guild.name, guild.id)
+
     try:
-        async with (await get_database_pool()).acquire() as conn:
-            # Load verification messages
-            try:
-                verification_rows = await conn.fetch("SELECT guild_id, message_id, channel_id FROM verification_message")
-                for row in verification_rows:
-                    guild_id, message_id, channel_id = row["guild_id"], row["message_id"], row["channel_id"]
-                    guild = bot.get_guild(int(guild_id))
-                    if guild:
-                        channel = guild.get_channel(int(channel_id))
-                        if channel:
-                            view = VerificationButton(guild_id)
-                            bot.add_view(view, message_id=int(message_id))
-                            print(f"✅ Verification message loaded for guild {guild_id}")
-                        else:
-                            await conn.execute("DELETE FROM verification_message WHERE guild_id = $1", guild_id)
-            except Exception as e:
-                print(f"⚠️ Could not load verification views: {e}")
-                
-            # Load ticket boxes
-            try:
-                ticket_rows = await conn.fetch("SELECT guild_id, message_id, channel_id FROM ticket_boxes")
-                for row in ticket_rows:
-                    guild_id, message_id, channel_id = row["guild_id"], row["message_id"], row["channel_id"]
-                    guild = bot.get_guild(int(guild_id))
-                    if guild:
-                        channel = guild.get_channel(int(channel_id))
-                        if channel:
-                            view = TicketButton(guild_id)
-                            await view.setup_button(guild)
-                            bot.add_view(view, message_id=int(message_id))
-                            print(f"✅ Ticket box loaded for guild {guild_id}")
-                        else:
-                            await conn.execute("DELETE FROM ticket_boxes WHERE guild_id = $1 AND message_id = $2", 
-                                             guild_id, message_id)
-            except Exception as e:
-                print(f"⚠️ Could not load ticket views: {e}")
-                
-    except Exception as e:
-        print(f"⚠️ Database not ready for view loading: {e}")
-
-def signal_handler(signum, frame):
-    """Handle shutdown signals"""
-    print(f"🛑 Received signal {signum}, shutting down...")
-    asyncio.create_task(bot.close())
-
-# Register signal handlers
-signal.signal(signal.SIGTERM, signal_handler)
-signal.signal(signal.SIGINT, signal_handler)
-
-async def main():
-    """Main async function"""
+        activity = disnake.Game(name=f"/help | {config.version}")
+        await bot.change_presence(activity=activity)
+        logger.info("✅ Status set")
+    except Exception:
+        logger.exception("⚠️ Could not set status")
+
+    asyncio.create_task(load_persistent_views())
+
+
+async def _shutdown(signum: signal.Signals) -> None:
+    logger.info("🛑 Received signal %s – shutting down", signum.name)
+    await bot.close()
+
+
+async def main() -> None:
+    logger.info("🚀 Starting KeyVerify Bot…")
+
+    loop = asyncio.get_running_loop()
+    for sig in (signal.SIGINT, signal.SIGTERM):
+        try:
+            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(_shutdown(s)))
+        except NotImplementedError:
+            # add_signal_handler is not available on some platforms (e.g. Windows)
+            signal.signal(sig, lambda *_: asyncio.create_task(_shutdown(sig)))
+
+    logger.info("📀 Initialising database…")
     try:
-        print("🚀 Starting KeyVerify Bot...")
-        
-        # Initialize database with timeout
-        print("📀 Initializing database...")
         await asyncio.wait_for(initialize_database(), timeout=60)
-        print("✅ Database initialized")
-        
-        # Load cogs
-        print("⚙️ Loading cogs...")
-        load_cogs()
-        print("✅ Cogs loaded")
-        
-        # Start bot
-        print("🤖 Starting Discord bot...")
-        await bot.start(DISCORD_TOKEN)
-        
+        logger.info("✅ Database initialised")
     except asyncio.TimeoutError:
-        print("❌ Startup timed out!")
-        sys.exit(1)
-    except Exception as e:
-        print(f"❌ Startup failed: {e}")
-        sys.exit(1)
+        logger.error("❌ Database initialisation timed out after 60 seconds")
+        raise
+
+    logger.info("⚙️ Loading cogs…")
+    load_cogs()
+    logger.info("✅ All cogs loaded")
+
+    logger.info("🤖 Connecting to Discord…")
+    await bot.start(ENV["DISCORD_TOKEN"])
 
-def run():
-    """Entry point"""
+
+def run() -> None:
     try:
         asyncio.run(main())
     except KeyboardInterrupt:
-        print("🛑 Bot shutdown requested")
-    except Exception as e:
-        print(f"💥 Fatal error: {e}")
+        logger.info("🛑 Bot shutdown requested by keyboard interrupt")
+    except Exception as exc:
+        logger.exception("💥 Fatal error during startup: %s", exc)
         sys.exit(1)
 
+
 if __name__ == "__main__":
     run()
