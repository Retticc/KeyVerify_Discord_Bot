# Updated handlers/verification_handler.py with NO Roblox API verification

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

        # Get products with PayHip info only (no Roblox verification)
        products = await fetch_products_payhip_only(str(self.guild_id))
        if not products:
            await safe_followup(interaction, "❌ No products available for verification.", ephemeral=True)
            return

        # Check for existing verifications and reassign roles
        reassigned_roles = []
        unowned_products = {}

        for product_name, product_secret in products.items():
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
                unowned_products[product_name] = product_secret

        if reassigned_roles:
            await safe_followup(interaction, f"The following roles have been reassigned: {', '.join(reassigned_roles)}", ephemeral=True)

        if unowned_products:
            # Create simple product selection dropdown
            options = []
            for name in unowned_products.keys():
                options.append(disnake.SelectOption(
                    label=name, 
                    description=f"Verify your {name} license key",
                    emoji="🎁"
                ))
                
            dropdown = disnake.ui.StringSelect(placeholder="Choose a product to verify", options=options)
            dropdown.callback = lambda inter: handle_product_selection(inter, unowned_products)

            dropdown_view = disnake.ui.View()
            dropdown_view.add_item(dropdown)

            await safe_followup(interaction, "🎁 **Select a product to verify:**", view=dropdown_view, ephemeral=True)

        elif not reassigned_roles:
            await safe_followup(interaction, "✅ All available products have already been verified!", ephemeral=True)

async def handle_product_selection(interaction, products):
    """Handle product selection and show PayHip license modal"""
    product_name = interaction.data["values"][0]
    product_secret = products[product_name]
    
    # Always use PayHip verification for verification system
    modal = VerifyLicenseModal(product_name, product_secret, "payhip")
    await interaction.response.send_modal(modal)

async def check_existing_verification(user_id, guild_id, product_name):
    """Check if user already has verification for this product"""
    async with (await get_database_pool()).acquire() as conn:
        # Only check license keys table for verification
        license_row = await conn.fetchrow(
            "SELECT 1 FROM verified_licenses WHERE user_id = $1 AND guild_id = $2 AND product_name = $3",
            str(user_id), guild_id, product_name
        )
        return bool(license_row)

async def fetch_products_payhip_only(guild_id):
    """Retrieves products that have PayHip secrets only"""
    async with (await get_database_pool()).acquire() as conn:
        rows = await conn.fetch(
            "SELECT product_name, payhip_secret FROM products WHERE guild_id = $1 AND payhip_secret IS NOT NULL", 
            guild_id
        )
        
        from utils.encryption import decrypt_data
        products = {}
        for row in rows:
            products[row["product_name"]] = decrypt_data(row["payhip_secret"])
        
        # Always add Test product
        products["Test"] = "test_secret"
        
        return products
