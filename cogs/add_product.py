# Updated cogs/add_product.py with simplified dual payment (no Roblox API)

import disnake
from disnake.ext import commands
from utils.encryption import encrypt_data
from utils.database import get_database_pool
from utils.permissions import owner_or_permission
import config
import logging
import uuid

logger = logging.getLogger(__name__)
product_session_cache = {}

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
                label="USD Price (Optional)",
                custom_id="usd_price",
                placeholder="e.g., $9.99 (for PayHip payments)",
                style=disnake.TextInputStyle.short,
                max_length=20,
                required=False
            ),
            disnake.ui.TextInput(
                label="Robux Price (Optional)",
                custom_id="robux_price",
                placeholder="e.g., 350 Robux (for gamepass payments)",
                style=disnake.TextInputStyle.short,
                max_length=20,
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
            title="Add a New Product",
            custom_id="add_product_modal",
            components=components
        )

    async def callback(self, interaction: disnake.ModalInteraction):
        product_name = interaction.text_values["product_name"].strip()
        usd_price = interaction.text_values.get("usd_price", "").strip()
        robux_price = interaction.text_values.get("robux_price", "").strip()
        product_description = interaction.text_values.get("product_description", "").strip()

        if not usd_price and not robux_price:
            await interaction.response.send_message(
                "❌ You must provide at least one payment method (USD Price or Robux Price).",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        session_id = str(uuid.uuid4())[:12]
        product_session_cache[session_id] = {
            "name": product_name,
            "usd_price": usd_price,
            "robux_price": robux_price,
            "description": product_description,
            "payhip_secret": None,
            "gamepass_id": None
        }

        # Show payment method configuration
        embed = disnake.Embed(
            title=f"🎁 Configure Payment Methods: {product_name}",
            description="Configure the payment methods you want to offer:",
            color=disnake.Color.blue()
        )

        if usd_price:
            embed.add_field(
                name="💳 USD Payment",
                value=f"**{usd_price}** - Needs PayHip configuration",
                inline=False
            )
        
        if robux_price:
            embed.add_field(
                name="🎮 Robux Payment", 
                value=f"**{robux_price}** - Needs Gamepass ID",
                inline=False
            )

        view = PaymentMethodView(session_id, bool(usd_price), bool(robux_price))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class PaymentMethodView(disnake.ui.View):
    def __init__(self, session_id, has_usd, has_robux):
        super().__init__(timeout=300)
        self.session_id = session_id
        self.has_usd = has_usd
        self.has_robux = has_robux

        if has_usd:
            usd_button = disnake.ui.Button(
                label="💳 Configure PayHip",
                style=disnake.ButtonStyle.primary,
                emoji="💳"
            )
            usd_button.callback = self.configure_payhip
            self.add_item(usd_button)

        if has_robux:
            robux_button = disnake.ui.Button(
                label="🎮 Configure Roblox",
                style=disnake.ButtonStyle.primary, 
                emoji="🎮"
            )
            robux_button.callback = self.configure_roblox
            self.add_item(robux_button)

        finish_button = disnake.ui.Button(
            label="✅ Finish Setup",
            style=disnake.ButtonStyle.green,
            emoji="✅"
        )
        finish_button.callback = self.finish_setup
        self.add_item(finish_button)

    async def configure_payhip(self, interaction):
        await interaction.response.send_modal(PayHipConfigModal(self.session_id))

    async def configure_roblox(self, interaction):
        await interaction.response.send_modal(RobloxConfigModal(self.session_id))

    async def finish_setup(self, interaction):
        product_data = product_session_cache.get(self.session_id)
        if not product_data:
            await interaction.response.send_message("❌ Session expired. Please try again.", ephemeral=True)
            return

        # Check if required configurations are complete
        missing = []
        if self.has_usd and not product_data.get("payhip_secret"):
            missing.append("💳 PayHip secret")
        if self.has_robux and not product_data.get("gamepass_id"):
            missing.append("🎮 Roblox gamepass ID")

        if missing:
            await interaction.response.send_message(
                f"❌ Please configure the missing payment methods:\n• {', '.join(missing)}",
                ephemeral=True
            )
            return

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
        else:
            role = interaction.guild.get_role(int(selected_value))

        # Create payment methods string for database
        payment_methods = []
        if product_data.get("usd_price"):
            payment_methods.append(f"usd:{product_data['usd_price']}")
        if product_data.get("robux_price"):
            payment_methods.append(f"robux:{product_data['robux_price']}")
        
        payment_methods_str = "|".join(payment_methods)

        async with (await get_database_pool()).acquire() as conn:
            try:
                # Store PayHip secret if available (no Roblox cookie needed)
                payhip_secret = encrypt_data(product_data.get("payhip_secret", "")) if product_data.get("payhip_secret") else None

                await conn.execute(
                    """INSERT INTO products (guild_id, product_name, role_id, description, payment_methods, 
                       payhip_secret, gamepass_id) VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                    str(interaction.guild.id), 
                    product_data['name'],
                    str(role.id),
                    product_data['description'],
                    payment_methods_str,
                    payhip_secret,
                    product_data.get('gamepass_id')
                )
                
                # Success message
                success_embed = disnake.Embed(
                    title="✅ Product Added Successfully!",
                    description=f"**{product_data['name']}** is now available with multiple payment options:",
                    color=disnake.Color.green()
                )
                
                success_embed.add_field(
                    name="🏷️ Role",
                    value=role.mention,
                    inline=True
                )
                
                if product_data.get("usd_price"):
                    success_embed.add_field(
                        name="💳 USD Payment",
                        value=f"**{product_data['usd_price']}** via PayHip (license verification)",
                        inline=True
                    )
                
                if product_data.get("robux_price"):
                    success_embed.add_field(
                        name="🎮 Robux Payment",
                        value=f"**{product_data['robux_price']}** via Gamepass (username verification)",
                        inline=True
                    )
                
                if product_data.get("description"):
                    success_embed.add_field(
                        name="📄 Description",
                        value=product_data["description"],
                        inline=False
                    )

                success_embed.add_field(
                    name="💡 Next Steps",
                    value="• Use `/start_verification` to deploy verification system\n• Use `/create_ticket_box` for support tickets\n• Users can choose their preferred payment method!",
                    inline=False
                )
                
                success_embed.add_field(
                    name="ℹ️ How It Works",
                    value="**PayHip:** Users enter license key for automatic verification\n**Roblox:** Users provide username for manual verification by staff",
                    inline=False
                )
                
                await interaction.response.send_message(embed=success_embed, ephemeral=True)
                
                logger.info(f"[Dual Payment Product] '{product_data['name']}' added with USD: {bool(product_data.get('usd_price'))}, Robux: {bool(product_data.get('robux_price'))} by {interaction.author}")
                
            except Exception as e:
                logger.error(f"[Product Creation Error] {e}")
                await interaction.response.send_message(
                    f"❌ Failed to create product. It may already exist.",
                    ephemeral=True
                )

class PayHipConfigModal(disnake.ui.Modal):
    def __init__(self, session_id):
        self.session_id = session_id
        components = [
            disnake.ui.TextInput(
                label="PayHip Product Secret",
                custom_id="payhip_secret",
                placeholder="Enter your PayHip product secret key",
                style=disnake.TextInputStyle.short,
                max_length=100,
            )
        ]
        super().__init__(title="💳 PayHip Configuration", components=components)

    async def callback(self, interaction):
        payhip_secret = interaction.text_values["payhip_secret"].strip()
        
        if self.session_id in product_session_cache:
            product_session_cache[self.session_id]["payhip_secret"] = payhip_secret
            
        await interaction.response.send_message(
            "✅ PayHip configuration saved! You can now finish the setup or configure Roblox if needed.",
            ephemeral=True,
            delete_after=config.message_timeout
        )

class RobloxConfigModal(disnake.ui.Modal):
    def __init__(self, session_id):
        self.session_id = session_id
        components = [
            disnake.ui.TextInput(
                label="Gamepass ID",
                custom_id="gamepass_id",
                placeholder="Enter the Roblox gamepass ID (numbers only)",
                style=disnake.TextInputStyle.short,
                max_length=20,
            )
        ]
        super().__init__(title="🎮 Roblox Configuration", components=components)

    async def callback(self, interaction):
        gamepass_id = interaction.text_values["gamepass_id"].strip()
        
        if not gamepass_id.isdigit():
            await interaction.response.send_message(
                "❌ Gamepass ID must be numbers only",
                ephemeral=True
            )
            return
            
        if self.session_id in product_session_cache:
            product_session_cache[self.session_id]["gamepass_id"] = gamepass_id
            
        await interaction.response.send_message(
            "✅ Roblox configuration saved!\n\n"
            "**Note:** Roblox gamepass verification is manual - users will provide their username in tickets for staff to verify.",
            ephemeral=True,
            delete_after=config.message_timeout
        )

def setup(bot):
    bot.add_cog(AddProduct(bot))
