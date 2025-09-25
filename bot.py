import disnake
from disnake.ext import commands
import os
import sys
import asyncio
import signal
from dotenv import load_dotenv
from utils.database import initialize_database, get_database_pool
from utils.logging_config import setup_logging
from handlers.verification_handler import VerificationButton
from handlers.ticket_handler import TicketButton
import config

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

if not DISCORD_TOKEN:
    print("❌ DISCORD_TOKEN not found in environment variables")
    sys.exit(1)

# Initialize logging
setup_logging(LOG_LEVEL)

# Bot setup
intents = disnake.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True

command_sync_flags = commands.CommandSyncFlags.default()
command_sync_flags.sync_commands_debug = False

bot = commands.InteractionBot(
    intents=intents,
    command_sync_flags=command_sync_flags,
    max_messages=1000,
    chunk_guilds_at_startup=False
)

# Load cogs with error handling
COG_DIR = "cogs"
cog_files = [
    "add_product.py",
    "blacklist.py", 
    "bot_settings.py",
    "enhanced_auto_roles.py",
    "help.py",
    "list_products.py",
    "member_events.py",
    "message_manager.py",
    "remove_product.py",
    "reset_key.py",
    "role_management.py",
    "server_log.py",
    "server_utilities.py",
    "start_verification.py",
    "stock_management.py",
    "ticket_categories.py",
    "ticket_customization.py",
    "ticket_management.py",
    "ticket_system.py"
]

def load_cogs():
    for filename in cog_files:
        if os.path.exists(os.path.join(COG_DIR, filename)):
            try:
                bot.load_extension(f"{COG_DIR}.{filename[:-3]}")
                print(f"✅ Loaded cog: {filename[:-3]}")
            except Exception as e:
                print(f"⚠️ Failed to load cog {filename[:-3]}: {e}")

# Create ticket category management cog
try:
    ticket_category_management_content = '''import disnake
from disnake.ext import commands
from utils.database import get_database_pool
from utils.permissions import owner_or_permission
import config
import logging

logger = logging.getLogger(__name__)

class TicketCategoryManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.setup_table())
        
    async def setup_table(self):
        """Creates table for storing Discord category assignments"""
        await self.bot.wait_until_ready()
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_discord_categories (
                    guild_id TEXT NOT NULL,
                    ticket_type TEXT NOT NULL,
                    category_name TEXT,
                    discord_category_id TEXT NOT NULL,
                    PRIMARY KEY (guild_id, ticket_type, COALESCE(category_name, ''))
                );
            """)

def setup(bot):
    bot.add_cog(TicketCategoryManagement(bot))
'''
    
    category_management_path = os.path.join(COG_DIR, "ticket_category_management.py")
    if not os.path.exists(category_management_path):
        with open(category_management_path, 'w') as f:
            f.write(ticket_category_management_content)
    
    bot.load_extension("cogs.ticket_category_management")
    print("✅ Loaded cog: ticket_category_management")
except Exception as e:
    print(f"⚠️ Failed to load ticket_category_management: {e}")

@bot.event
async def on_ready():
    print(f"🤖 Bot is online as {bot.user}!")
    for guild in bot.guilds:
        print(f"• {guild.name} (ID: {guild.id})")
    
    # Set default status
    try:
        version = config.version
        default_activity = disnake.Game(name=f"/help | {version}")
        await bot.change_presence(activity=default_activity)
        print("✅ Status set")
    except Exception as e:
        print(f"⚠️ Could not set status: {e}")

    # Load persistent views asynchronously
    asyncio.create_task(load_views())

async def load_views():
    """Load persistent views without blocking"""
    try:
        async with (await get_database_pool()).acquire() as conn:
            # Load verification messages
            try:
                verification_rows = await conn.fetch("SELECT guild_id, message_id, channel_id FROM verification_message")
                for row in verification_rows:
                    guild_id, message_id, channel_id = row["guild_id"], row["message_id"], row["channel_id"]
                    guild = bot.get_guild(int(guild_id))
                    if guild:
                        channel = guild.get_channel(int(channel_id))
                        if channel:
                            view = VerificationButton(guild_id)
                            bot.add_view(view, message_id=int(message_id))
                            print(f"✅ Verification message loaded for guild {guild_id}")
                        else:
                            await conn.execute("DELETE FROM verification_message WHERE guild_id = $1", guild_id)
            except Exception as e:
                print(f"⚠️ Could not load verification views: {e}")
                
            # Load ticket boxes
            try:
                ticket_rows = await conn.fetch("SELECT guild_id, message_id, channel_id FROM ticket_boxes")
                for row in ticket_rows:
                    guild_id, message_id, channel_id = row["guild_id"], row["message_id"], row["channel_id"]
                    guild = bot.get_guild(int(guild_id))
                    if guild:
                        channel = guild.get_channel(int(channel_id))
                        if channel:
                            view = TicketButton(guild_id)
                            await view.setup_button(guild)
                            bot.add_view(view, message_id=int(message_id))
                            print(f"✅ Ticket box loaded for guild {guild_id}")
                        else:
                            await conn.execute("DELETE FROM ticket_boxes WHERE guild_id = $1 AND message_id = $2", 
                                             guild_id, message_id)
            except Exception as e:
                print(f"⚠️ Could not load ticket views: {e}")
                
    except Exception as e:
        print(f"⚠️ Database not ready for view loading: {e}")

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    print(f"🛑 Received signal {signum}, shutting down...")
    asyncio.create_task(bot.close())

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

async def main():
    """Main async function"""
    try:
        print("🚀 Starting KeyVerify Bot...")
        
        # Initialize database with timeout
        print("📀 Initializing database...")
        await asyncio.wait_for(initialize_database(), timeout=60)
        print("✅ Database initialized")
        
        # Load cogs
        print("⚙️ Loading cogs...")
        load_cogs()
        print("✅ Cogs loaded")
        
        # Start bot
        print("🤖 Starting Discord bot...")
        await bot.start(DISCORD_TOKEN)
        
    except asyncio.TimeoutError:
        print("❌ Startup timed out!")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Startup failed: {e}")
        sys.exit(1)

def run():
    """Entry point"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Bot shutdown requested")
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run()
