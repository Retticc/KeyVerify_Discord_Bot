import disnake
from disnake.ext import commands
from utils.database import get_database_pool, fetch_products
import config
import logging

logger = logging.getLogger(__name__)

# This cog allows the server owner to remove a registered product from the server
class RemoveProduct(commands.Cog):
    @commands.slash_command(
        description="Remove a product from the server's list (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def remove_product(self, inter: disnake.ApplicationCommandInteraction):
        if inter.author.id != inter.guild.owner_id:                 # Ensure only the server owner can access this command
            logger.warning(f"[Blocked] {inter.author} tried to access /remove_product in '{inter.guild.name}'")
            await inter.response.send_message("❌ Only the server owner can use this command.", ephemeral=True, delete_after=config.message_timeout)
            return
        
        # Fetch all products registered in the current guild
        products = await fetch_products(str(inter.guild.id))
        if not products:
            logger.info(f"[No Products] {inter.author} opened /remove_product but no products exist in '{inter.guild.name}'")
            await inter.response.send_message("❌ No products to remove.", ephemeral=True, delete_after=config.message_timeout)
            return
        
        # Build a dropdown menu with all product names
        options = [
            disnake.SelectOption(label=product, description=f"Remove '{product}'")
            for product in products.keys()
        ]

        dropdown = disnake.ui.StringSelect(
            placeholder="Select a product to remove",
            options=options
        )
        
        # Called when a product is selected from the dropdown
        async def product_selected(select_inter: disnake.MessageInteraction):
            selected = select_inter.data["values"][0]

            # Confirmation UI: Confirm / Cancel buttons
            class ConfirmView(disnake.ui.View):
                def __init__(self):
                    super().__init__(timeout=30)

                @disnake.ui.button(label="✅ Confirm", style=disnake.ButtonStyle.danger)
                async def confirm(self, button: disnake.ui.Button, button_inter: disnake.MessageInteraction):
                    async with (await get_database_pool()).acquire() as conn:
                        result = await conn.execute(
                            "DELETE FROM products WHERE guild_id = $1 AND product_name = $2",
                            str(inter.guild.id), selected
                        )
                        
                    # No matching product found in DB    
                    if result == "DELETE 0":
                        logger.warning(f"[Failed Delete] Product '{selected}' not found during deletion in '{inter.guild.name}' by {button_inter.author}")
                        await button_inter.response.send_message(
                            f"❌ Product '{selected}' not found.",
                            ephemeral=True,
                            delete_after=config.message_timeout
                        )
                    else:
                        # Deletion succeeded
                        logger.info(f"[Delete] Product '{selected}' removed from '{inter.guild.name}' by {button_inter.author}")
                        await button_inter.response.send_message(
                            f"✅ Product '{selected}' has been removed.",
                            ephemeral=True,
                            delete_after=config.message_timeout
                        )
                    self.stop()

                @disnake.ui.button(label="❌ Cancel", style=disnake.ButtonStyle.secondary)
                async def cancel(self, button: disnake.ui.Button, button_inter: disnake.MessageInteraction):
                    await button_inter.response.send_message(
                        "Deletion cancelled 💨",
                        ephemeral=True,
                        delete_after=config.message_timeout
                    )
                    logger.info(f"[Cancel] Product deletion cancelled by {button_inter.author} in '{inter.guild.name}'")
                    self.stop()
                    
            # Present the confirmation view to the user
            view = ConfirmView()
            await select_inter.response.send_message(
                f"⚠️ Are you sure you want to delete **`{selected}`**?",
                view=view,
                ephemeral=True,
                delete_after=config.message_timeout
            )
            
        # Attach the product selection handler
        dropdown.callback = product_selected
        view = disnake.ui.View()
        view.add_item(dropdown)

        logger.info(f"[Dropdown Init] {inter.author} opened product removal dropdown in '{inter.guild.name}'")
        
        # Send the dropdown to the user
        await inter.response.send_message(
            "🗑️ Select a product to remove:",
            view=view,
            ephemeral=True,
            delete_after=config.message_timeout
        )
        
# Registers the cog with the bot
def setup(bot):
    bot.add_cog(RemoveProduct(bot))
