import disnake
import logging
from disnake.ext import commands
from utils.database import get_database_pool, fetch_products
from handlers.verification_handler import create_verification_embed, create_verification_view
import config

logger = logging.getLogger(__name__)

# This cog allows a server owner to create or update a persistent verification message in a Discord channel.
# The message includes an interactive button users can click to begin the license verification process.
class StartVerification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        description="Start the product verification process (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def start_verification(self, inter: disnake.ApplicationCommandInteraction): 
        # Ensure only the server owner can use this command
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can use this command.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Fetch products and create the embed and view
        products = await fetch_products(str(inter.guild.id))
        has_products = bool(products)

        embed = create_verification_embed()
        view = create_verification_view(str(inter.guild.id))

        # If no products exist, disable the Verify button
        if not has_products:
            for item in view.children:
                item.disabled = True

        async with (await get_database_pool()).acquire() as conn:
            result = await conn.fetchrow(
                "SELECT message_id, channel_id FROM verification_message WHERE guild_id = $1",
                str(inter.guild.id)
            )

            if result:
                # Try to update the existing verification message
                try:
                    channel = inter.guild.get_channel(int(result["channel_id"]))
                    if not channel:
                        raise disnake.NotFound("Channel not found", f"Channel ID: {result['channel_id']}")

                    existing_message = await channel.fetch_message(int(result["message_id"]))
                    await existing_message.edit(embed=embed, view=view)
                    await inter.response.send_message(
                        "✅ Verification message updated successfully.",
                        ephemeral=True,
                        delete_after=config.message_timeout
                    )
                except disnake.NotFound as e:
                    logging.error(f"NotFound error: {e}")
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
                        "✅ New verification message created successfully.",
                        ephemeral=True,
                        delete_after=config.message_timeout
                    )
            else:
                # If no verification message exists, send a new one and store it
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

                # If first-time setup, send onboarding guide to the server owner
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

# Register the cog with the bot

def setup(bot):
    bot.add_cog(StartVerification(bot))
