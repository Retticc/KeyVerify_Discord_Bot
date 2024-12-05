import disnake
from disnake.ext import commands
import requests
from utils.encryption import decrypt_data
from utils.database import get_database_pool

message_timeout = 120
class ResetKey(commands.Cog):
    
    @commands.slash_command(
        description="Reset a product license key's usage count (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def reset_key(
        self,
        inter: disnake.ApplicationCommandInteraction,
        product_name: str,
        license_key: str,
    ):
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message("❌ Only the server owner can use this command.", ephemeral=True,delete_after=message_timeout)
            return

        async with (await get_database_pool()).acquire() as conn:
            row = await conn.fetchrow(
                "SELECT product_secret FROM products WHERE guild_id = $1 AND product_name = $2",
                str(inter.guild.id), product_name
            )

            if not row:
                await inter.response.send_message(f"❌ Product '{product_name}' not found.", ephemeral=True,delete_after=message_timeout)
                return

            product_secret_key = decrypt_data(row["product_secret"])

        PAYHIP_RESET_USAGE_URL = "https://payhip.com/api/v2/license/decrease"
        headers = {"product-secret-key": product_secret_key}

        try:
            response = requests.put(
                PAYHIP_RESET_USAGE_URL,
                headers=headers,
                data={"license_key": license_key.strip()},
                timeout=10
            )
            response.raise_for_status()

            if response.status_code == 200:
                await inter.response.send_message(
                    f"✅ License key for '{product_name}' has been reset successfully.",
                    ephemeral=True
                )
            else:
                await inter.response.send_message("❌ Failed to reset the license key.", ephemeral=True,delete_after=message_timeout)
        except requests.exceptions.RequestException as e:
            await inter.response.send_message("❌ Unable to contact the reset server.", ephemeral=True,delete_after=message_timeout)

def setup(bot):
    bot.add_cog(ResetKey(bot))
