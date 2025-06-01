import disnake
from disnake.ext import commands
from utils.encryption import encrypt_data
from utils.database import get_database_pool
import config
import logging
import uuid

logger = logging.getLogger(__name__)
product_session_cache = {}  # session_id -> (product_name, product_secret)

class AddProduct(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        description="Add a product to the server's list with an assigned role (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def add_product(self, inter: disnake.ApplicationCommandInteraction):
        if inter.author.id != inter.guild.owner_id:
            logger.warning(f"[Unauthorized Attempt] {inter.author} tried to add a product in '{inter.guild.name}'")
            await inter.response.send_message(
                "❌ Only the server owner can use this command.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

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
                label="Product Secret",
                custom_id="product_secret",
                placeholder="Enter the Payhip product secret",
                style=disnake.TextInputStyle.short,
                max_length=100,
            )
        ]
        super().__init__(
            title="Add a New Product",
            custom_id="add_product_modal",
            components=components
        )

    async def callback(self, interaction: disnake.ModalInteraction):
        product_name = interaction.text_values["product_name"].strip()
        product_secret = interaction.text_values["product_secret"].strip()

        # Create a session ID to avoid long custom_id
        session_id = str(uuid.uuid4())[:12]
        product_session_cache[session_id] = (product_name, product_secret)

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
            custom_id=f"role_select:{session_id}"
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
            product_name, product_secret = product_session_cache.pop(session_id)
        except Exception as e:
            logger.error(f"[Role Selection Error] Invalid session ID: {e}")
            await interaction.response.send_message("❌ Something went wrong. Please try again.", ephemeral=True)
            return

        selected_value = interaction.data['values'][0]
        if selected_value == "auto":
            role_name = f"Verified-{product_name}"
            role = await interaction.guild.create_role(name=role_name)
            await interaction.response.send_message(f"Role '{role.name}' was created automatically.", ephemeral=True,
                                                    delete_after=config.message_timeout)
        else:
            role = interaction.guild.get_role(int(selected_value))
            await interaction.response.send_message(f"Selected role: {role.mention}", ephemeral=True,
                                                    delete_after=config.message_timeout)

        encrypted_secret = encrypt_data(product_secret)

        async with (await get_database_pool()).acquire() as conn:
            try:
                await conn.execute(
                    "INSERT INTO products (guild_id, product_name, product_secret, role_id) VALUES ($1, $2, $3, $4)",
                    str(interaction.guild.id), product_name, encrypted_secret, str(role.id)
                )
                logger.info(f"[Product Added] '{product_name}' added to '{interaction.guild.name}' with role '{role.name}'")
                await interaction.followup.send(
                    f"✅ Product **`{product_name}`** added successfully with role {role.mention}.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
            except Exception:
                logger.warning(f"[Duplicate Product] Attempt to add duplicate product '{product_name}' in '{interaction.guild.name}'")
                await interaction.followup.send(
                    f"❌ Product '{product_name}' already exists.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )

def setup(bot):
    bot.add_cog(AddProduct(bot))
