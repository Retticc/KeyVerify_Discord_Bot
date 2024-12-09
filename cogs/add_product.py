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
        # Check if the command is executed by the server owner
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can use this command.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Encrypt the product secret
        encrypted_secret = encrypt_data(product_secret)

        # Create a new role if none is provided
        if not role:
            role_name = f"Verified-{product_name}"
            role = await inter.guild.create_role(name=role_name)
            role_id = str(role.id)
            await inter.response.send_message(
                f"⚠️ Role '{role_name}' was created automatically.",
                ephemeral=True,delete_after=config.message_timeout
            )
        else:
            role_id = str(role.id)

        # Add the product to the database
        async with (await get_database_pool()).acquire() as conn:
            try:
                await conn.execute(
                    "INSERT INTO products (guild_id, product_name, product_secret, role_id) VALUES ($1, $2, $3, $4)",
                    str(inter.guild.id), product_name, encrypted_secret, role_id
                )
                # Send success message
                await inter.followup.send(
                    f"✅ Product '{product_name}' added successfully with role '{role.name}'.",
                    ephemeral=True,delete_after=config.message_timeout
                )
            except Exception as e:
                # Handle duplicate entry
                await inter.followup.send(
                    f"❌ Product '{product_name}' already exists.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )

def setup(bot):
    bot.add_cog(AddProduct(bot))
