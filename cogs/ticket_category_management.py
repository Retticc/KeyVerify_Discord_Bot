import disnake
from disnake.ext import commands
from utils.database import get_database_pool
from utils.permissions import owner_or_permission
import config
import logging

logger = logging.getLogger(__name__)

class TicketCategoryManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.setup_table())
        
    async def setup_table(self):
        """Creates table for storing Discord category assignments"""
        await self.bot.wait_until_ready()
        async with (await get_database_pool()).acquire() as conn:
            # Table for mapping ticket types to Discord categories
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_discord_categories (
                    guild_id TEXT NOT NULL,
                    ticket_type TEXT NOT NULL,
                    category_name TEXT,
                    discord_category_id TEXT NOT NULL,
                    PRIMARY KEY (guild_id, ticket_type, COALESCE(category_name, ''))
                );
            """)

    @commands.slash_command(
        description="Set Discord categories for different ticket types (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @owner_or_permission("manage_categories")
    async def set_ticket_discord_categories(self, inter: disnake.ApplicationCommandInteraction):
        """Set which Discord category each ticket type goes into"""
        # Get Discord categories
        categories = inter.guild.categories
        if not categories:
            await inter.response.send_message(
                "❌ No Discord categories found. Create some categories first using Discord's interface.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        embed = disnake.Embed(
            title="🏷️ Set Ticket Categories",
            description="Choose what type of tickets you want to organize:",
            color=disnake.Color.blue()
        )

        class TicketTypeView(disnake.ui.View):
            def __init__(self):
                super().__init__(timeout=180)

            @disnake.ui.button(label="🎫 General Support", style=disnake.ButtonStyle.secondary, emoji="🎫")
            async def general_support(self, button, button_inter):
                await self.show_category_selection(button_inter, "general", "General Support Tickets")

            @disnake.ui.button(label="🎁 All Product Tickets", style=disnake.ButtonStyle.secondary, emoji="🎁")
            async def all_product_tickets(self, button, button_inter):
                await self.show_category_selection(button_inter, "product", "All Product Tickets")

            @disnake.ui.button(label="🔧 Specific Products", style=disnake.ButtonStyle.secondary, emoji="🔧")
            async def specific_products(self, button, button_inter):
                await self.show_product_selection(button_inter)

            @disnake.ui.button(label="📋 Custom Categories", style=disnake.ButtonStyle.secondary, emoji="📋")
            async def custom_categories(self, button, button_inter):
                await self.show_custom_category_selection(button_inter)

            @disnake.ui.button(label="🔍 View Current Settings", style=disnake.ButtonStyle.primary, emoji="🔍")
            async def view_settings(self, button, button_inter):
                await self.show_current_settings(button_inter)

            async def show_category_selection(self, button_inter, ticket_type, description, category_name=None):
                """Show Discord category selection dropdown"""
                category_options = [
                    disnake.SelectOption(
                        label=f"📁 {category.name}", 
                        value=str(category.id),
                        description=f"{len(category.channels)} channels"
                    )
                    for category in inter.guild.categories
                ][:24]  # Leave room for default option
                
                # Add option to remove category assignment
                category_options.insert(0, disnake.SelectOption(
                    label="🏠 Default Location", 
                    value="none",
                    description="Remove category assignment - use default location"
                ))

                dropdown = disnake.ui.StringSelect(
                    placeholder=f"Select Discord category for {description}...",
                    options=category_options
                )
                
                async def category_selected(select_inter):
                    selected_category_id = select_inter.data["values"][0]
                    
                    async with (await get_database_pool()).acquire() as conn:
                        if selected_category_id == "none":
                            # Remove category assignment
                            if category_name:
                                await conn.execute(
                                    "DELETE FROM ticket_discord_categories WHERE guild_id = $1 AND ticket_type = $2 AND category_name = $3",
                                    str(inter.guild.id), ticket_type, category_name
                                )
                            else:
                                await conn.execute(
                                    "DELETE FROM ticket_discord_categories WHERE guild_id = $1 AND ticket_type = $2 AND category_name IS NULL",
                                    str(inter.guild.id), ticket_type
                                )
                            await select_inter.response.send_message(
                                f"✅ {description} will now use the default location.",
                                ephemeral=True
                            )
                        else:
                            selected_category = inter.guild.get_channel(int(selected_category_id))
                            if category_name:
                                await conn.execute(
                                    """
                                    INSERT INTO ticket_discord_categories (guild_id, ticket_type, category_name, discord_category_id)
                                    VALUES ($1, $2, $3, $4)
                                    ON CONFLICT (guild_id, ticket_type, category_name)
                                    DO UPDATE SET discord_category_id = $4
                                    """,
                                    str(inter.guild.id), ticket_type, category_name, str(selected_category.id)
                                )
                            else:
                                await conn.execute(
                                    """
                                    INSERT INTO ticket_discord_categories (guild_id, ticket_type, discord_category_id)
                                    VALUES ($1, $2, $3)
                                    ON CONFLICT (guild_id, ticket_type, category_name)
                                    DO UPDATE SET discord_category_id = $3
                                    """,
                                    str(inter.guild.id), ticket_type, str(selected_category.id)
                                )
                            await select_inter.response.send_message(
                                f"✅ {description} will now be created in **📁 {selected_category.name}**",
                                ephemeral=True
                            )

                dropdown.callback = category_selected
                view = disnake.ui.View()
                view.add_item(dropdown)

                await button_inter.response.send_message(
                    f"**Setting category for:** {description}\n\nSelect which Discord category these tickets should be created in:",
                    view=view,
                    ephemeral=True
                )

            async def show_product_selection(self, button_inter):
                """Show product selection for category assignment"""
                from utils.database import fetch_products
                products = await fetch_products(str(inter.guild.id))
                
                if not products:
                    await button_inter.response.send_message(
                        "❌ No products found. Add products first with `/add_product`.",
                        ephemeral=True
                    )
                    return

                product_options = [
                    disnake.SelectOption(
                        label=product_name, 
                        value=product_name,
                        description=f"Set category for {product_name} tickets"
                    )
                    for product_name in products.keys()
                ][:25]

                dropdown = disnake.ui.StringSelect(
                    placeholder="Select a product to set its ticket category...",
                    options=product_options
                )
                
                async def product_selected(select_inter):
                    product_name = select_inter.data["values"][0]
                    await self.show_category_selection(
                        select_inter, 
                        "product", 
                        f"{product_name} Tickets",
                        product_name
                    )

                dropdown.callback = product_selected
                view = disnake.ui.View()
                view.add_item(dropdown)

                await button_inter.response.send_message(
                    "**🎁 Product-Specific Ticket Categories**\n\nSelect which product you want to set a category for:",
                    view=view,
                    ephemeral=True
                )

            async def show_custom_category_selection(self, button_inter):
                """Show custom ticket category selection"""
                async with (await get_database_pool()).acquire() as conn:
                    custom_categories = await conn.fetch(
                        "SELECT category_name FROM ticket_categories WHERE guild_id = $1 ORDER BY display_order",
                        str(inter.guild.id)
                    )

                if not custom_categories:
                    await button_inter.response.send_message(
                        "❌ No custom ticket categories found. Use `/add_ticket_category` to create some first.",
                        ephemeral=True
                    )
                    return

                category_options = [
                    disnake.SelectOption(
                        label=cat["category_name"], 
                        value=cat["category_name"],
                        description=f"Set Discord category for {cat['category_name']}"
                    )
                    for cat in custom_categories
                ][:25]

                dropdown = disnake.ui.StringSelect(
                    placeholder="Select a custom ticket category...",
                    options=category_options
                )
                
                async def custom_category_selected(select_inter):
                    category_name = select_inter.data["values"][0]
                    await self.show_category_selection(
                        select_inter, 
                        "custom", 
                        f"{category_name} Tickets",
                        category_name
                    )

                dropdown.callback = custom_category_selected
                view = disnake.ui.View()
                view.add_item(dropdown)

                await button_inter.response.send_message(
                    "**📋 Custom Ticket Categories**\n\nSelect which custom category you want to assign a Discord category to:",
                    view=view,
                    ephemeral=True
                )

            async def show_current_settings(self, button_inter):
                """Show current category assignments"""
                async with (await get_database_pool()).acquire() as conn:
                    assignments = await conn.fetch(
                        "SELECT ticket_type, category_name, discord_category_id FROM ticket_discord_categories WHERE guild_id = $1 ORDER BY ticket_type",
                        str(inter.guild.id)
                    )

                if not assignments:
                    await button_inter.response.send_message(
                        "📋 No ticket category assignments found. All tickets will use the default location.",
                        ephemeral=True
                    )
                    return

                embed = disnake.Embed(
                    title="🏷️ Current Ticket Category Settings",
                    color=disnake.Color.blue()
                )

                for assignment in assignments:
                    ticket_type = assignment["ticket_type"]
                    category_name = assignment["category_name"]
                    discord_category_id = assignment["discord_category_id"]
                    discord_category = inter.guild.get_channel(int(discord_category_id))
                    
                    if ticket_type == "general":
                        field_name = "🎫 General Support"
                    elif ticket_type == "product" and not category_name:
                        field_name = "🎁 All Product Tickets"
                    elif ticket_type == "product" and category_name:
                        field_name = f"🔧 {category_name} Product"
                    elif ticket_type == "custom":
                        field_name = f"📋 {category_name}"
                    else:
                        field_name = f"❓ {ticket_type}"
                    
                    field_value = f"📁 {discord_category.name}" if discord_category else "❌ Category not found"
                    
                    embed.add_field(
                        name=field_name,
                        value=field_value,
                        inline=True
                    )

                embed.set_footer(text="Use the buttons above to modify these settings")
                await button_inter.response.send_message(embed=embed, ephemeral=True)

        view = TicketTypeView()
        await inter.response.send_message(embed=embed, view=view, ephemeral=True)

    @commands.slash_command(
        description="Remove Discord category assignments (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @owner_or_permission("manage_categories")
    async def remove_ticket_category_assign(self, inter: disnake.ApplicationCommandInteraction):
        """Remove Discord category assignments"""
        async with (await get_database_pool()).acquire() as conn:
            assignments = await conn.fetch(
                "SELECT ticket_type, category_name, discord_category_id FROM ticket_discord_categories WHERE guild_id = $1",
                str(inter.guild.id)
            )

        if not assignments:
            await inter.response.send_message(
                "❌ No ticket category assignments found.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        options = []
        for assignment in assignments:
            ticket_type = assignment["ticket_type"]
            category_name = assignment["category_name"]
            discord_category_id = assignment["discord_category_id"]
            discord_category = inter.guild.get_channel(int(discord_category_id))
            
            if ticket_type == "general":
                label = "🎫 General Support"
            elif ticket_type == "product" and not category_name:
                label = "🎁 All Product Tickets"
            elif ticket_type == "product" and category_name:
                label = f"🔧 {category_name}"
            elif ticket_type == "custom":
                label = f"📋 {category_name}"
            else:
                label = f"❓ {ticket_type}"
            
            description = f"Currently in: {discord_category.name if discord_category else 'Category not found'}"
            value = f"{ticket_type}:{category_name or ''}"
            
            options.append(disnake.SelectOption(
                label=label[:100],
                description=description[:100],
                value=value
            ))

        dropdown = disnake.ui.StringSelect(
            placeholder="Select assignment to remove...",
            options=options[:25]  # Discord limit
        )
        
        async def assignment_selected(select_inter):
            selected_value = select_inter.data["values"][0]
            ticket_type, category_name = selected_value.split(":", 1)
            category_name = category_name if category_name else None
            
            class ConfirmRemoveView(disnake.ui.View):
                def __init__(self):
                    super().__init__(timeout=30)

                @disnake.ui.button(label="✅ Confirm Remove", style=disnake.ButtonStyle.danger)
                async def confirm(self, button, button_inter):
                    async with (await get_database_pool()).acquire() as conn:
                        if category_name:
                            await conn.execute(
                                "DELETE FROM ticket_discord_categories WHERE guild_id = $1 AND ticket_type = $2 AND category_name = $3",
                                str(inter.guild.id), ticket_type, category_name
                            )
                        else:
                            await conn.execute(
                                "DELETE FROM ticket_discord_categories WHERE guild_id = $1 AND ticket_type = $2 AND category_name IS NULL",
                                str(inter.guild.id), ticket_type
                            )
                    
                    await button_inter.response.send_message(
                        "✅ Category assignment removed. Tickets will now use the default location.",
                        ephemeral=True
                    )
                    self.stop()

                @disnake.ui.button(label="❌ Cancel", style=disnake.ButtonStyle.secondary)
                async def cancel(self, button, button_inter):
                    await button_inter.response.send_message("Removal cancelled.", ephemeral=True)
                    self.stop()
            
            view = ConfirmRemoveView()
            await select_inter.response.send_message(
                "⚠️ Are you sure you want to remove this category assignment?",
                view=view,
                ephemeral=True
            )

        dropdown.callback = assignment_selected
        view = disnake.ui.View()
        view.add_item(dropdown)

        await inter.response.send_message(
            "🗑️ **Remove Category Assignment**\n\nSelect which assignment to remove:",
            view=view,
            ephemeral=True,
            delete_after=config.message_timeout
        )

# Utility function to get the Discord category for a ticket type
async def get_ticket_discord_category(guild_id, ticket_type, category_name=None):
    """Get the Discord category ID for a specific ticket type"""
    async with (await get_database_pool()).acquire() as conn:
        if category_name:
            # Product or custom category specific
            result = await conn.fetchrow(
                "SELECT discord_category_id FROM ticket_discord_categories WHERE guild_id = $1 AND ticket_type = $2 AND category_name = $3",
                guild_id, ticket_type, category_name
            )
        else:
            # General ticket type
            result = await conn.fetchrow(
                "SELECT discord_category_id FROM ticket_discord_categories WHERE guild_id = $1 AND ticket_type = $2 AND category_name IS NULL",
                guild_id, ticket_type
            )
    
    return result["discord_category_id"] if result else None

def setup(bot):
    bot.add_cog(TicketCategoryManagement(bot))
