# Create cogs/bot_settings.py

import disnake
from disnake.ext import commands
from utils.database import get_database_pool
import config
import logging

logger = logging.getLogger(__name__)

class BotSettings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.setup_table())
        
    async def setup_table(self):
        """Creates table for storing bot settings"""
        await self.bot.wait_until_ready()
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    guild_id TEXT NOT NULL,
                    setting_name TEXT NOT NULL,
                    setting_value TEXT NOT NULL,
                    PRIMARY KEY (guild_id, setting_name)
                );
            """)

    @commands.slash_command(
        description="Set the bot's status message (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def set_bot_status(
        self,
        inter: disnake.ApplicationCommandInteraction,
        status_text: str,
        status_type: str = commands.Param(
            choices=["Playing", "Listening", "Watching", "Streaming"],
            default="Playing"
        )
    ):
        """Set custom bot status"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can change bot settings.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Map status types to disnake activity types
        activity_map = {
            "Playing": disnake.Game,
            "Listening": lambda name: disnake.Activity(type=disnake.ActivityType.listening, name=name),
            "Watching": lambda name: disnake.Activity(type=disnake.ActivityType.watching, name=name),
            "Streaming": lambda name: disnake.Streaming(name=name, url="https://twitch.tv/keyverify")
        }

        try:
            # Set the bot's status
            activity = activity_map[status_type](status_text)
            await self.bot.change_presence(activity=activity)

            # Save to database for persistence
            async with (await get_database_pool()).acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO bot_settings (guild_id, setting_name, setting_value)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id, setting_name)
                    DO UPDATE SET setting_value = $3
                    """,
                    str(inter.guild.id), "bot_status", f"{status_type}:{status_text}"
                )

            await inter.response.send_message(
                f"✅ Bot status set to: **{status_type}** `{status_text}`",
                ephemeral=True,
                delete_after=config.message_timeout
            )

            logger.info(f"[Bot Status] {inter.author} set bot status to '{status_type}: {status_text}' in '{inter.guild.name}'")

        except Exception as e:
            await inter.response.send_message(
                f"❌ Failed to set bot status: {str(e)}",
                ephemeral=True
            )

    @commands.slash_command(
        description="Reset bot status to default (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def reset_bot_status(self, inter: disnake.ApplicationCommandInteraction):
        """Reset bot status to default"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can change bot settings.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        try:
            # Set default status
            version = config.version
            activity = disnake.Game(name=f"/help | {version}")
            await self.bot.change_presence(activity=activity)

            # Remove custom status from database
            async with (await get_database_pool()).acquire() as conn:
                await conn.execute(
                    "DELETE FROM bot_settings WHERE guild_id = $1 AND setting_name = $2",
                    str(inter.guild.id), "bot_status"
                )

            await inter.response.send_message(
                f"✅ Bot status reset to default: **Playing** `/help | {version}`",
                ephemeral=True,
                delete_after=config.message_timeout
            )

            logger.info(f"[Bot Status] {inter.author} reset bot status to default in '{inter.guild.name}'")

        except Exception as e:
            await inter.response.send_message(
                f"❌ Failed to reset bot status: {str(e)}",
                ephemeral=True
            )

    @commands.slash_command(
        description="View current bot settings (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def view_bot_settings(self, inter: disnake.ApplicationCommandInteraction):
        """View current bot settings"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can view bot settings.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            settings = await conn.fetch(
                "SELECT setting_name, setting_value FROM bot_settings WHERE guild_id = $1",
                str(inter.guild.id)
            )

        embed = disnake.Embed(
            title="🤖 Bot Settings",
            color=disnake.Color.blue()
        )

        if settings:
            for setting in settings:
                name = setting["setting_name"]
                value = setting["setting_value"]
                
                if name == "bot_status":
                    status_parts = value.split(":", 1)
                    if len(status_parts) == 2:
                        status_type, status_text = status_parts
                        embed.add_field(
                            name="🎭 Bot Status",
                            value=f"**{status_type}** `{status_text}`",
                            inline=False
                        )
                else:
                    embed.add_field(
                        name=name.replace("_", " ").title(),
                        value=f"`{value}`",
                        inline=False
                    )
        else:
            embed.description = "No custom settings configured. All settings are using defaults."

        # Show current activity
        current_activity = self.bot.activity
        if current_activity:
            activity_type = "Playing"
            if hasattr(current_activity, 'type'):
                if current_activity.type == disnake.ActivityType.listening:
                    activity_type = "Listening"
                elif current_activity.type == disnake.ActivityType.watching:
                    activity_type = "Watching"
                elif current_activity.type == disnake.ActivityType.streaming:
                    activity_type = "Streaming"
            
            embed.add_field(
                name="📊 Current Status",
                value=f"**{activity_type}** `{current_activity.name}`",
                inline=False
            )

        embed.set_footer(text="Use /set_bot_status to customize")
        await inter.response.send_message(embed=embed, ephemeral=True)

def setup(bot):
    bot.add_cog(BotSettings(bot))
