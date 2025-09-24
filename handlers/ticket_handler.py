import disnake
from disnake.ext.commands import CooldownMapping, BucketType
from utils.database import fetch_products, get_database_pool
from utils.helper import safe_followup
import config
import time
import logging
import asyncio
import re

logger = logging.getLogger(__name__)

async def parse_variables(text: str, guild, products_data=None) -> str:
    """Parse variables in text and replace with actual values"""
    if not text:
        return text

    # Get products data if not provided
    if products_data is None:
        from utils.database import fetch_products_with_stock
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

async def create_ticket_embed(guild):
    """Creates the main ticket box embed with custom text support"""
    # Get custom settings
    async with (await get_database_pool()).acquire() as conn:
        custom = await conn.fetchrow(
            "SELECT * FROM ticket_customization WHERE guild_id = $1",
            str(guild.id)
        )
    
    # Default values
    if custom:
        title = custom["title"] or "🎫 Support Tickets"
        description = custom["description"] or """Need help with one of our products? Click the button below to create a support ticket!

**What happens next?**
• Select the product you need help with
• A private channel will be created for you
• Provide your license key for verification
• Get personalized support from our team"""
    else:
        title = "🎫 Support Tickets"
        description = """Need help with one of our products? Click the button below to create a support ticket!

**What happens next?**
• Select the product you need help with
• A private channel will be created for you
• Provide your license key for verification
• Get personalized support from our team"""
    
    # Parse variables in the description
    parsed_description = await parse_variables(description, guild)
    
    embed = disnake.Embed(
        title=title,
        description=parsed_description,
        color=disnake.Color.blurple()
    )
    embed.set_footer(text="Powered by KeyVerify")
    return embed

def create_ticket_view(guild_id):
    """Returns an instance of the ticket creation button view"""
    return TicketButton(guild_id)

async def fetch_products_with_stock(guild_id):
    """Fetches all products with their stock information"""
    async with (await get_database_pool()).acquire() as conn:
        rows = await conn.fetch(
            "SELECT product_name, product_secret, stock FROM products WHERE guild_id = $1", 
            guild_id
        )
        from utils.encryption import decrypt_data
        return {
            row["product_name"]: {
                "secret": decrypt_data(row["product_secret"]),
                "stock": row["stock"] if row["stock"] is not None else -1
            } 
            for row in rows
        }

# Cooldown for ticket creation: 1 ticket every 60 seconds per user
ticket_cooldown = CooldownMapping.from_cooldown(1, 60, BucketType.user)

class TicketButton(disnake.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        # Button will be created in on_ready to get custom settings
        
    async def setup_button(self, guild):
        """Setup button with custom text and emoji"""
        # Get custom settings
        async with (await get_database_pool()).acquire() as conn:
            custom = await conn.fetchrow(
                "SELECT button_text, button_emoji FROM ticket_customization WHERE guild_id = $1",
                str(guild.id)
            )
        
        button_text = "Create Ticket"
        button_emoji = "🎫"
        
        if custom:
            button_text = custom["button_text"] or button_text
            button_emoji = custom["button_emoji"] or button_emoji
        
        button = disnake.ui.Button(
            label=button_text, 
            style=disnake.ButtonStyle.green, 
            custom_id=f"create_ticket_{self.guild_id}",
            emoji=button_emoji
        )
        button.callback = self.on_button_click
        self.clear_items()
        self.add_item(button)
        
    async def on_button_click(self, interaction: disnake.MessageInteraction):
        """Handles the ticket creation button click"""
        # Cooldown check
        current = time.time()
        bucket = ticket_cooldown.get_bucket(interaction)
        retry_after = bucket.update_rate_limit(current)

        if retry_after:
            logger.warning(f"[Ticket Cooldown] {interaction.author} tried to create ticket too quickly in '{interaction.guild.name}'")
            await interaction.response.send_message(
                f"⏳ Please wait `{int(retry_after)}s` before creating another ticket.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Check if user already has an open ticket
        async with (await get_database_pool()).acquire() as conn:
            existing_ticket = await conn.fetchrow(
                "SELECT channel_id FROM active_tickets WHERE guild_id = $1 AND user_id = $2",
                str(interaction.guild.id), str(interaction.author.id)
            )
            
            if existing_ticket:
                channel = interaction.guild.get_channel(int(existing_ticket["channel_id"]))
                if channel:
                    await safe_followup(
                        interaction,
                        f"❌ You already have an open ticket: {channel.mention}",
                        ephemeral=True,
                        delete_after=config.message_timeout
                    )
                    return
                else:
                    # Clean up stale ticket record
                    await conn.execute(
                        "DELETE FROM active_tickets WHERE guild_id = $1 AND channel_id = $2",
                        str(interaction.guild.id), existing_ticket["channel_id"]
                    )

        # Get products with stock information
        products = await fetch_products_with_stock(str(interaction.guild.id))
        if not products:
            await safe_followup(
                interaction,
                "❌ No products available for tickets.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Create product selection dropdown with stock status
        options = []
        
        # Add general support option first
        options.append(disnake.SelectOption(
            label="General Support",
            description="General questions or issues",
            value="general",
            emoji="❓"
        ))

        # Add products with stock indicators
        for product_name, product_data in products.items():
            stock = product_data["stock"]
            
            if stock == 0:
                # Sold out - show as disabled option
                label = f"🔴 {product_name} (SOLD OUT)"
                description = "This product is currently sold out"
                emoji = "🔴"
                # We'll still add it but handle it in the callback
                options.append(disnake.SelectOption(
                    label=label[:100],  # Discord limit
                    description=description[:100],  # Discord limit
                    value=f"soldout_{product_name}",
                    emoji=emoji
                ))
            elif stock == -1:
                # Unlimited stock
                label = f"♾️ {product_name}"
                description = f"Create ticket for {product_name} (In Stock)"
                emoji = "♾️"
                options.append(disnake.SelectOption(
                    label=label[:100],
                    description=description[:100],
                    value=product_name,
                    emoji=emoji
                ))
            elif stock <= 5:
                # Low stock warning
                label = f"🟡 {product_name} ({stock} left)"
                description = f"Create ticket for {product_name} (Low Stock)"
                emoji = "🟡"
                options.append(disnake.SelectOption(
                    label=label[:100],
                    description=description[:100],
                    value=product_name,
                    emoji=emoji
                ))
            else:
                # Normal stock
                label = f"🟢 {product_name}"
                description = f"Create ticket for {product_name} (In Stock)"
                emoji = "🟢"
                options.append(disnake.SelectOption(
                    label=label[:100],
                    description=description[:100],
                    value=product_name,
                    emoji=emoji
                ))

        # Limit to Discord's maximum of 25 options
        options = options[:25]

        dropdown = disnake.ui.StringSelect(
            placeholder="Select the product you need help with...",
            options=options
        )
        dropdown.callback = lambda inter: self.handle_product_selection(inter, products)

        dropdown_view = disnake.ui.View()
        dropdown_view.add_item(dropdown)

        await safe_followup(
            interaction,
            "🎫 **Create Support Ticket**\nSelect the product you need help with:",
            view=dropdown_view,
            ephemeral=True,
            delete_after=config.message_timeout
        )

    async def handle_product_selection(self, interaction, products):
        """Handles product selection and creates the ticket channel"""
        selected_value = interaction.data["values"][0]
        
        # Check if it's a sold out product
        if selected_value.startswith("soldout_"):
            product_name = selected_value.replace("soldout_", "")
            await interaction.response.send_message(
                f"❌ **{product_name}** is currently sold out and not available for new tickets.\n"
                "Please select a different product or contact support through general support.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return
        
        selected_product = selected_value
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get next ticket number
            async with (await get_database_pool()).acquire() as conn:
                # Initialize counter if it doesn't exist
                await conn.execute(
                    """
                    INSERT INTO ticket_counters (guild_id, counter)
                    VALUES ($1, 0)
                    ON CONFLICT (guild_id) DO NOTHING
                    """,
                    str(interaction.guild.id)
                )
                
                # Increment and get new ticket number
                result = await conn.fetchrow(
                    """
                    UPDATE ticket_counters 
                    SET counter = counter + 1 
                    WHERE guild_id = $1 
                    RETURNING counter
                    """,
                    str(interaction.guild.id)
                )
                ticket_number = result["counter"]

            # Create ticket channel
            guild = interaction.guild
            user = interaction.author
            
            # Set up channel permissions
            overwrites = {
                guild.default_role: disnake.PermissionOverwrite(read_messages=False),
                user: disnake.PermissionOverwrite(
                    read_messages=True, 
                    send_messages=True, 
                    attach_files=True,
                    embed_links=True
                ),
                guild.me: disnake.PermissionOverwrite(
                    read_messages=True, 
                    send_messages=True, 
                    manage_messages=True,
                    embed_links=True
                ),
            }
            
            # Add server owner permissions
            if guild.owner:
                overwrites[guild.owner] = disnake.PermissionOverwrite(
                    read_messages=True, 
                    send_messages=True, 
                    manage_messages=True
                )
            
            # Add permissions for roles with manage_channels permission
            for role in guild.roles:
                if role.permissions.manage_channels:
                    overwrites[role] = disnake.PermissionOverwrite(
                        read_messages=True, 
                        send_messages=True, 
                        manage_messages=True
                    )

            # Create the channel
            channel_name = f"ticket-{ticket_number:04d}-{user.display_name.lower().replace(' ', '-')}"
            channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                reason=f"Ticket created by {user} for {selected_product}"
            )

            # Save ticket to database
            async with (await get_database_pool()).acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO active_tickets (guild_id, channel_id, user_id, product_name, ticket_number)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    str(guild.id), str(channel.id), str(user.id), 
                    selected_product if selected_product != "general" else None, ticket_number
                )

            # Get stock info for display
            stock_info = ""
            if selected_product != "general" and selected_product in products:
                stock = products[selected_product]["stock"]
                if stock == -1:
                    stock_info = "♾️ **Stock:** Unlimited"
                elif stock <= 5:
                    stock_info = f"🟡 **Stock:** {stock} remaining"
                else:
                    stock_info = f"🟢 **Stock:** {stock} available"

            # Create welcome embed for the ticket
            welcome_embed = disnake.Embed(
                title=f"🎫 Support Ticket #{ticket_number:04d}",
                description=(
                    f"Hello {user.mention}! Welcome to your support ticket.\n\n"
                    f"**Product:** {selected_product}\n"
                    f"{stock_info}\n" if stock_info else ""
                    f"**Created:** <t:{int(time.time())}:F>\n\n"
                ),
                color=disnake.Color.green()
            )
            
            if selected_product != "general":
                welcome_embed.description += (
                    "**📋 Next Steps:**\n"
                    "Please provide your license key for this product so we can verify your purchase and assist you better.\n\n"
                    "**🔒 Privacy Notice:**\n"
                    "This is a private channel - only you, server moderators, and the server owner can see this conversation."
                )
            else:
                welcome_embed.description += (
                    "**📋 Next Steps:**\n"
                    "Please describe your question or issue in detail, and our support team will assist you shortly.\n\n"
                    "**🔒 Privacy Notice:**\n"
                    "This is a private channel - only you, server moderators, and the server owner can see this conversation."
                )

            welcome_embed.set_footer(text="Use /close_ticket to close this ticket when resolved")

            await channel.send(embed=welcome_embed)

            # If it's a product-specific ticket, ask for license key
            if selected_product != "general":
                license_embed = disnake.Embed(
                    title="🔑 License Verification Required",
                    description=(
                        f"To provide you with the best support for **{selected_product}**, "
                        "please share your license key in the format: `XXXXX-XXXXX-XXXXX-XXXXX`\n\n"
                        "**Why do we need this?**\n"
                        "• Verify your purchase\n"
                        "• Access your product details\n"
                        "• Provide personalized assistance\n\n"
                        "*Your license key will only be used for support purposes.*"
                    ),
                    color=disnake.Color.blue()
                )
                license_embed.set_footer(text="Please paste your license key in your next message")
                
                await asyncio.sleep(2)  # Small delay for better UX
                await channel.send(embed=license_embed)

            logger.info(f"[Ticket Created] #{ticket_number:04d} created by {user} for '{selected_product}' in '{guild.name}'")
            
            await safe_followup(
                interaction,
                f"✅ Ticket created! Check out {channel.mention}",
                ephemeral=True,
                delete_after=config.message_timeout
            )

        except disnake.Forbidden:
            await safe_followup(
                interaction,
                "❌ I don't have permission to create channels. Please contact an administrator.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"[Ticket Creation Failed] Error creating ticket for {interaction.author}: {e}")
            await safe_followup(
                interaction,
                "❌ Failed to create ticket. Please try again later.",
                ephemeral=True
            )
