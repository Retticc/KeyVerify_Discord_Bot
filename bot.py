import disnake
from disnake.ext import commands
import os
from dotenv import load_dotenv
from utils.database import initialize_database, get_database_pool, fetch_products
from utils.logging_config import setup_logging
from handlers.verification_handler import VerificationButton
from handlers.ticket_handler import TicketButton
import threading
import config

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Initialize logging
setup_logging(LOG_LEVEL)

# Bot setup
intents = disnake.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
command_sync_flags = commands.CommandSyncFlags.default()
command_sync_flags.sync_commands_debug = True

bot = commands.InteractionBot(intents=intents,command_sync_flags=command_sync_flags,)

# Load all cogs dynamically
COG_DIR = "cogs"
for filename in os.listdir(COG_DIR):
    if filename.endswith(".py") and not filename.startswith("__"):
        bot.load_extension(f"{COG_DIR}.{filename[:-3]}")

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}!")
    for guild in bot.guilds:
        print(f"• {guild.name} (ID: {guild.id})")
    version = config.version  # Replace with your actual version, or load from a config
    activity = disnake.Game(name=f"/help | {version}")
    await bot.change_presence(activity=activity)    
       
    async with (await get_database_pool()).acquire() as conn:
        # Load verification messages
        verification_rows = await conn.fetch("SELECT guild_id, message_id, channel_id FROM verification_message")
        for row in verification_rows:
            guild_id, message_id, channel_id = row["guild_id"], row["message_id"], row["channel_id"]

            guild = bot.get_guild(int(guild_id))
            if not guild:
                continue

            channel = guild.get_channel(int(channel_id))
            if not channel:
                await conn.execute("DELETE FROM verification_message WHERE guild_id = $1", guild_id)
                continue

            products = await fetch_products(guild_id)
            if not products:
                continue

            # Initialize the persistent verification view
            view = VerificationButton(guild_id)
            bot.add_view(view, message_id=int(message_id))
            print(f"Verification message loaded for guild {guild_id}.")
            
        # Load ticket boxes
        try:
            ticket_rows = await conn.fetch("SELECT guild_id, message_id, channel_id FROM ticket_boxes")
            for row in ticket_rows:
                guild_id, message_id, channel_id = row["guild_id"], row["message_id"], row["channel_id"]

                guild = bot.get_guild(int(guild_id))
                if not guild:
                    continue

                channel = guild.get_channel(int(channel_id))
                if not channel:
                    await conn.execute("DELETE FROM ticket_boxes WHERE guild_id = $1 AND message_id = $2", 
                                     guild_id, message_id)
                    continue

                # Initialize the persistent ticket view with custom settings
                view = TicketButton(guild_id)
                await view.setup_button(guild)  # Setup custom button text/emoji
                bot.add_view(view, message_id=int(message_id))
                print(f"Ticket box loaded for guild {guild_id}.")
        except Exception as e:
            print(f"Note: Ticket system tables not yet created: {e}")
            
# Run the bot
def run():
    bot.loop.run_until_complete(initialize_database())
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    run()
