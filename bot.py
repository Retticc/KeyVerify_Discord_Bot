import disnake
from disnake.ext import commands
import os
from dotenv import load_dotenv
from utils.database import initialize_database, get_database_pool, fetch_products
from utils.logging_config import setup_logging
from handlers.verification_handler import VerificationButton
import threading

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
       
    async with (await get_database_pool()).acquire() as conn:
        rows = await conn.fetch("SELECT guild_id, message_id, channel_id FROM verification_message")
        for row in rows:
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

            # Initialize the persistent view
            view = VerificationButton(guild_id)
            bot.add_view(view, message_id=int(message_id))
            print(f"Verification message loaded for guild {guild_id}.")
            
for guild in bot.guilds:
    print(guild.name)
    
# Run the bot
def run():
    bot.loop.run_until_complete(initialize_database())
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    run()
