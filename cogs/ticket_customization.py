import disnake
from disnake.ext import commands
from utils.database import get_database_pool, fetch_products_with_stock
import config
import logging
import re

logger = logging.getLogger(__name__)

class TicketCustomization(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.setup_table())
        
    async def setup_table(self):
        """Creates table for storing custom ticket box settings"""
        await self.bot.wait_until_ready()
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_customization (
                    guild_id TEXT PRIMARY KEY,
                    title TEXT DEFAULT 'Support Tickets',
                    description TEXT DEFAULT 'Need help with one of our products? Click the button below to create a support ticket!

**What happens next?**
• Select the product you need help with
• A private channel will be created for you
• Provide your license key for verification
• Get personalized support from our team',
                    button_text TEXT DEFAULT 'Create Ticket',
                    button_emoji TEXT DEFAULT '🎫',
                    show_stock_info BOOLEAN DEFAULT TRUE
                );
            """)

    @commands.slash_command(
        description="Customize the ticket box appearance and text (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def customize_ticket_box(self, inter: disnake.ApplicationCommandInteraction):
        """Customize the ticket box with variables support"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can customize the ticket box.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Get current settings
        async with (await get_database_pool()).acquire() as conn:
            current = await conn.fetchrow(
                "SELECT * FROM ticket_customization WHERE guild_id = $1",
                str(inter.guild.id)
            )

        await inter.response.send_modal(CustomizeTicketModal(current))

    @commands.slash_command(
        description="Preview variables available for ticket customization (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def ticket_variables(self, inter: disnake.ApplicationCommandInteraction):
        """Shows available variables for ticket customization"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can view this.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        embed = disnake.Embed(
            title="🎫 Ticket Box Variables",
            description="Use these variables in your custom ticket box text:",
            color=disnake.Color.blue()
        )

       embed.add_field(
    name="📊 Product Variables",
    value=(
        "`{PRODUCT_COUNT}` - Total number of products\n"
        "`{PRODUCTNAME.STOCK}` - Stock for specific product*\n"
        "`{TOTAL_STOCK}` - Combined stock of all products\n"
        "`{TOTAL_SALES}` - Total sales across all products\n"
        "`{PRODUCTS_IN_STOCK}` - Number of products available\n"
        "`{PRODUCTS_SOLD_OUT}` - Number of sold out products"
    ),
    inline=False
)

        embed.add_field(
            name="🏠 Server Variables",
            value=(
                "`{SERVER_NAME}` - Server name\n"
                "`{SERVER_MEMBER_COUNT}` - Total members\n"
                "`{SERVER_OWNER}` - Server owner mention\n"
                "`{CURRENT_DATE}` - Today's date\n"
                "`{CURRENT_TIME}` - Current time"
            ),
            inline=False
        )

        embed.add_field(
            name="📝 Examples",
            value=(
                "`We have {PRODUCT_COUNT} products available!`\n"
                "`Premium Bot has {Premium Bot.STOCK} licenses left`\n"
                "`Welcome to {SERVER_NAME} with {SERVER_MEMBER_COUNT} members!`"
            ),
            inline=False
        )

        embed.add_field(
            name="⚠️ Important Notes",
            value=(
                "• Replace spaces in product names with underscores for variables\n"
                "• Example: `My Cool Product` → `{My_Cool_Product.STOCK}`\n"
                "• Variables are case-sensitive\n"
                "• Use `/customize_ticket_box` to apply changes"
            ),
            inline=False
        )

        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.slash_command(
        description="Reset ticket box to default appearance (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def reset_ticket_box(self, inter: disnake.ApplicationCommandInteraction):
        """Reset ticket box to default settings"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can reset the ticket box.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        class ConfirmResetView(disnake.ui.View):
            def __init__(self):
                super().__init__(timeout=30)

            @disnake.ui.button(label="✅ Reset to Default", style=disnake.ButtonStyle.danger)
            async def confirm(self, button, button_inter):
                async with (await get_database_pool()).acquire() as conn:
                    await conn.execute(
                        "DELETE FROM ticket_customization WHERE guild_id = $1",
                        str(inter.guild.id)
                    )
                
                await button_inter.response.send_message(
                    "✅ Ticket box reset to default settings. Use `/create_ticket_box` to apply changes.",
                    ephemeral=True
                )
                self.stop()

            @disnake.ui.button(label="❌ Cancel", style=disnake.ButtonStyle.secondary)
            async def cancel(self, button, button_inter):
                await button_inter.response.send_message("Reset cancelled.", ephemeral=True)
                self.stop()

        view = ConfirmResetView()
        await inter.response.send_message(
            "⚠️ Are you sure you want to reset the ticket box to default settings?",
            view=view,
            ephemeral=True
        )

async def parse_variables(text: str, guild, products_data=None) -> str:
    """Parse variables in text and replace with actual values"""
    if not text:
        return text

    # Get products data if not provided
    if products_data is None:
        products_data = await fetch_products_with_stock(str(guild.id))
    
    # Server variables
    text = text.replace("{SERVER_NAME}", guild.name)
    text = text.replace("{SERVER_MEMBER_COUNT}", str(guild.member_count))
    text = text.replace("{SERVER_OWNER}", guild.owner.mention if guild.owner else "Unknown")
    
    # Date/time variables
    from datetime import datetime
    now = datetime.now()
    text = text.replace("{CURRENT_DATE}", now.strftime("%B %d, %Y"))
    text = text.replace("{CURRENT_TIME}", now.strftime("%H:%M"))
    
    # Product variables
    text = text.replace("{PRODUCT_COUNT}", str(len(products_data)))
    
    total_stock = sum(data["stock"] for data in products_data.values() if data["stock"] != -1)
    unlimited_count = sum(1 for data in products_data.values() if data["stock"] == -1)
    
    if unlimited_count > 0:
        text = text.replace("{TOTAL_STOCK}", f"{total_stock} + {unlimited_count} unlimited")
    else:
        text = text.replace("{TOTAL_STOCK}", str(total_stock))
    
    products_in_stock = sum(1 for data in products_data.values() if data["stock"] != 0)
    text = text.replace("{PRODUCTS_IN_STOCK}", str(products_in_stock))
    
    products_sold_out = sum(1 for data in products_data.values() if data["stock"] == 0)
    text = text.replace("{PRODUCTS_SOLD_OUT}", str(products_sold_out))
    
    # Product-specific stock variables: {ProductName.STOCK}
    stock_pattern = r'\{([^}]+)\.STOCK\}'
    matches = re.finditer(stock_pattern, text)
    
    for match in matches:
        var_name = match.group(0)  # Full match like {ProductName.STOCK}
        product_name = match.group(1).replace("_", " ")  # Product name with spaces restored
        
        if product_name in products_data:
            stock = products_data[product_name]["stock"]
            if stock == -1:
                stock_text = "Unlimited"
            elif stock == 0:
                stock_text = "SOLD OUT"
            else:
                stock_text = str(stock)
            text = text.replace(var_name, stock_text)
        else:
            text = text.replace(var_name, "N/A")
    
    return text

class CustomizeTicketModal(disnake.ui.Modal):
    def __init__(self, current_settings=None):
        self.current = current_settings
        
        # Default values
        default_title = "🎫 Support Tickets"
        default_description = """Need help with one of our products? Click the button below to create a support ticket!

**What happens next?**
• Select the product you need help with
• A private channel will be created for you
• Provide your license key for verification
• Get personalized support from our team

**Server Stats:**
• Products: {PRODUCT_COUNT}
• Members: {SERVER_MEMBER_COUNT}
• In Stock: {PRODUCTS_IN_STOCK}"""
        
        default_button = "Create Ticket"
        default_emoji = "🎫"
        
        if current_settings:
            default_title = current_settings["title"] or default_title
            default_description = current_settings["description"] or default_description
            default_button = current_settings["button_text"] or default_button
            default_emoji = current_settings["button_emoji"] or default_emoji
        
        components = [
            disnake.ui.TextInput(
                label="Title",
                custom_id="title",
                value=default_title,
                style=disnake.TextInputStyle.short,
                max_length=256,
            ),
            disnake.ui.TextInput(
                label="Description (supports variables)",
                custom_id="description",
                value=default_description,
                style=disnake.TextInputStyle.paragraph,
                max_length=2000,
            ),
            disnake.ui.TextInput(
                label="Button Text",
                custom_id="button_text",
                value=default_button,
                style=disnake.TextInputStyle.short,
                max_length=50,
            ),
            disnake.ui.TextInput(
                label="Button Emoji",
                custom_id="button_emoji",
                value=default_emoji,
                style=disnake.TextInputStyle.short,
                max_length=10,
            )
        ]
        super().__init__(title="Customize Ticket Box", components=components)

    async def callback(self, interaction: disnake.ModalInteraction):
        title = interaction.text_values["title"].strip()
        description = interaction.text_values["description"].strip()
        button_text = interaction.text_values["button_text"].strip()
        button_emoji = interaction.text_values["button_emoji"].strip()

        # Save settings to database
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ticket_customization (guild_id, title, description, button_text, button_emoji)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (guild_id) 
                DO UPDATE SET 
                    title = $2, 
                    description = $3, 
                    button_text = $4, 
                    button_emoji = $5
                """,
                str(interaction.guild.id), title, description, button_text, button_emoji
            )

        # Show preview
        products_data = await fetch_products_with_stock(str(interaction.guild.id))
        parsed_description = await parse_variables(description, interaction.guild, products_data)
        
        embed = disnake.Embed(
            title=title,
            description=parsed_description,
            color=disnake.Color.blurple()
        )
        embed.set_footer(text="Powered by KeyVerify")
        
        # Create preview button
        preview_button = disnake.ui.Button(
            label=button_text,
            style=disnake.ButtonStyle.green,
            emoji=button_emoji,
            disabled=True
        )
        view = disnake.ui.View()
        view.add_item(preview_button)

        await interaction.response.send_message(
            f"✅ **Ticket box customized!**\n\n**Preview:**",
            embed=embed,
            view=view,
            ephemeral=True,
            delete_after=config.message_timeout
        )

def setup(bot):
    bot.add_cog(TicketCustomization(bot))
