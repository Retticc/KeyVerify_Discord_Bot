import disnake
from disnake.ext import commands
from utils.database import get_database_pool
import config
import asyncio

# This cog allows a server owner to define a log channel where license verifications will be announced.
class SetLogChannel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Schedule the database table creation as a background task after the bot is ready
        self.bot.loop.create_task(self.setup_table())
        
    # Ensures the required table exists for storing log channel mappings
    async def setup_table(self):
        await self.bot.wait_until_ready()  # Ensure bot is fully loaded
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS server_log_channels (
                    guild_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL
                );
            """)

    @commands.slash_command(
        description="Set a channel to log successful verifications (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True)
    )
    async def set_lchannel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        channel: disnake.TextChannel
    ):
        # This command allows the server owner to set or update the log channel for license verification events.
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message("❌ Only the server owner can set the log channel.", ephemeral=True,delete_after=config.message_timeout)
            return

        async with (await get_database_pool()).acquire() as conn:
            await conn.execute(
                """
                INSERT INTO server_log_channels (guild_id, channel_id)
                VALUES ($1, $2)
                ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2
                """,
                str(inter.guild.id), str(channel.id)
            )

        await inter.response.send_message(
            f"✅ Verification log channel set to {channel.mention}.",
            ephemeral=True,
            delete_after=config.message_timeout
        )

# Registers the SetLogChannel cog with the bot
def setup(bot):
    bot.add_cog(SetLogChannel(bot))
