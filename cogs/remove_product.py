import disnake
from disnake.ext import commands
from utils.database import get_database_pool
import config

class RemoveProduct(commands.Cog):
    @commands.slash_command(
        description="Remove a product from the server's list (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def remove_product(
        self,
        inter: disnake.ApplicationCommandInteraction,
        product_name: str,
    ):
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message("❌ Only the server owner can use this command.", ephemeral=True,delete_after=config.message_timeout)
            return

        async with (await get_database_pool()).acquire() as conn:
            result = await conn.execute(
                "DELETE FROM products WHERE guild_id = $1 AND product_name = $2",
                str(inter.guild.id), product_name
            )

            if result == "DELETE 0":
                await inter.response.send_message(f"❌ Product '{product_name}' not found.", ephemeral=True,delete_after=config.message_timeout)
            else:
                await inter.response.send_message(f"✅ Product '{product_name}' removed successfully.", ephemeral=True,delete_after=config.message_timeout)

def setup(bot):
    bot.add_cog(RemoveProduct(bot))
