import disnake
from disnake.ext import commands
from utils.encryption import encrypt_data
from utils.database import get_database_pool
import config

class AddProduct(commands.Cog):
    @commands.slash_command(
        description="Add a product to the server's list with an assigned role (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def add_product(
        self,
        inter: disnake.ApplicationCommandInteraction,
        product_secret: str,
        product_name: str,
        role: disnake.Role = None,
    ):
        # Defer response to avoid webhook expiration
        await inter.response.defer(ephemeral=True)

        if inter.author.id != inter.guild.owner_id:
            await inter.followup.send(
                "❌ Only the server owner can use this command.",
                delete_after=config.message_timeout
            )
            return

        encrypted_secret = encrypt_data(product_secret)

        if not role:
            role_name = f"Verified-{product_name}"
            role = await inter.guild.create_role(name=role_name)
            role_id = str(role.id)
            await inter.followup.send(
                f"⚠️ Role '{role_name}' was created automatically.",
                delete_after=config.message_timeout
            )
        else:
            role_id = str(role.id)

        async with (await get_database_pool()).acquire() as conn:
            try:
                await conn.execute(
                    "INSERT INTO products (guild_id, product_name, product_secret, role_id) VALUES ($1, $2, $3, $4)",
                    str(inter.guild.id), product_name, encrypted_secret, role_id
                )
                await inter.followup.send(
                    f"✅ Product '{product_name}' added successfully with role '{role.name}'.",
                    delete_after=config.message_timeout
                )
            except Exception as e:
                await inter.followup.send(
                    f"❌ Product '{product_name}' already exists.",
                    delete_after=config.message_timeout
                )

def setup(bot):
    bot.add_cog(AddProduct(bot))
