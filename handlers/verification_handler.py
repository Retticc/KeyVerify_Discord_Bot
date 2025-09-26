# Updated handlers/verification_handler.py with dual payment support

import disnake
from disnake.ext.commands import CooldownMapping, BucketType
from handlers.verify_license_modal import VerifyLicenseModal
from utils.database import get_database_pool
from utils.helper import safe_followup
import config
import time
import logging

logger = logging.getLogger(__name__)

def create_verification_embed():
    embed = disnake.Embed(
        title="Verify your purchase",
        description="Click the button below to begin verifying your purchase.",
        color=disnake.Color.blurple()
    )
    embed.set_footer(text="Powered by KeyVerify")
    return embed

def create_verification_view(guild_id):
    return VerificationButton(guild_id)

verify_cooldown = CooldownMapping.from_cooldown(1, 20, BucketType.user)

class VerificationButton(disnake.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        button = disnake.ui.Button(label="Verify", style=disnake.ButtonStyle.primary, custom_id="verify_button")
        button.callback = self.on_button_click
        self.add_item(button)
        
    async def on_button_click(self, interaction: disnake.MessageInteraction):
        current = time.time()
        bucket = verify_cooldown.get_bucket(interaction)
        retry_after = bucket.update_rate_limit(current)

        if retry_after:
            await interaction.response.send_message(
                f"⏳ You're clicking too fast, try again in `{int(retry_after)}s`.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Get products with dual payment info
        products = await fetch_products_with_payment_methods(str(self.guild_id))
        if not products:
            await safe_followup(interaction, "❌ No products available for verification.", ephemeral=True)
            return

        # Check for existing verifications and reassign roles
        reassigned_roles = []
        unowned_products = {}

        for product_name, product_data in products.items():
            has_verification = await check_existing_verification(interaction.author.id, str(self.guild_id), product_name)
            
            if has_verification:
                # Reassign role if needed
                async with (await get_database_pool()).acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT role_id FROM products WHERE guild_id = $1 AND product_name = $2",
                        str(self.guild_id), product_name
                    )
                    if row:
                        role = disnake.utils.get(interaction.guild.roles, id=int(row["role_id"]))
                        if role and role not in interaction.author.roles:
                            try:
                                await interaction.author.add_roles(role)
                                reassigned_roles.append(role.name)
                            except:
                                pass
            else:
                unowned_products[product_name] = product_data

        if reassigned_roles:
            await safe_followup(interaction, f"The following roles have been reassigned: {', '.join(reassigned_roles)}", ephemeral=True)

        if unowned_products:
            # Create product selection dropdown with payment method info
            options = []
            for name, data in unowned_products.items():
                payment_methods = data.get("payment_methods", {})
                
                # Create description showing available payment methods
                payment_options = []
                if "usd" in payment_methods:
                    payment_options.append(f"💳 {payment_methods['usd']}")
                if "robux" in payment_methods:
                    payment_options.append(f"🎮 {payment_methods['robux']}")
                
                description = " or ".join(payment_options) if payment_options else "Product"
                
                # Choose emoji based on available payment methods
                if "usd" in payment_methods and "robux" in payment_methods:
                    emoji = "💎"  # Both methods available
                elif "robux" in payment_methods:
                    emoji = "🎮"  # Robux only
                else:
                    emoji = "💳"  # USD only
                
                options.append(disnake.SelectOption(
                    label=name, 
                    description=description[:100],
                    emoji=emoji
                ))
                
            dropdown = disnake.ui.StringSelect(placeholder="Choose a product to verify", options=options)
            dropdown.callback = lambda inter: handle_product_selection(inter, unowned_products)

            dropdown_view = disnake.ui.View()
            dropdown_view.add_item(dropdown)

            await safe_followup(interaction, "🎁 **Select a product to verify:**", view=dropdown_view, ephemeral=True)

        elif not reassigned_roles:
            await safe_followup(interaction, "✅ All available products have already been verified!", ephemeral=True)

async def handle_product_selection(interaction, products):
    """Handle product selection and show payment method options"""
    product_name = interaction.data["values"][0]
    product_data = products[product_name]
    payment_methods = product_data.get("payment_methods", {})
    
    # If only one payment method, skip selection
    if len(payment_methods) == 1:
        method_type = list(payment_methods.keys())[0]
        await start_verification_flow(interaction, product_name, product_data, method_type)
        return
    
    # Show payment method selection
    embed = disnake.Embed(
        title=f"💳 Choose Payment Method: {product_name}",
        description="How did you purchase this product?",
        color=disnake.Color.blue()
    )
    
    if product_data.get("description"):
        embed.add_field(name="📄 Product", value=product_data["description"], inline=False)
    
    view = PaymentMethodSelectionView(product_name, product_data, payment_methods)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class PaymentMethodSelectionView(disnake.ui.View):
    def __init__(self, product_name, product_data, payment_methods):
        super().__init__(timeout=180)
        self.product_name = product_name
        self.product_data = product_data
        self.payment_methods = payment_methods
        
        # Add buttons for each payment method
        if "usd" in payment_methods:
            usd_button = disnake.ui.Button(
                label=f"💳 Paid {payment_methods['usd']}",
                style=disnake.ButtonStyle.primary,
                emoji="💳"
            )
            usd_button.callback = self.select_usd_payment
            self.add_item(usd_button)
        
        if "robux" in payment_methods:
            robux_button = disnake.ui.Button(
                label=f"🎮 Paid {payment_methods['robux']}",
                style=disnake.ButtonStyle.primary,
                emoji="🎮"
            )
            robux_button.callback = self.select_robux_payment
            self.add_item(robux_button)

    async def select_usd_payment(self, interaction):
        await start_verification_flow(interaction, self.product_name, self.product_data, "usd")

    async def select_robux_payment(self, interaction):
        await start_verification_flow(interaction, self.product_name, self.product_data, "robux")

async def start_verification_flow(interaction, product_name, product_data, payment_method):
    """Start the appropriate verification flow based on payment method"""
    
    if product_name == "Test":
        # Test product flow
        modal = VerifyLicenseModal(product_name, "test_secret", "payhip")
        await interaction.response.send_modal(modal)
        return
    
    if payment_method == "usd":
        # PayHip license key verification
        payhip_secret = product_data.get("payhip_secret")
        if not payhip_secret:
            await interaction.response.send_message(
                "❌ PayHip verification not configured for this product.",
                ephemeral=True
            )
            return
            
        modal = VerifyLicenseModal(product_name, payhip_secret, "payhip")
        await interaction.response.send_modal(modal)
        
    elif payment_method == "robux":
        # Roblox username verification
        gamepass_id = product_data.get("gamepass_id")
        roblox_cookie = product_data.get("roblox_cookie")
        
        if not gamepass_id or not roblox_cookie:
            await interaction.response.send_message(
                "❌ Roblox verification not configured for this product.",
                ephemeral=True
            )
            return
            
        modal = VerifyLicenseModal(
            product_name, 
            roblox_cookie, 
            "roblox", 
            gamepass_id=gamepass_id
        )
        await interaction.response.send_modal(modal)

async def check_existing_verification(user_id, guild_id, product_name):
    """Check if user already has verification for this product (either method)"""
    async with (await get_database_pool()).acquire() as conn:
        # Check license keys
        license_row = await conn.fetchrow(
            "SELECT 1 FROM verified_licenses WHERE user_id = $1 AND guild_id = $2 AND product_name = $3",
            str(user_id), guild_id, product_name
        )
        if license_row:
            return True
        
        # Check Roblox verifications
        roblox_row = await conn.fetchrow(
            "SELECT 1 FROM roblox_verified_users WHERE discord_user_id = $1 AND guild_id = $2 AND product_name = $3",
            str(user_id), guild_id, product_name
        )
        return bool(roblox_row)

# Updated fetch function (add this to database.py)
async def fetch_products_with_payment_methods(guild_id):
    """Retrieves all products with their payment method information"""
    async with (await get_database_pool()).acquire() as conn:
        rows = await conn.fetch(
            """SELECT product_name, payment_methods, payhip_secret, gamepass_id, 
               roblox_cookie, stock, description FROM products WHERE guild_id = $1""", 
            guild_id
        )
        
        from utils.encryption import decrypt_data
        products = {}
        for row in rows:
            payment_methods = parse_payment_methods(row["payment_methods"]) if row["payment_methods"] else {}
            
            products[row["product_name"]] = {
                "payment_methods": payment_methods,
                "payhip_secret": decrypt_data(row["payhip_secret"]) if row["payhip_secret"] else None,
                "gamepass_id": row["gamepass_id"],
                "roblox_cookie": decrypt_data(row["roblox_cookie"]) if row["roblox_cookie"] else None,
                "stock": row["stock"] if row["stock"] is not None else -1,
                "description": row["description"]
            }
        
        # Always add Test product
        products["Test"] = {
            "payment_methods": {"usd": "Free"},
            "payhip_secret": "test_secret",
            "gamepass_id": None,
            "roblox_cookie": None,
            "stock": -1,
            "description": "Test product for verification system testing"
        }
        
        return products

def parse_payment_methods(payment_methods_str):
    """Parse payment methods string into dictionary"""
    if not payment_methods_str:
        return {}
    
    methods = {}
    for method in payment_methods_str.split("|"):
        if ":" in method:
            method_type, price = method.split(":", 1)
            methods[method_type] = price
    
    return methods
