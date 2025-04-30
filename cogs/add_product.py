import disnake
from disnake.ext import commands
from utils.encryption import encrypt_data
from utils.database import get_database_pool
import config

import logging
logger = logging.getLogger(__name__)

# This cog allows the server owner to add a product to the server's database
# A product consists of a name, a Payhip secret key, and a role to assign upon verification
class AddProduct(commands.Cog):
    @commands.slash_command(
        description="Add a product to the server's list with an assigned role (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )  # Slash command to register a new product into the server's product list
    async def add_product(
        self,
        inter: disnake.ApplicationCommandInteraction,
        product_secret: str,
        product_name: str,
        role: disnake.Role = None,
    ):
        await inter.response.defer(ephemeral=True)

        if inter.author.id != inter.guild.owner_id:
            logger.warning(f"[Unauthorized Attempt] {inter.author} tried to add a product in '{inter.guild.name}'")
            await inter.followup.send(
                "❌ Only the server owner can use this command.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        encrypted_secret = encrypt_data(product_secret)

        if not role:
            role_name = f"Verified-{product_name}"
            role = await inter.guild.create_role(name=role_name)
            logger.info(f"[Role Auto-Created] Role '{role_name}' was auto-created in '{inter.guild.name}'")
            role_id = str(role.id)
            await inter.followup.send(
                f"⚠️ Role '{role_name}' was created automatically.",
                ephemeral=True,
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
                logger.info(f"[Product Added] '{product_name}' added to '{inter.guild.name}' with role '{role.name}'")
                await inter.followup.send(
                    f"✅ Product **`{product_name}`** added successfully with role {role.mention}.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
            except Exception:
                logger.warning(f"[Duplicate Product] Attempt to add duplicate product '{product_name}' in '{inter.guild.name}'")
                await inter.followup.send(
                    f"❌ Product '{product_name}' already exists.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
# Registers the cog with the bot
def setup(bot):
    bot.add_cog(AddProduct(bot))
