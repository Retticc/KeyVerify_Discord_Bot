# Updated handlers/ticket_handler.py with payment method dropdown for tickets

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

async def has_ticket_permission(user, guild):
    """Check if user can access tickets"""
    if user.id == guild.owner_id:
        return True

    async with (await get_database_pool()).acquire() as conn:
        user_role_ids = [str(role.id) for role in user.roles]
        if not user_role_ids:
            return False

        result = await conn.fetchrow(
            """
            SELECT 1 FROM role_permissions 
            WHERE guild_id = $1 AND role_id = ANY($2) 
            AND (permission_type = $3 OR permission_type = $4)
            """,
            str(guild.id), user_role_ids, "handle_tickets", "manage_tickets"
        )
        return result is not None

async def get_ticket_discord_category(guild_id, ticket_type, category_name=None):
    """Get the Discord category for a specific ticket type"""
    async with (await get_database_pool()).acquire() as conn:
        category_name_val = category_name if category_name else ''
        result = await conn.fetchrow(
            "SELECT discord_category_id FROM ticket_discord_categories WHERE guild_id = $1 AND ticket_type = $2 AND category_name = $3",
            guild_id, ticket_type, category_name_val
        )
    
    return result["discord_category_id"] if result else None

async def parse_variables(text: str, guild, products_data=None) -> str:
    """Parse variables in text and replace with actual values"""
    if not text:
        return text

    if products_data is None:
        products_data = await fetch_products_with_payment_info(str(guild.id))
        
    # Get total sales from database
    async with (await get_database_pool()).acquire() as conn:
        total_sales_result = await conn.fetchval(
            "SELECT COALESCE(SUM(total_sold), 0) FROM product_sales WHERE guild_id = $1",
            str(guild.id)
        )
    
    total_sales = total_sales_result or 0
    text = text.replace("{TOTAL_SALES}", f"{total_sales:,}")
    
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
    
    # Product-specific stock variables
    stock_pattern = r'\{([^}]+)\.STOCK\}'
    matches = re.finditer(stock_pattern, text)
    
    for match in matches:
        var_name = match.group(0)
        product_name = match.group(1).replace("_", " ")
        
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
    async with (await get_database_pool()).acquire() as conn:
        custom = await conn.fetchrow(
            "SELECT * FROM ticket_customization WHERE guild_id = $1",
            str(guild.id)
        )
    
    if custom:
        title = custom["title"] or "🎫 Support Tickets"
        description = custom["description"] or """Need help with one of our products? Click the button below to create a support ticket!

**What happens next?**
- Select the product you need help with
- A private channel will be created for you
- Provide your license key for verification
- Get personalized support from our team"""
    else:
        title = "🎫 Support Tickets"
        description = """Need help with one of our products? Click the button below to create a support ticket!

**What happens next?**
- Select the product you need help with
- A private channel will be created for you
- Provide your license key for verification
- Get personalized support from our team"""
    
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

async def fetch_products_with_payment_info(guild_id):
    """Fetches all products with payment information for tickets"""
    async with (await get_database_pool()).acquire() as conn:
        rows = await conn.fetch(
            """SELECT product_name, payment_methods, stock, description 
               FROM products WHERE guild_id = $1""", 
            guild_id
        )
        
        products = {}
        for row in rows:
            payment_methods = parse_payment_methods(row["payment_methods"]) if row["payment_methods"] else {}
            
            products[row["product_name"]] = {
                "payment_methods": payment_methods,
                "stock": row["stock"] if row["stock"] is not None else -1,
                "description": row["description"]
            }
        
        # Always add Test product
        products["Test"] = {
            "payment_methods": {"usd": "Free"},
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

async def fetch_ticket_categories(guild_id):
    """Fetches custom ticket categories for a guild"""
    async with (await get_database_pool()).acquire() as conn:
        categories = await conn.fetch(
            "SELECT category_name, category_description, emoji FROM ticket_categories WHERE guild_id = $1 ORDER BY display_order",
            guild_id
        )
        return categories

async def create_product_ticket_embed(user, selected_name, selected_data, ticket_number, discord_category, payment_method=None):
    """Create ticket embed for products with payment method info"""
    embed = disnake.Embed(
        title=f"🎫 Private Support Ticket #{ticket_number:04d}",
        description=f"Hello {user.mention}! Welcome to your **private** support ticket.",
        color=disnake.Color.green()
    )
    
    # Product name
    embed.add_field(
        name="🎁 Product",
        value=f"**{selected_name}**",
        inline=True
    )
    
    # Payment method selection
    if payment_method:
        payment_methods = selected_data.get("payment_methods", {})
        if payment_method in payment_methods:
            if payment_method == "usd":
                embed.add_field(
                    name="💳 Payment Method",
                    value=f"**PayHip License** - {payment_methods[payment_method]}",
                    inline=True
                )
            elif payment_method == "robux":
                embed.add_field(
                    name="🎮 Payment Method", 
                    value=f"**Roblox Gamepass** - {payment_methods[payment_method]}",
                    inline=True
                )
    
    # Stock information
    stock = selected_data.get("stock", -1)
    if stock == -1:
        stock_display = "♾️ **Unlimited**"
    elif stock == 0:
        stock_display = "🔴 **SOLD OUT**"
    elif stock <= 5:
        stock_display = f"🟡 **{stock} remaining**"
    else:
        stock_display = f"🟢 **{stock} available**"
    
    embed.add_field(
        name="📦 Stock Status",
        value=stock_display,
        inline=True
    )
    
    # Product description
    if selected_data.get("description"):
        embed.add_field(
            name="📋 Description",
            value=selected_data["description"],
            inline=False
        )
    
    # Ticket details
    embed.add_field(
        name="⏰ Created",
        value=f"<t:{int(time.time())}:F>",
        inline=True
    )
    
    embed.add_field(
        name="📍 Category",
        value=f"**{discord_category.name}**" if discord_category else "**Default**",
        inline=True
    )
    
    # Payment-specific instructions
    if payment_method == "usd":
        next_steps_text = (
            "**💳 PayHip License Verification:**\n\n"
            "• Share your license key (XXXXX-XXXXX-XXXXX-XXXXX)\n"
            "• Our team will verify your purchase\n"
            "• Get personalized support for your product"
        )
    elif payment_method == "robux":
        next_steps_text = (
            "**🎮 Roblox Gamepass Verification:**\n\n"
            "• Share your exact Roblox username\n"
            "• Mention that you purchased the gamepass\n"
            "• Our team will assist with your gamepass-related question"
        )
    else:
        next_steps_text = "Please describe your question or issue in detail."
    
    embed.add_field(
        name="📋 Next Steps",
        value=next_steps_text,
        inline=False
    )
    
    embed.add_field(
        name="🔒 Privacy Notice",
        value="This is a **PRIVATE** channel - only you and authorized support staff can see this conversation.",
        inline=False
    )
    
    embed.set_footer(text="Use /close_ticket to close this ticket when resolved")
    
    return embed

# Cooldown for ticket creation
ticket_cooldown = CooldownMapping.from_cooldown(1, 60, BucketType.user)

class TicketButton(disnake.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        
    async def setup_button(self, guild):
        """Setup button with custom text and emoji"""
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
                    await conn.execute(
                        "DELETE FROM active_tickets WHERE guild_id = $1 AND channel_id = $2",
                        str(interaction.guild.id), existing_ticket["channel_id"]
                    )

        categories = await fetch_ticket_categories(str(interaction.guild.id))
        products = await fetch_products_with_payment_info(str(interaction.guild.id))

        if not categories and not products:
            await self.create_default_ticket(interaction, "General Support")
            return

        options = []
        
        # Add custom categories first
        for category in categories:
            if category["category_name"] not in products:
                emoji = category["emoji"] or "🎫"
                options.append(disnake.SelectOption(
                    label=category["category_name"],
                    description=category["category_description"],
                    value=f"category_{category['category_name']}",
                    emoji=emoji
                ))

        # Add products
        for product_name, product_data in products.items():
            stock = product_data.get("stock", -1)
            payment_methods = product_data.get("payment_methods", {})
            description = product_data.get("description", "")
            
            # Create description showing payment options
            desc_parts = []
            
            payment_options = []
            if "usd" in payment_methods:
                payment_options.append(f"💳 {payment_methods['usd']}")
            if "robux" in payment_methods:
                payment_options.append(f"🎮 {payment_methods['robux']}")
            
            if payment_options:
                desc_parts.append(" or ".join(payment_options))
            
            if description:
                desc_parts.append(f"• {description}")
            
            full_description = " ".join(desc_parts)[:100]
            
            # Choose emoji and label based on stock and payment methods
            if stock == 0:
                label = f"🔴 {product_name} (SOLD OUT)"
                emoji = "🔴"
                options.append(disnake.SelectOption(
                    label=label[:100],
                    description="This product is currently sold out",
                    value=f"soldout_{product_name}",
                    emoji=emoji
                ))
            else:
                # Determine emoji based on payment methods
                if "usd" in payment_methods and "robux" in payment_methods:
                    emoji = "💎"  # Dual payment
                elif "robux" in payment_methods:
                    emoji = "🎮"  # Robux only
                else:
                    emoji = "💳"  # USD only
                
                stock_indicator = ""
                if stock == -1:
                    stock_indicator = " (Unlimited)"
                elif stock <= 5 and stock > 0:
                    stock_indicator = f" ({stock} left)"
                
                label = f"{product_name}{stock_indicator}"
                
                options.append(disnake.SelectOption(
                    label=label[:100],
                    description=full_description,
                    value=f"product_{product_name}",
                    emoji=emoji
                ))

        options = options[:25]

        if not options:
            await self.create_default_ticket(interaction, "General Support")
            return

        dropdown = disnake.ui.StringSelect(
            placeholder="Select what you need help with...",
            options=options
        )
        dropdown.callback = lambda inter: self.handle_selection(inter, categories, products)

        dropdown_view = disnake.ui.View()
        dropdown_view.add_item(dropdown)

        await safe_followup(
            interaction,
            "🎫 **Create Support Ticket**\nSelect what you need help with:",
            view=dropdown_view,
            ephemeral=True,
            delete_after=config.message_timeout
        )

    async def handle_selection(self, interaction, categories, products):
        """Handle selection with payment method choice for products"""
        selected_value = interaction.data["values"][0]
        
        if selected_value.startswith("soldout_"):
            product_name = selected_value.replace("soldout_", "")
            await interaction.response.send_message(
                f"❌ **{product_name}** is currently sold out and not available for new tickets.\n"
                "Please select a different option.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return
        
        if selected_value.startswith("category_"):
            selected_category = selected_value.replace("category_", "")
            selected_type = "custom"
            selected_name = selected_category
            selected_data = None
            await self.create_ticket(interaction, selected_type, selected_name, selected_data)
        elif selected_value.startswith("product_"):
            selected_product = selected_value.replace("product_", "")
            selected_type = "product"
            selected_name = selected_product
            selected_data = products.get(selected_product)
            
            # Check if product has multiple payment methods
            payment_methods = selected_data.get("payment_methods", {})
            
            if len(payment_methods) > 1:
                # Show payment method selection
                await self.show_payment_method_selection(interaction, selected_name, selected_data, payment_methods)
            else:
                # Single payment method or no payment methods
                payment_method = list(payment_methods.keys())[0] if payment_methods else None
                await self.create_ticket(interaction, selected_type, selected_name, selected_data, payment_method)
        else:
            selected_type = "product"
            selected_name = selected_value
            selected_data = products.get(selected_value)
            await self.create_ticket(interaction, selected_type, selected_name, selected_data)

    async def show_payment_method_selection(self, interaction, product_name, product_data, payment_methods):
        """Show payment method selection for products with multiple payment options"""
        embed = disnake.Embed(
            title=f"💳 Choose Payment Method: {product_name}",
            description="How did you pay for this product? This helps us provide better support.",
            color=disnake.Color.blue()
        )
        
        if product_data.get("description"):
            embed.add_field(name="📄 Product", value=product_data["description"], inline=False)
        
        view = PaymentMethodTicketView(product_name, product_data, payment_methods)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def create_ticket(self, interaction, selected_type, selected_name, selected_data, payment_method=None):
        """Create the actual ticket"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            async with (await get_database_pool()).acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO ticket_counters (guild_id, counter)
                    VALUES ($1, 0)
                    ON CONFLICT (guild_id) DO NOTHING
                    """,
                    str(interaction.guild.id)
                )
                
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

            # Get Discord category for this ticket type
            discord_category = None
            if selected_type == "custom":
                category_id = await get_ticket_discord_category(
                    str(interaction.guild.id), 
                    "custom", 
                    selected_name
                )
            elif selected_type == "product":
                category_id = await get_ticket_discord_category(
                    str(interaction.guild.id), 
                    "product", 
                    selected_name
                )
                
                if not category_id:
                    category_id = await get_ticket_discord_category(
                        str(interaction.guild.id), 
                        "product", 
                        None
                    )
            else:
                category_id = await get_ticket_discord_category(
                    str(interaction.guild.id), 
                    "general", 
                    None
                )

            if category_id:
                discord_category = interaction.guild.get_channel(int(category_id))

            guild = interaction.guild
            user = interaction.author
            
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
            
            if guild.owner:
                overwrites[guild.owner] = disnake.PermissionOverwrite(
                    read_messages=True, 
                    send_messages=True, 
                    manage_messages=True
                )
            
            for member in guild.members:
                if await has_ticket_permission(member, guild) and member != user and member != guild.owner:
                    overwrites[member] = disnake.PermissionOverwrite(
                        read_messages=True, 
                        send_messages=True, 
                        manage_messages=True
                    )

            channel_name = f"ticket-{ticket_number:04d}-{user.display_name.lower().replace(' ', '-')}"
            channel_name = re.sub(r'[^a-z0-9\-]', '', channel_name)
            
            channel = await guild.create_text_channel(
                name=channel_name,
                category=discord_category,
                overwrites=overwrites,
                reason=f"Private ticket created by {user} for {selected_name}"
            )

            product_name_for_db = selected_name if selected_type == "product" else None
            async with (await get_database_pool()).acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO active_tickets (guild_id, channel_id, user_id, product_name, ticket_number)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    str(guild.id), str(channel.id), str(user.id), product_name_for_db, ticket_number
                )

            # Create appropriate embed based on type
            if selected_type == "product" and selected_data:
                embed = await create_product_ticket_embed(
                    user, selected_name, selected_data, ticket_number, discord_category, payment_method
                )
            else:
                # Standard embed for non-product tickets
                embed = disnake.Embed(
                    title=f"🎫 Private Support Ticket #{ticket_number:04d}",
                    description=f"Hello {user.mention}! Welcome to your **private** support ticket for **{selected_name}**.",
                    color=disnake.Color.green()
                )
                embed.add_field(
                    name="📋 Category",
                    value=f"**{selected_name}**",
                    inline=True
                )
                embed.add_field(
                    name="⏰ Created",
                    value=f"<t:{int(time.time())}:F>",
                    inline=True
                )
                embed.add_field(
                    name="📍 Location",
                    value=f"**{discord_category.name}**" if discord_category else "**Default**",
                    inline=True
                )
                embed.add_field(
                    name="📋 Next Steps",
                    value="Please describe your question or issue in detail, and our support team will assist you shortly.",
                    inline=False
                )
                embed.add_field(
                    name="🔒 Privacy Notice",
                    value="This is a **PRIVATE** channel - only you and authorized support staff can see this conversation.",
                    inline=False
                )
                embed.set_footer(text="Use /close_ticket to close this ticket when resolved")
            
            await channel.send(embed=embed)
            
            # Send payment-specific prompts
            if selected_type == "product" and selected_data and payment_method:
                if payment_method == "usd":
                    prompt_embed = disnake.Embed(
                        title="💳 PayHip License Support",
                        description=(
                            f"You selected **PayHip License** support for **{selected_name}**.\n\n"
                            "**To help you faster, please share:**\n"
                            "• Your license key (XXXXX-XXXXX-XXXXX-XXXXX)\n"
                            "• Description of your issue\n\n"
                            "*Your information is only used for support verification.*"
                        ),
                        color=disnake.Color.blue()
                    )
                elif payment_method == "robux":
                    prompt_embed = disnake.Embed(
                        title="🎮 Roblox Gamepass Support",
                        description=(
                            f"You selected **Roblox Gamepass** support for **{selected_name}**.\n\n"
                            "**To help you faster, please share:**\n"
                            "• Your exact Roblox username\n"
                            "• Confirmation that you bought the gamepass\n"
                            "• Description of your issue\n\n"
                            "*We'll manually verify your gamepass purchase.*"
                        ),
                        color=disnake.Color.blue()
                    )
                
                if 'prompt_embed' in locals():
                    await asyncio.sleep(2)
                    await channel.send(embed=prompt_embed)

            logger.info(f"[Private Ticket Created] #{ticket_number:04d} created by {user} for '{selected_name}' ({selected_type}) with payment method: {payment_method} in '{guild.name}' -> {discord_category.name if discord_category else 'Default'}")
            
            await safe_followup(
                interaction,
                f"✅ **Private** ticket created! Check out {channel.mention}",
                ephemeral=True,
                delete_after=config.message_timeout
            )

        except disnake.Forbidden:
            logger.error(f"[Ticket Creation Failed] No permission to create channels in '{interaction.guild.name}'")
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

    async def create_default_ticket(self, interaction, category_name="General Support"):
        """Creates a default ticket when no categories/products exist"""
        try:
            async with (await get_database_pool()).acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO ticket_counters (guild_id, counter)
                    VALUES ($1, 0)
                    ON CONFLICT (guild_id) DO NOTHING
                    """,
                    str(interaction.guild.id)
                )
                
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

            discord_category = None
            category_id = await get_ticket_discord_category(str(interaction.guild.id), "general", None)
            if category_id:
                discord_category = interaction.guild.get_channel(int(category_id))

            guild = interaction.guild
            user = interaction.author
            
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
            
            if guild.owner:
                overwrites[guild.owner] = disnake.PermissionOverwrite(
                    read_messages=True, 
                    send_messages=True, 
                    manage_messages=True
                )
            
            for member in guild.members:
                if await has_ticket_permission(member, guild) and member != user and member != guild.owner:
                    overwrites[member] = disnake.PermissionOverwrite(
                        read_messages=True, 
                        send_messages=True, 
                        manage_messages=True
                    )

            channel_name = f"ticket-{ticket_number:04d}-{user.display_name.lower().replace(' ', '-')}"
            channel_name = re.sub(r'[^a-z0-9\-]', '', channel_name)
            
            channel = await guild.create_text_channel(
                name=channel_name,
                category=discord_category,
                overwrites=overwrites,
                reason=f"Private ticket created by {user} for {category_name}"
            )

            async with (await get_database_pool()).acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO active_tickets (guild_id, channel_id, user_id, product_name, ticket_number)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    str(guild.id), str(channel.id), str(user.id), None, ticket_number
                )

            welcome_embed = disnake.Embed(
                title=f"🎫 Private Support Ticket #{ticket_number:04d}",
                description=(
                    f"Hello {user.mention}! Welcome to your **private** support ticket.\n\n"
                    f"**Category:** {category_name}\n"
                    f"**Created:** <t:{int(time.time())}:F>\n"
                    f"**Location:** {discord_category.name if discord_category else 'Default'}\n\n"
                    "**📋 Next Steps:**\n"
                    "Please describe your question or issue in detail, and our support team will assist you shortly.\n\n"
                    "**🔒 Privacy Notice:**\n"
                    "This is a **PRIVATE** channel - only you and authorized support staff can see this conversation."
                ),
                color=disnake.Color.green()
            )
            welcome_embed.set_footer(text="Use /close_ticket to close this ticket when resolved")

            await channel.send(embed=welcome_embed)

            logger.info(f"[Private Default Ticket] #{ticket_number:04d} created by {user} for {category_name} in '{guild.name}' -> {discord_category.name if discord_category else 'Default'}")
            
            await safe_followup(
                interaction,
                f"✅ **Private** ticket created! Check out {channel.mention}",
                ephemeral=True,
                delete_after=config.message_timeout
            )

        except disnake.Forbidden:
            logger.error(f"[Default Ticket Creation Failed] No permission to create channels in '{interaction.guild.name}'")
            await safe_followup(
                interaction,
                "❌ I don't have permission to create channels. Please contact an administrator.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"[Default Ticket Creation Failed] Error creating ticket for {interaction.author}: {e}")
            await safe_followup(
                interaction,
                "❌ Failed to create ticket. Please try again later.",
                ephemeral=True
            )

class PaymentMethodTicketView(disnake.ui.View):
    def __init__(self, product_name, product_data, payment_methods):
        super().__init__(timeout=180)
        self.product_name = product_name
        self.product_data = product_data
        self.payment_methods = payment_methods
        
        # Add buttons for each payment method
        if "usd" in payment_methods:
            usd_button = disnake.ui.Button(
                label=f"💳 PayHip - {payment_methods['usd']}",
                style=disnake.ButtonStyle.primary,
                emoji="💳"
            )
            usd_button.callback = self.select_usd_payment
            self.add_item(usd_button)
        
        if "robux" in payment_methods:
            robux_button = disnake.ui.Button(
                label=f"🎮 Roblox - {payment_methods['robux']}",
                style=disnake.ButtonStyle.primary,
                emoji="🎮"
            )
            robux_button.callback = self.select_robux_payment
            self.add_item(robux_button)

    async def select_usd_payment(self, interaction):
        # Get the ticket button instance from the original view
        ticket_button = TicketButton(str(interaction.guild.id))
        await ticket_button.create_ticket(interaction, "product", self.product_name, self.product_data, "usd")

    async def select_robux_payment(self, interaction):
        # Get the ticket button instance from the original view
        ticket_button = TicketButton(str(interaction.guild.id))
        await ticket_button.create_ticket(interaction, "product", self.product_name, self.product_data, "robux")
