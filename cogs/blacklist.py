import disnake
from disnake.ext import commands
import requests
from utils.database import get_database_pool
from utils.encryption import decrypt_data
import os  # To access environment variables
import config

class RemoveUser(commands.Cog):
    """Handles removing a user and deactivating their licenses."""

    def __init__(self, bot: commands.InteractionBot):
        self.bot = bot
        self.payhip_api_key = os.getenv("PAYHIP_API_KEY")  # Fetch the Payhip API key directly from environment variables
        if not self.payhip_api_key:
            raise ValueError("PAYHIP_API_KEY is not defined in environment variables.")

    @commands.slash_command(
        description="Remove a user from the database and deactivate their licenses (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def remove_user(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user: disnake.Member
    ):
        """Removes a user from the database and deactivates their licenses on Payhip."""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can use this command.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            # Fetch all licenses associated with the user
            rows = await conn.fetch(
                """
                SELECT verified_licenses.product_name, verified_licenses.license_key, products.product_secret
                FROM verified_licenses
                JOIN products ON verified_licenses.product_name = products.product_name
                WHERE verified_licenses.user_id = $1 AND verified_licenses.guild_id = $2
                """,
                str(user.id), str(inter.guild.id)
            )

            if not rows:
                await inter.response.send_message(
                    f"⚠️ No licenses found for user `{user}` in this server.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

            # Deactivate licenses on Payhip
            deactivated_licenses = []
            failed_licenses = []

            for row in rows:
                product_name = row["product_name"]
                license_key = decrypt_data(row["license_key"])
                product_secret = decrypt_data(row["product_secret"])

                try:
                    PAYHIP_DISABLE_LICENSE_URL = "https://payhip.com/api/v2/license/disable"
                    headers = {"product-secret-key": product_secret, "payhip-api-key": self.payhip_api_key}
                    response = requests.put(
                        PAYHIP_DISABLE_LICENSE_URL,
                        headers=headers,
                        data={"license_key": license_key},
                        timeout=10
                    )

                    if response.status_code == 200:
                        deactivated_licenses.append(product_name)
                    else:
                        failed_licenses.append(product_name)

                except requests.exceptions.RequestException:
                    failed_licenses.append(product_name)

            # Remove user from the database
            await conn.execute(
                """
                DELETE FROM verified_licenses
                WHERE user_id = $1 AND guild_id = $2
                """,
                str(user.id), str(inter.guild.id)
            )

        # Notify the user of the results
        message = ""
        if deactivated_licenses:
            message += f"✅ User `{user}` has been removed and the following licenses were deactivated: {', '.join(deactivated_licenses)}.\n"
        if failed_licenses:
            message += f"\n⚠️ Failed to deactivate the following licenses: {', '.join(failed_licenses)}. Please check manually."
        
        await inter.response.send_message(message, ephemeral=True)

# Registers the cog with the bot
def setup(bot: commands.InteractionBot):
    bot.add_cog(RemoveUser(bot))
