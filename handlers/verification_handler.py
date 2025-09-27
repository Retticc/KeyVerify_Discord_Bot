import disnake
import logging
from disnake.ext import commands
from utils.database import get_database_pool, fetch_products
from handlers.verification_handler import create_verification_embed, create_verification_view
import config

logger = logging.getLogger(__name__)

class StartVerification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        description="Start the product verification process (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def start_verification(self, inter: disnake.ApplicationCommandInteraction): 
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can use this command.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        products = await fetch_products(str(inter.guild.id))
        has_products = bool(products)

        embed = create_verification_embed()
        view = create_verification_view(str(inter.guild.id))

        if not has_products:
            embed.description += "\n\n⚠️ *Note: No products are currently configured for this server.*"

        async with (await get_database_pool()).acquire() as conn:
            result = await conn.fetchrow(
                "SELECT message_id, channel_id FROM verification_message WHERE guild_id = $1",
                str(inter.guild.id)
            )

            if result:
                try:
                    channel = inter.guild.get_channel(int(result["channel_id"]))
                    if not channel:
                        # Channel not found, clean up and create new
                        await conn.execute("DELETE FROM verification_message WHERE guild_id = $1", str(inter.guild.id))
                        logger.warning(f"[Channel Missing] Verification channel {result['channel_id']} not found, cleaned up record")
                        # Continue to create new message below
                        result = None
                    else:
                        try:
                            existing_message = await channel.fetch_message(int(result["message_id"]))
                            await existing_message.edit(embed=embed, view=view)
                            await inter.response.send_message(
                                "✅ Verification message updated successfully.",
                                ephemeral=True,
                                delete_after=config.message_timeout
                            )
                            return
                        except disnake.NotFound:
                            # Message not found, clean up and create new
                            await conn.execute("DELETE FROM verification_message WHERE guild_id = $1", str(inter.guild.id))
                            logger.warning(f"[Message Missing] Verification message {result['message_id']} not found, cleaned up record")
                            result = None
                        except disnake.Forbidden:
                            await inter.response.send_message(
                                "❌ I don't have permission to edit the existing verification message. "
                                "Please make sure I have the **Send Messages** and **Embed Links** permissions in that channel.",
                                ephemeral=True
                            )
                            return
                except Exception as e:
                    logger.error(f"[Verification Update Error] {e}")
                    # Clean up and create new
                    await conn.execute("DELETE FROM verification_message WHERE guild_id = $1", str(inter.guild.id))
                    result = None

            # Create new verification message (either first time or after cleanup)
            if not result:
                try:
                    new_message = await inter.channel.send(embed=embed, view=view)
                except disnake.Forbidden:
                    await inter.response.send_message(
                        "❌ I don't have permission to send messages in this channel. "
                        "Please make sure I have the **Send Messages** and **Embed Links** permissions.",
                        ephemeral=True
                    )
                    return

                await conn.execute(
                    """
                    INSERT INTO verification_message (guild_id, message_id, channel_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id)
                    DO UPDATE SET message_id = $2, channel_id = $3
                    """,
                    str(inter.guild.id), str(new_message.id), str(inter.channel.id)
                )
                await inter.response.send_message(
                    "✅ Verification message created successfully.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )

                onboarding_embed = disnake.Embed(
                    title="Welcome to KeyVerify!",
                    description=(
                        "You've successfully set up the verification message! Here's what you can do next:\n\n"
                        "• `/add_product` — Add a product via a secure form\n"
                        "• `/list_products` — View current products and their roles\n"
                        "• `/remove_product` — Remove a product from the server\n"
                        "• `/reset_key` — Reset usage for a license key\n"
                        "• `/set_lchannel` — Set up a log channel for verified users\n"
                        "• `/help` —  Shows this message again + support server.\n"
                        "• `/start_verification` — Repost the verification message if needed"
                    ),
                    color=disnake.Color.green()
                )
                onboarding_embed.set_footer(text="Need help? Use /help at any time.")

                try:
                    await inter.author.send(embed=onboarding_embed)
                except disnake.Forbidden:
                    logger.warning(f"[Onboarding Failed] Could not DM {inter.author} after verification setup.")

def setup(bot):
    bot.add_cog(StartVerification(bot))
