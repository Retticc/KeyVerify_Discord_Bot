import disnake
from handlers.verify_license_modal import VerifyLicenseModal
from utils.database import fetch_products
import config

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

class VerificationButton(disnake.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        button = disnake.ui.Button(label="Verify", style=disnake.ButtonStyle.primary, custom_id="verify_button")
        button.callback = self.on_button_click
        self.add_item(button)

    async def on_button_click(self, interaction: disnake.MessageInteraction):
        products = await fetch_products(self.guild_id)
        if not products:
            await interaction.response.send_message("❌ No products available for verification.", ephemeral=True,delete_after=config.message_timeout)
            return

        options = [
            disnake.SelectOption(label=name, description=f"Verify {name}")
            for name in products.keys()
        ]

        dropdown = disnake.ui.StringSelect(placeholder="Choose a product", options=options)
        dropdown.callback = lambda inter: handle_product_dropdown(inter, products)

        dropdown_view = disnake.ui.View()
        dropdown_view.add_item(dropdown)
        await interaction.response.send_message("Select a product to verify:", view=dropdown_view, ephemeral=True,delete_after=config.message_timeout)

async def handle_product_dropdown(interaction, products):
    product_name = interaction.data["values"][0]
    product_secret_key = products[product_name]
    modal = VerifyLicenseModal(product_name, product_secret_key)
    await interaction.response.send_modal(modal)
