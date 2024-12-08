import disnake
from disnake.ext import commands
from utils.database import get_database_pool, fetch_products
from handlers.verification_handler import create_verification_embed, create_verification_view
import config

class StartVerification(commands.Cog):
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
        if not products:
            await inter.response.send_message(
                "❌ No products are registered for this server.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        embed = create_verification_embed()
        view = create_verification_view(str(inter.guild.id))

        async with (await get_database_pool()).acquire() as conn:
            result = await conn.fetchrow(
                "SELECT message_id, channel_id FROM verification_message WHERE guild_id = $1",
                str(inter.guild.id)
            )

            if result:
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
                    # Handle cases where the message or channel is not found
                    logging.error(f"NotFound error: {e}")
                    new_message = await inter.channel.send(embed=embed, view=view)
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
                new_message = await inter.channel.send(embed=embed, view=view)
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

def setup(bot):
    bot.add_cog(StartVerification(bot))
