# Replace cogs/ticket_system.py with this complete fixed version

import disnake
from disnake.ext import commands

from utils.database import get_database_pool, fetch_products
from handlers.ticket_handler import create_ticket_embed, create_ticket_view, fetch_ticket_categories
import config
import logging
import asyncio

logger = logging.getLogger(__name__)


class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        description="Create a ticket system box for users to create support tickets (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def create_ticket_box(self, inter: disnake.ApplicationCommandInteraction):
        """Creates a ticket box that users can interact with to create support tickets"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can use this command.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Check if there are any categories or products (allow creation even if neither exist)
        async with (await get_database_pool()).acquire() as conn:
            categories = await conn.fetch(
                "SELECT category_name FROM ticket_categories WHERE guild_id = $1",
                str(inter.guild.id)
            )
            products = await fetch_products(str(inter.guild.id))

        # Create embed with custom text support
        embed = await create_ticket_embed(inter.guild)
        view = create_ticket_view(str(inter.guild.id))

        # Add a note if no categories or products are configured
        if not categories and not products:
            embed.description += (
                "\n\n⚠️ *Note: No categories or products are configured yet. "
                "Use /add_ticket_category or /add_product to add options.*"
            )

        # Setup button with custom settings
        await view.setup_button(inter.guild)

        try:
            message = await inter.channel.send(embed=embed, view=view)
        except disnake.Forbidden:
            await inter.response.send_message(
                "❌ I don't have permission to send messages in this channel. "
                "Please make sure I have the **Send Messages** and **Embed Links** permissions.",
                ephemeral=True
            )
            return

        # Store the ticket box in the database
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute(
                """INSERT INTO ticket_boxes (guild_id, message_id, channel_id) VALUES ($1, $2, $3)""",
                str(inter.guild.id), str(message.id), str(inter.channel.id)
            )

        logger.info(
            f"[Ticket Box Created] {inter.author} created a ticket box in '{inter.guild.name}'"
        )

        success_msg = "✅ Ticket box created successfully!"
        if not categories and not products:
            success_msg += (
                "\n💡 **Tip:** Add categories with /add_ticket_category or products with /add_product "
                "to give users ticket options."
            )
        else:
            success_msg += (
                "\n💡 **Tip:** Use /customize_ticket_box to personalize the text and /ticket_variables "
                "to see available variables."
            )

        await inter.response.send_message(
            success_msg,
            ephemeral=True,
            delete_after=config.message_timeout
        )

    @commands.slash_command(
        description="Update all existing ticket boxes with new customization (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def update_ticket_boxes(self, inter: disnake.ApplicationCommandInteraction):
        """Updates all existing ticket boxes in the server"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can update ticket boxes.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        await inter.response.defer(ephemeral=True)

        # Get all ticket boxes in this guild
        async with (await get_database_pool()).acquire() as conn:
            boxes = await conn.fetch(
                "SELECT message_id, channel_id FROM ticket_boxes WHERE guild_id = $1",
                str(inter.guild.id)
            )

        if not boxes:
            await inter.followup.send(
                "❌ No ticket boxes found in this server.",
                ephemeral=True
            )
            return

        updated_count = 0
        failed_count = 0

        # Create new embed and view
        embed = await create_ticket_embed(inter.guild)

        for box in boxes:
            try:
                channel = inter.guild.get_channel(int(box["channel_id"]))
                if not channel:
                    continue

                message = await channel.fetch_message(int(box["message_id"]))
                view = create_ticket_view(str(inter.guild.id))
                await view.setup_button(inter.guild)
                await message.edit(embed=embed, view=view)
                updated_count += 1

            except (disnake.NotFound, disnake.Forbidden):
                failed_count += 1
                # Clean up stale records
                async with (await get_database_pool()).acquire() as conn:
                    await conn.execute(
                        "DELETE FROM ticket_boxes WHERE guild_id = $1 AND message_id = $2",
                        str(inter.guild.id), box["message_id"]
                    )

        result_msg = f"✅ Updated {updated_count} ticket box(es)."
        if failed_count > 0:
            result_msg += f"\n⚠️ {failed_count} box(es) could not be updated (deleted or no permissions)."

        await inter.followup.send(result_msg, ephemeral=True)

    @commands.slash_command(
        description="Close the current ticket channel (server owner/moderators only).",
        default_member_permissions=disnake.Permissions(manage_channels=True),
    )
    async def close_ticket(self, inter: disnake.ApplicationCommandInteraction):
        """Closes an active ticket channel"""
        async with (await get_database_pool()).acquire() as conn:
            ticket = await conn.fetchrow(
                "SELECT user_id, product_name, ticket_number FROM active_tickets WHERE guild_id = $1 AND channel_id = $2",
                str(inter.guild.id), str(inter.channel.id)
            )

        if not ticket:
            await inter.response.send_message(
                "❌ This is not a ticket channel.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Create confirmation embed
        user = inter.guild.get_member(int(ticket["user_id"]))
        user_display = user.display_name if user else "Unknown User"

        embed = disnake.Embed(
            title="🔒 Close Ticket",
            description=(
                f"Are you sure you want to close this ticket?\n\n"
                f"**User:** {user_display}\n"
                f"**Product:** {ticket['product_name'] or 'Not specified'}\n"
                f"**Ticket #:** {ticket['ticket_number']}"
            ),
            color=disnake.Color.red()
        )

        class ConfirmCloseView(disnake.ui.View):
            def __init__(self):
                super().__init__(timeout=30)

            @disnake.ui.button(label="✅ Close Ticket", style=disnake.ButtonStyle.danger)
            async def confirm_close(self, button: disnake.ui.Button, button_inter: disnake.MessageInteraction):
                try:
                    # Remove from database
                    async with (await get_database_pool()).acquire() as conn:
                        await conn.execute(
                            "DELETE FROM active_tickets WHERE guild_id = $1 AND channel_id = $2",
                            str(inter.guild.id), str(inter.channel.id)
                        )

                    await button_inter.response.send_message(
                    f"**Setting category for:** {description}\n\nSelect which Discord category these tickets should be created in:",
                    view=view,
                    ephemeral=True
                )

            async def show_product_selection(self, button_inter):
                """Show product selection for category assignment"""
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
                        description=f"Set Discord category for {product_name} tickets"
                    )
                    for product_name in products.keys()
                ][:25]

                dropdown = disnake.ui.StringSelect(
                    placeholder="Select a product to set its ticket Discord category...",
                    options=product_options
                )
                
                async def product_selected(select_inter):
                    product_name = select_inter.data["values"][0]
                    await self.show_category_selection(
                        select_inter, 
                        "product", 
                        f"{product_name} Product Tickets",
                        product_name
                    )

                dropdown.callback = product_selected
                view = disnake.ui.View()
                view.add_item(dropdown)

                await button_inter.response.send_message(
                    "**🎁 Product-Specific Discord Categories**\n\nSelect which product you want to set a Discord category for:",
                    view=view,
                    ephemeral=True
                )

            async def show_custom_category_selection(self, button_inter):
                """Show custom ticket category selection"""
                custom_categories = await fetch_ticket_categories(str(inter.guild.id))

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
                        f"{category_name} Custom Tickets",
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
                        "📋 No ticket Discord category assignments found. All tickets will use the default location.",
                        ephemeral=True
                    )
                    return

                embed = disnake.Embed(
                    title="🏷️ Current Ticket Discord Category Settings",
                    color=disnake.Color.blue()
                )

                for assignment in assignments:
                    ticket_type = assignment["ticket_type"]
                    category_name = assignment["category_name"]
                    discord_category_id = assignment["discord_category_id"]
                    discord_category = inter.guild.get_channel(int(discord_category_id))
                    
                    if ticket_type == "general" and not category_name:
                        field_name = "🎫 General Support"
                    elif ticket_type == "product" and not category_name:
                        field_name = "🎁 All Product Tickets"
                    elif ticket_type == "product" and category_name:
                        field_name = f"🔧 {category_name} Product"
                    elif ticket_type == "custom":
                        field_name = f"📋 {category_name} Custom"
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
        description="View current ticket Discord category assignments (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def view_ticket_discord_categories(self, inter: disnake.ApplicationCommandInteraction):
        """View current ticket Discord category assignments"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can view ticket Discord category settings.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            assignments = await conn.fetch(
                """
                SELECT ticket_type, category_name, discord_category_id 
                FROM ticket_discord_categories 
                WHERE guild_id = $1
                ORDER BY ticket_type, category_name
                """,
                str(inter.guild.id)
            )

        if not assignments:
            await inter.response.send_message(
                "❌ No ticket Discord category assignments found. Use `/set_ticket_discord_categories` to set them up.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        embed = disnake.Embed(
            title="🎫 Current Ticket Discord Category Assignments",
            description="Current Discord category assignments for ticket types:",
            color=disnake.Color.blue()
        )

        for assignment in assignments:
            ticket_type = assignment["ticket_type"]
            category_name = assignment["category_name"]
            discord_category_id = assignment["discord_category_id"]
            discord_category = inter.guild.get_channel(int(discord_category_id))
            
            if ticket_type == "general" and not category_name:
                label = "🎫 General Support"
            elif ticket_type == "product" and not category_name:
                label = "🎁 All Product Tickets"
            elif ticket_type == "product" and category_name:
                label = f"🔧 {category_name} Product"
            elif ticket_type == "custom":
                label = f"📋 {category_name} Custom"
            else:
                label = f"❓ {ticket_type}"
            
            description = f"📁 {discord_category.name}" if discord_category else "❌ Category not found"
            
            embed.add_field(
                name=label,
                value=description,
                inline=True
            )

        embed.set_footer(text="Use /set_ticket_discord_categories to modify assignments")
        
        await inter.response.send_message(embed=embed, ephemeral=True)


def setup(bot):
    bot.add_cog(TicketSystem(bot)).send_message("🔒 Ticket will be deleted in 5 seconds...")
                    await asyncio.sleep(5)
                    await inter.channel.delete()

                    logger.info(
                        f"[Ticket Closed] Ticket #{ticket['ticket_number']} closed by {button_inter.author} in '{inter.guild.name}'"
                    )

                except disnake.Forbidden:
                    await button_inter.response.send_message(
                        "❌ I don't have permission to delete this channel.",
                        ephemeral=True
                    )

                self.stop()

            @disnake.ui.button(label="❌ Cancel", style=disnake.ButtonStyle.secondary)
            async def cancel_close(self, button: disnake.ui.Button, button_inter: disnake.MessageInteraction):
                await button_inter.response.send_message("Ticket closure cancelled.", ephemeral=True)
                self.stop()

        view = ConfirmCloseView()
        await inter.response.send_message(embed=embed, view=view, ephemeral=True)

    @commands.slash_command(
        description="Set Discord categories for different ticket types (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def set_ticket_discord_categories(self, inter: disnake.ApplicationCommandInteraction):
        """Set which Discord category each ticket type goes into"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can set ticket Discord categories.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

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
            title="🏷️ Set Ticket Discord Categories",
            description="Choose what type of tickets you want to organize into Discord categories:",
            color=disnake.Color.blue()
        )

        class TicketTypeView(disnake.ui.View):
            def __init__(self):
                super().__init__(timeout=180)

            @disnake.ui.button(label="🎫 General Support", style=disnake.ButtonStyle.secondary, emoji="🎫")
            async def general_support(self, button, button_inter):
                await self.show_category_selection(button_inter, "general", "General Support Tickets", None)

            @disnake.ui.button(label="🎁 All Product Tickets", style=disnake.ButtonStyle.secondary, emoji="🎁")
            async def all_product_tickets(self, button, button_inter):
                await self.show_category_selection(button_inter, "product", "All Product Tickets", None)

            @disnake.ui.button(label="🔧 Specific Products", style=disnake.ButtonStyle.secondary, emoji="🔧")
            async def specific_products(self, button, button_inter):
                await self.show_product_selection(button_inter)

            @disnake.ui.button(label="📋 Custom Categories", style=disnake.ButtonStyle.secondary, emoji="📋")
            async def custom_categories(self, button, button_inter):
                await self.show_custom_category_selection(button_inter)

            @disnake.ui.button(label="🔍 View Current Settings", style=disnake.ButtonStyle.primary, emoji="🔍")
            async def view_settings(self, button, button_inter):
                await self.show_current_settings(button_inter)

            async def show_category_selection(self, button_inter, ticket_type, description, category_name):
                """Show Discord category selection dropdown"""
                category_options = []
                
                # Add option to remove category assignment
                category_options.append(disnake.SelectOption(
                    label="🏠 Default Location", 
                    value="none",
                    description="Remove category assignment - use default location"
                ))
                
                # Add Discord categories
                for category in inter.guild.categories:
                    category_options.append(disnake.SelectOption(
                        label=f"📁 {category.name}", 
                        value=str(category.id),
                        description=f"{len(category.channels)} channels"
                    ))
                
                # Limit to Discord's max
                category_options = category_options[:25]

                dropdown = disnake.ui.StringSelect(
                    placeholder=f"Select Discord category for {description}...",
                    options=category_options
                )
                
                async def category_selected(select_inter):
                    selected_category_id = select_inter.data["values"][0]
                    
                    async with (await get_database_pool()).acquire() as conn:
                        if selected_category_id == "none":
                            # Remove category assignment
                            category_name_val = category_name if category_name else ''
                            await conn.execute(
                                "DELETE FROM ticket_discord_categories WHERE guild_id = $1 AND ticket_type = $2 AND category_name = $3",
                                str(inter.guild.id), ticket_type, category_name_val
                            )
                            await select_inter.response.send_message(
                                f"✅ {description} will now use the default location.",
                                ephemeral=True
                            )
                        else:
                            selected_category = inter.guild.get_channel(int(selected_category_id))
                            category_name_val = category_name if category_name else ''
                            
                            await conn.execute(
                                """
                                INSERT INTO ticket_discord_categories (guild_id, ticket_type, category_name, discord_category_id)
                                VALUES ($1, $2, $3, $4)
                                ON CONFLICT (guild_id, ticket_type, category_name)
                                DO UPDATE SET discord_category_id = $4
                                """,
                                str(inter.guild.id), ticket_type, category_name_val, str(selected_category.id)
                            )
                            await select_inter.response.send_message(
                                f"✅ {description} will now be created in **📁 {selected_category.name}**",
                                ephemeral=True
                            )

                dropdown.callback = category_selected
                view = disnake.ui.View()
                view.add_item(dropdown)

                await button_inter.response
