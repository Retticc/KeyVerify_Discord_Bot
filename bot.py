import disnake
from disnake.ext import commands
import os
import asyncio
from dotenv import load_dotenv
from utils.database import initialize_database, get_database_pool
from utils.logging_config import setup_logging
import config

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Validate environment variables
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is not set!")

# Initialize logging
setup_logging(LOG_LEVEL)

# Bot setup with more conservative settings
intents = disnake.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True

command_sync_flags = commands.CommandSyncFlags.default()
command_sync_flags.sync_commands_debug = False  # Disable debug to reduce startup time

bot = commands.InteractionBot(
    intents=intents,
    command_sync_flags=command_sync_flags,
    sync_commands_on_cog_reload=False  # Prevent unnecessary syncing
)

# Load cogs with error handling
def load_cogs():
    COG_DIR = "cogs"
    essential_cogs = [
        "help.py",
        "add_product.py", 
        "list_products.py",
        "start_verification.py",
        "ticket_system.py"
    ]
    
    # Load essential cogs first
    for filename in essential_cogs:
        if os.path.exists(os.path.join(COG_DIR, filename)):
            try:
                bot.load_extension(f"{COG_DIR}.{filename[:-3]}")
                print(f"✅ Loaded essential cog: {filename[:-3]}")
            except Exception as e:
                print(f"❌ Failed to load essential cog {filename[:-3]}: {e}")
                # Don't exit, but log the error
    
    # Load other cogs
    other_cogs = [
        "blacklist.py", "bot_settings.py", "enhanced_auto_roles.py",
        "member_events.py", "message_manager.py", "remove_product.py",
        "reset_key.py", "role_management.py", "server_log.py",
        "server_utilities.py", "stock_management.py", "ticket_categories.py",
        "ticket_customization.py", "ticket_management.py"
    ]
    
    for filename in other_cogs:
        if os.path.exists(os.path.join(COG_DIR, filename)):
            try:
                bot.load_extension(f"{COG_DIR}.{filename[:-3]}")
                print(f"✅ Loaded cog: {filename[:-3]}")
            except Exception as e:
                print(f"⚠️ Failed to load optional cog {filename[:-3]}: {e}")
                # Continue loading other cogs

@bot.event
async def on_ready():
    print(f"🤖 Bot is online as {bot.user}!")
    print(f"📊 Connected to {len(bot.guilds)} guilds")
    
    # Set default status quickly
    try:
        version = config.version
        activity = disnake.Game(name=f"/help | {version}")
        await bot.change_presence(activity=activity)
        print("✅ Default status set")
    except Exception as e:
        print(f"⚠️ Could not set status: {e}")

async def main():
    """Main async function to handle startup sequence"""
    try:
        print("🚀 Starting KeyVerify Bot...")
        
        # Step 1: Initialize database with timeout
        print("📀 Initializing database...")
        await asyncio.wait_for(initialize_database(), timeout=60)
        print("✅ Database initialized")
        
        # Step 2: Load cogs
        print("⚙️ Loading cogs...")
        load_cogs()
        print("✅ Cogs loaded")
        
        # Step 3: Start bot
        print("🤖 Starting Discord bot...")
        await bot.start(DISCORD_TOKEN)
        
    except asyncio.TimeoutError:
        print("❌ Startup timed out!")
        raise
    except Exception as e:
        print(f"❌ Startup failed: {e}")
        raise

def run():
    """Entry point for the bot"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Bot shutdown requested")
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        exit(1)

if __name__ == "__main__":
    run()
