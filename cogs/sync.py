import disnake
from disnake.ext import commands
import config
import logging

logger = logging.getLogger(__name__)

# Put your user ID(s) here
ALLOWED_OWNERS = [336584067044868097] 

class Sync(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        description="Sync slash commands with Discord (bot owner only)."
    )
    async def sync(
        self,
        inter: disnake.ApplicationCommandInteraction,
        scope: str = commands.Param(
            default="guild",
            choices=["guild", "global"],
            description="Choose where to sync your commands"
        )
    ):
        if inter.author.id not in ALLOWED_OWNERS:
            await inter.response.send_message(
                "❌ Only the bot owner can use this.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        await inter.response.defer(ephemeral=True)

        try:
            if scope == "guild":
                synced = await self.bot.application_command_sync(guild=inter.guild)
                scope_label = f"**{inter.guild.name}**"
            else:
                synced = await self.bot.application_command_sync()
                scope_label = "**globally** 🌍 (may take up to 1 hour)"

            await inter.followup.send(
                f"✅ Synced `{len(synced)}` command(s) {scope_label}.",
                ephemeral=True,
                delete_after=config.message_timeout
            )

        except Exception as e:
            logger.exception("[SYNC] Failed to sync commands")
            await inter.followup.send(
                f"❌ Failed to sync commands:\n```{str(e)}```",
                ephemeral=True,
                delete_after=config.message_timeout
            )

def setup(bot):
    bot.add_cog(Sync(bot))
