import disnake
from disnake.ext.commands import CooldownMapping, BucketType

from handlers.verify_license_modal import VerifyLicenseModal
from utils.database import fetch_products, get_database_pool
from utils.encryption import decrypt_data
from utils.helper import safe_followup

import config
import time
import logging

logger = logging.getLogger(__name__)

# Creates a styled embed message prompting users to verify their purchase.
def create_verification_embed():
    embed = disnake.Embed(
        title="Verify your purchase",
        description="Click the button below to begin verifying your purchase.",
        color=disnake.Color.blurple()
    )
    embed.set_footer(text="Powered by KeyVerify")
    return embed

# Returns an instance of the verification button view for the given guild.
def create_verification_view(guild_id):
    return VerificationButton(guild_id)

# Retrieves the verified license key for a user, guild, and product from the database.
# If no key exists, returns None.
async def get_verified_license(user_id, guild_id, product_name):
    """Retrieve the verified license for a user, guild, and product."""
    async with (await get_database_pool()).acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT license_key FROM verified_licenses
            WHERE user_id = $1 AND guild_id = $2 AND product_name = $3
            """,
            str(user_id), str(guild_id), product_name
        )
        return decrypt_data(row["license_key"]) if row else None
    
# Cooldown rate limiter: allows 1 verification request every 20 seconds per user
verify_cooldown = CooldownMapping.from_cooldown(1, 20, BucketType.user)

# Represents a view containing a verification button.
# When clicked, it checks cooldowns, checks owned products, assigns roles, and handles verification flows.
class VerificationButton(disnake.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        button = disnake.ui.Button(label="Verify", style=disnake.ButtonStyle.primary, custom_id="verify_button")
        button.callback = self.on_button_click
        self.add_item(button)
        
    # Handles button interaction when user clicks "Verify".
    # Checks cooldown, fetches owned products, assigns missing roles, and opens dropdown if necessary.
    async def on_button_click(self, interaction: disnake.MessageInteraction):
        # Cooldown check
        current = time.time()
        bucket = verify_cooldown.get_bucket(interaction)
        retry_after = bucket.update_rate_limit(current)

        if retry_after:
            logger.warning(f"[Cooldown] {interaction.author} in guild '{interaction.guild.name}' tried to verify too quickly.")
            await interaction.response.send_message(
                f"⏳ You're clicking too fast, try again in `{int(retry_after)}s`.",
                ephemeral=True,delete_after=config.message_timeout
            )
            return

        await interaction.response.defer(ephemeral=True)

        user_id = interaction.author.id
        guild_id = self.guild_id

        products = await fetch_products(guild_id)
        if not products:
            logger.info(f"[No Products] {interaction.author} attempted to verify in '{interaction.guild.name}' but no products exist.")
            await safe_followup(interaction, "❌ No products available for verification.", ephemeral=True, delete_after=config.message_timeout)
            return

        reassigned_roles = []
        unowned_products = {}

        for product_name, product_secret in products.items():
            verified_key = await get_verified_license(user_id, guild_id, product_name)
            if verified_key:
                async with (await get_database_pool()).acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT role_id FROM products WHERE guild_id = $1 AND product_name = $2",
                        str(guild_id), product_name
                    )
                    if row:
                        role = disnake.utils.get(interaction.guild.roles, id=int(row["role_id"]))
                        if role and role not in interaction.author.roles:
                            bot_member = interaction.guild.me
                            if bot_member.top_role <= role:
                                logger.warning(f"[Role Skipped] Bot couldn't assign '{role.name}' to {interaction.author} in '{interaction.guild.name}' (role too high).")
                                await safe_followup(interaction, f"❌ I can't assign the role `{role.name}` because it's higher than my own."
                                    " Please move my bot role up in the role settings.", ephemeral=True, delete_after=config.message_timeout)
                                continue

                            await interaction.author.add_roles(role)
                            reassigned_roles.append(role.name)
                            logger.info(f"[Role Assigned] Gave '{role.name}' to {interaction.author} in '{interaction.guild.name}' for '{product_name}'.")
            else:
                unowned_products[product_name] = product_secret
                logger.info(f"[Unowned Product] {interaction.author} in '{interaction.guild.name}' does not own '{product_name}'.")

        if reassigned_roles:
            await safe_followup(interaction, f"The following roles have been reassigned: {', '.join(reassigned_roles)}", ephemeral=True, delete_after=config.message_timeout)

        if unowned_products:
            options = [
                disnake.SelectOption(label=name, description=f"Verify {name}")
                for name in unowned_products.keys()
            ]
            dropdown = disnake.ui.StringSelect(placeholder="Choose a product", options=options)
            dropdown.callback = lambda inter: handle_product_dropdown(inter, unowned_products)

            dropdown_view = disnake.ui.View()
            dropdown_view.add_item(dropdown)

            logger.info(f"[Dropdown Sent] {interaction.author} prompted to verify unowned products in '{interaction.guild.name}'.")
            await safe_followup(interaction, "Select a product to verify:", view=dropdown_view, ephemeral=True, delete_after=config.message_timeout)

        elif not reassigned_roles:
            await safe_followup(interaction, "✅ All available products have already been verified, and no roles needed reassignment.", ephemeral=True, delete_after=config.message_timeout)
            logger.info(f"[Fully Verified] {interaction.author} already owns all roles in '{interaction.guild.name}'.")

# Called when a user selects a product from the dropdown.
# Opens a modal prompting for license verification input.
async def handle_product_dropdown(interaction, products):
    product_name = interaction.data["values"][0]
    product_secret_key = products[product_name]
    modal = VerifyLicenseModal(product_name, product_secret_key)
    try:
        await interaction.response.send_modal(modal)
    except disnake.NotFound:
        # Interaction expired (user clicked too late)
        logger.warning(f"[Expired Interaction] User {interaction.user} tried to verify after interaction expired.")
