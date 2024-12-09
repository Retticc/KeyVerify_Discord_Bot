import disnake
from handlers.verify_license_modal import VerifyLicenseModal
from utils.database import fetch_products
import config
from utils.database import get_database_pool
from utils.encryption import decrypt_data

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

class VerificationButton(disnake.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        button = disnake.ui.Button(label="Verify", style=disnake.ButtonStyle.primary, custom_id="verify_button")
        button.callback = self.on_button_click
        self.add_item(button)

    async def on_button_click(self, interaction: disnake.MessageInteraction):
        await interaction.response.defer(ephemeral=True)  # Ensure the interaction is acknowledged promptly.

        user_id = interaction.author.id
        guild_id = self.guild_id

        # Fetch all products for the guild
        products = await fetch_products(guild_id)
        if not products:
            await interaction.followup.send(
                "❌ No products available for verification.",
                ephemeral=True,delete_after=config.message_timeout
            )
            return

        # Track reassigned roles and unowned products
        reassigned_roles = []
        unowned_products = {}

        for product_name, product_secret in products.items():
            verified_key = await get_verified_license(user_id, guild_id, product_name)
            if verified_key:
                # Reassign roles for owned products
                async with (await get_database_pool()).acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT role_id FROM products WHERE guild_id = $1 AND product_name = $2",
                        str(guild_id), product_name
                    )
                    if row:
                        role = disnake.utils.get(interaction.guild.roles, id=int(row["role_id"]))
                        if role and role not in interaction.author.roles:
                            await interaction.author.add_roles(role)
                            reassigned_roles.append(role.name)
            else:
                # Add to unowned products for the dropdown
                unowned_products[product_name] = product_secret

        # Notify the user about reassigned roles only if roles were reassigned
        if reassigned_roles:
            await interaction.followup.send(
                f"The following roles have been reassigned: {', '.join(reassigned_roles)}",
                ephemeral=True,delete_after=config.message_timeout
            )

        # If there are unowned products, show the dropdown
        if unowned_products:
            options = [
                disnake.SelectOption(label=name, description=f"Verify {name}")
                for name in unowned_products.keys()
            ]
            dropdown = disnake.ui.StringSelect(placeholder="Choose a product", options=options)
            dropdown.callback = lambda inter: handle_product_dropdown(inter, unowned_products)

            dropdown_view = disnake.ui.View()
            dropdown_view.add_item(dropdown)

            await interaction.followup.send(
                "Select a product to verify:",
                view=dropdown_view,
                ephemeral=True,delete_after=config.message_timeout
            )
        elif not reassigned_roles:
            # If no roles were reassigned and no unowned products are left
            await interaction.followup.send(
                "✅ All available products have already been verified, and no roles needed reassignment.",
                ephemeral=True,delete_after=config.message_timeout
            )


async def handle_product_dropdown(interaction, products):
    product_name = interaction.data["values"][0]
    product_secret_key = products[product_name]
    modal = VerifyLicenseModal(product_name, product_secret_key)
    await interaction.response.send_modal(modal)
