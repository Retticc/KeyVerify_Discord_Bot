# Complete updated cogs/add_product.py with Roblox gamepass support

import disnake
from disnake.ext import commands
from utils.encryption import encrypt_data
from utils.database import get_database_pool
from utils.permissions import owner_or_permission
import config
import logging
import uuid

logger = logging.getLogger(__name__)
product_session_cache = {}  # session_id -> product_data

class AddProduct(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        description="Add a product to the server's list with an assigned role.",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @owner_or_permission("manage_products")
    async def add_product(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.send_modal(AddProductModal())

class AddProductModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Product Name",
                custom_id="product_name",
                placeholder="Enter the product name",
                style=disnake.TextInputStyle.short,
                max_length=100,
            ),
            disnake.ui.TextInput(
                label="Product Type",
                custom_id="product_type",
                placeholder="Enter 'payhip' or 'roblox'",
                style=disnake.TextInputStyle.short,
                max_length=10,
            ),
            disnake.ui.TextInput(
                label="Price (Optional)",
                custom_id="product_price",
                placeholder="e.g., $9.99 or 350 Robux",
                style=disnake.TextInputStyle.short,
                max_length=50,
                required=False
            ),
            disnake.ui.TextInput(
                label="Description (Optional)",
                custom_id="product_description",
                placeholder="Brief description of the product",
                style=disnake.TextInputStyle.paragraph,
                max_length=200,
                required=False
            )
        ]
        super().__init__(
            title="Add a New Product - Step 1",
            custom_id="add_product_modal",
            components=components
        )

    async def callback(self, interaction: disnake.ModalInteraction):
        product_name = interaction.text_values["product_name"].strip()
        product_type = interaction.text_values["product_type"].strip().lower()
        product_price = interaction.text_values.get("product_price", "").strip()
        product_description = interaction.text_values.get("product_description", "").strip()

        if product_type not in ["payhip", "roblox"]:
            await interaction.response.send_message(
                "❌ Product type must be either 'payhip' or 'roblox'",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Create a session ID to store data between modals
        session_id = str(uuid.uuid4())[:12]
        
        if product_type == "payhip":
            await interaction.response.send_modal(PayhipProductModal(session_id, product_name, product_price, product_description))
        else:  # roblox
            await interaction.response.send_modal(RobloxProductModal(session_id, product_name, product_price, product_description))

class PayhipProductModal(disnake.ui.Modal):
    def __init__(self, session_id, product_name, product_price, product_description):
        self.session_id = session_id
        self.product_name = product_name
        self.product_price = product_price
        self.product_description = product_description
        
        components = [
            disnake.ui.TextInput(
                label="Payhip Product Secret",
                custom_id="product_secret",
                placeholder="Enter the Payhip product secret key",
                style=disnake.TextInputStyle.short,
                max_length=100,
            )
        ]
        super().__init__(
            title=f"Payhip Product: {product_name}",
            custom_id="payhip_product_modal",
            components=components
        )

    async def callback(self, interaction: disnake.ModalInteraction):
        product_secret = interaction.text_values["product_secret"].strip()
        
        # Store all data in session cache
        product_session_cache[self.session_id] = {
            "name": self.product_name,
            "type": "payhip",
            "secret": product_secret,
            "price": self.product_price,
            "description": self.product_description,
            "gamepass_id": None,
            "roblox_cookie": None
        }
        
        await self.show_role_selection(interaction)

class RobloxProductModal(disnake.ui.Modal):
    def __init__(self, session_id, product_name, product_price, product_description):
        self.session_id = session_id
        self.product_name = product_name
        self.product_price = product_price
        self.product_description = product_description
        
        components = [
            disnake.ui.TextInput(
                label="Roblox Gamepass ID",
                custom_id="gamepass_id",
                placeholder="Enter the gamepass ID (numbers only)",
                style=disnake.TextInputStyle.short,
                max_length=20,
            ),
            disnake.ui.TextInput(
                label="Roblox Cookie (.ROBLOSECURITY)",
                custom_id="roblox_cookie",
                placeholder="Paste your .ROBLOSECURITY cookie here",
                style=disnake.TextInputStyle.paragraph,
                max_length=2000,
            )
        ]
        super().__init__(
            title=f"Roblox Product: {product_name}",
            custom_id="roblox_product_modal",
            components=components
        )

    async def callback(self, interaction: disnake.ModalInteraction):
        gamepass_id = interaction.text_values["gamepass_id"].strip()
        roblox_cookie = interaction.text_values["roblox_cookie"].strip()
        
        # Validate gamepass ID is numeric
        if not gamepass_id.isdigit():
            await interaction.response.send_message(
                "❌ Gamepass ID must be numbers only",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return
        
        # Store all data in session cache
        product_session_cache[self.session_id] = {
            "name": self.product_name,
            "type": "roblox",
            "secret": roblox_cookie,  # Store cookie as "secret"
            "price": self.product_price,
            "description": self.product_description,
            "gamepass_id": gamepass_id,
            "roblox_cookie": roblox_cookie
        }
        
        await self.show_role_selection(interaction)

    async def show_role_selection(self, interaction):
        MAX_SELECT_OPTIONS = 24
        role_options = [
            disnake.SelectOption(label="Create New Role Automatically", value="auto")
        ] + [
            disnake.SelectOption(label=role.name, value=str(role.id))
            for role in interaction.guild.roles 
            if role < interaction.guild.me.top_role and not role.managed
        ][:MAX_SELECT_OPTIONS]

        select = disnake.ui.StringSelect(
            placeholder="Choose a role or create one",
            options=role_options,
            custom_id=f"role_select:{self.session_id}"
        )
        select.callback = self.finish_product

        view = disnake.ui.View(timeout=180)
        view.add_item(select)

        await interaction.response.send_message(
            "Select a role for this product:",
            view=view,
            ephemeral=True,
            delete_after=config.message_timeout
        )

    async def finish_product(self, interaction: disnake.MessageInteraction):
        try:
            _, session_id = interaction.data['custom_id'].split(":")
            product_data = product_session_cache.pop(session_id)
        except Exception as e:
            logger.error(f"[Role Selection Error] Invalid session ID: {e}")
            await interaction.response.send_message("❌ Something went wrong. Please try again.", ephemeral=True)
            return

        selected_value = interaction.data['values'][0]
        if selected_value == "auto":
            role_name = f"Verified-{product_data['name']}"
            role = await interaction.guild.create_role(name=role_name)
            await interaction.response.send_message(f"Role '{role.name}' was created automatically.", ephemeral=True,
                                                    delete_after=config.message_timeout)
        else:
            role = interaction.guild.get_role(int(selected_value))
            await interaction.response.send_message(f"Selected role: {role.mention}", ephemeral=True,
                                                    delete_after=config.message_timeout)

        # Encrypt the secret (cookie for Roblox, secret for Payhip)
        encrypted_secret = encrypt_data(product_data['secret'])

        async with (await get_database_pool()).acquire() as conn:
            try:
                await conn.execute(
                    """INSERT INTO products (guild_id, product_name, product_secret, role_id, product_type, 
                       gamepass_id, price, description) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                    str(interaction.guild.id), 
                    product_data['name'], 
                    encrypted_secret, 
                    str(role.id),
                    product_data['type'],
                    product_data['gamepass_id'],
                    product_data['price'],
                    product_data['description']
                )
                
                logger.info(f"[Product Added] '{product_data['name']}' ({product_data['type']}) added to '{interaction.guild.name}' with role '{role.name}' by {interaction.author}")
                
                success_msg = f"✅ **{product_data['type'].title()}** product **`{product_data['name']}`** added successfully with role {role.mention}!"
                
                if product_data['price']:
                    success_msg += f"\n💰 **Price:** {product_data['price']}"
                if product_data['description']:
                    success_msg += f"\n📄 **Description:** {product_data['description']}"
                if product_data['type'] == 'roblox':
                    success_msg += f"\n🎮 **Gamepass ID:** {product_data['gamepass_id']}"
                
                success_msg += (
                    f"\n\n💡 **Next Steps:**\n"
                    f"• Use `/set_product_auto_roles` to configure additional auto-roles\n"
                    f"• Use `/set_stock` to manage inventory\n"
                    f"• Use `/start_verification` to deploy verification system"
                )
                
                await interaction.followup.send(
                    success_msg,
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
            except Exception:
                logger.warning(f"[Duplicate Product] Attempt to add duplicate product '{product_data['name']}' in '{interaction.guild.name}' by {interaction.author}")
                await interaction.followup.send(
                    f"❌ Product '{product_data['name']}' already exists.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )

# Add the show_role_selection method to PayhipProductModal as well
PayhipProductModal.show_role_selection = RobloxProductModal.show_role_selection
PayhipProductModal.finish_product = RobloxProductModal.finish_product

def setup(bot):
    bot.add_cog(AddProduct(bot))
