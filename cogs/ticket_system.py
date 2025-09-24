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
        # Schedule the database table creation as a background task after the bot is ready
        self.bot.loop.create_task(self.setup_table())

    async def setup_table(self):
        """Ensures the required tables exist for storing ticket data"""
        await self.bot.wait_until_ready()
        async with (await get_database_pool()).acquire() as conn:
            # Table for tracking ticket boxes
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_boxes (
                    guild_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    PRIMARY KEY (guild_id, message_id)
                );
            """)

            # Table for tracking active tickets
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS active_tickets (
                    guild_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    product_name TEXT,
                    ticket_number INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, channel_id)
                );
            """)

            # Table for ticket counter per guild
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_counters (
                    guild_id TEXT PRIMARY KEY,
                    counter INTEGER DEFAULT 0
                );
            """)

            # Table for custom ticket categories
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_categories (
                    guild_id TEXT NOT NULL,
                    category_name TEXT NOT NULL,
                    category_description TEXT NOT NULL,
                    emoji TEXT DEFAULT '🎫',
                    display_order INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, category_name)
                );
            """)

            # Table for ticket category to Discord category mapping
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_category_channels (
                    guild_id TEXT NOT NULL,
                    category_name TEXT NOT NULL,
                    discord_category_id TEXT NOT NULL,
                    PRIMARY KEY (guild_id, category_name)
                );
            """)

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

                    await button_inter.response.send_message("🔒 Ticket will be deleted in 5 seconds...")
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
        description="Add a custom ticket category.",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def add_ticket_category(
        self, 
        inter: disnake.ApplicationCommandInteraction,
        name: str = commands.Param(description="Category name (e.g., 'General Support')"),
        description: str = commands.Param(description="Category description shown in dropdown"),
        emoji: str = commands.Param(description="Emoji for this category", default="🎫")
    ):
        """Add a custom ticket category"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can add ticket categories.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Check if category already exists
        async with (await get_database_pool()).acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT 1 FROM ticket_categories WHERE guild_id = $1 AND category_name = $2",
                str(inter.guild.id), name
            )
            
            if existing:
                await inter.response.send_message(
                    f"❌ Category **{name}** already exists.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

            # Get next display order
            max_order = await conn.fetchval(
                "SELECT COALESCE(MAX(display_order), 0) FROM ticket_categories WHERE guild_id = $1",
                str(inter.guild.id)
            )
            
            # Add the category
            await conn.execute(
                """
                INSERT INTO ticket_categories (guild_id, category_name, category_description, emoji, display_order)
                VALUES ($1, $2, $3, $4, $5)
                """,
                str(inter.guild.id), name, description, emoji, max_order + 1
            )

        embed = disnake.Embed(
            title="✅ Ticket Category Added",
            description=f"**{emoji} {name}** has been added to your ticket system.",
            color=disnake.Color.green()
        )
        embed.add_field(name="Description", value=description, inline=False)
        embed.add_field(name="Emoji", value=emoji, inline=True)
        embed.set_footer(text="Users can now select this category when creating tickets")

        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.slash_command(
        description="Remove a custom ticket category.",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def remove_ticket_category(self, inter: disnake.ApplicationCommandInteraction):
        """Remove a custom ticket category"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can remove ticket categories.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Get existing categories
        categories = await fetch_ticket_categories(str(inter.guild.id))

        if not categories:
            await inter.response.send_message(
                "❌ No custom ticket categories found.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Create dropdown for categories to remove
        options = [
            disnake.SelectOption(
                label=cat["category_name"],
                value=cat["category_name"],
                description=cat["category_description"][:100],
                emoji=cat["emoji"]
            )
            for cat in categories
        ]

        dropdown = disnake.ui.StringSelect(
            placeholder="Select category to remove...",
            options=options
        )
        
        async def category_selected(select_inter):
            category_name = select_inter.data["values"][0]
            
            async with (await get_database_pool()).acquire() as conn:
                # Remove the category
                await conn.execute(
                    "DELETE FROM ticket_categories WHERE guild_id = $1 AND category_name = $2",
                    str(inter.guild.id), category_name
                )
                
                # Also remove any Discord category assignments
                await conn.execute(
                    "DELETE FROM ticket_category_channels WHERE guild_id = $1 AND category_name = $2",
                    str(inter.guild.id), category_name
                )
            
            await select_inter.response.send_message(
                f"✅ Removed ticket category **{category_name}** and its Discord category assignment.",
                ephemeral=True
            )
        
        dropdown.callback = category_selected
        
        view = disnake.ui.View()
        view.add_item(dropdown)
        
        await inter.response.send_message(
            "**🗑️ Remove Ticket Category**\n\nSelect which category to remove:",
            view=view,
            ephemeral=True
        )

    @commands.slash_command(
        description="List all custom ticket categories.",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def list_ticket_categories(self, inter: disnake.ApplicationCommandInteraction):
        """List all custom ticket categories"""
        categories = await fetch_ticket_categories(str(inter.guild.id))
        
        if not categories:
            await inter.response.send_message(
                "❌ No custom ticket categories found. Use `/add_ticket_category` to create some.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        embed = disnake.Embed(
            title="🎫 Custom Ticket Categories",
            description=f"Found {len(categories)} custom categories:",
            color=disnake.Color.blue()
        )

        for i, category in enumerate(categories, 1):
            embed.add_field(
                name=f"{i}. {category['emoji']} {category['category_name']}",
                value=category['category_description'],
                inline=False
            )

        embed.set_footer(text="Use /set_ticket_discord_categories to assign Discord categories")
        
        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.slash_command(
        description="Set Discord categories for ticket types (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def set_ticket_discord_categories(self, inter: disnake.ApplicationCommandInteraction):
        """Set which Discord category each ticket type goes into"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can set ticket categories.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Get custom ticket categories
        categories = await fetch_ticket_categories(str(inter.guild.id))
        
        if not categories:
            await inter.response.send_message(
                "❌ No custom ticket categories found. Use `/add_ticket_category` first.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Create dropdown for ticket categories
        options = [
            disnake.SelectOption(
                label=cat["category_name"], 
                value=cat["category_name"],
                description=f"Set Discord category for {cat['category_name']}"
            )
            for cat in categories
        ]

        dropdown = disnake.ui.StringSelect(
            placeholder="Select ticket category to assign Discord category...",
            options=options
        )
        
        async def category_selected(select_inter):
            ticket_category = select_inter.data["values"][0]
            
            # Get Discord categories
            discord_categories = [
                disnake.SelectOption(
                    label=f"📁 {category.name}", 
                    value=str(category.id),
                    description=f"{len(category.channels)} channels"
                )
                for category in inter.guild.categories
            ][:25]
            
            if not discord_categories:
                await select_inter.response.send_message(
                    "❌ No Discord categories found. Create some categories first.",
                    ephemeral=True
                )
                return
            
            discord_dropdown = disnake.ui.StringSelect(
                placeholder="Select Discord category...",
                options=discord_categories
            )
            
            async def discord_category_selected(dc_inter):
                discord_category_id = dc_inter.data["values"][0]
                discord_category = inter.guild.get_channel(int(discord_category_id))
                
                async with (await get_database_pool()).acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO ticket_category_channels (guild_id, category_name, discord_category_id)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (guild_id, category_name)
                        DO UPDATE SET discord_category_id = $3
                        """,
                        str(inter.guild.id), ticket_category, discord_category_id
                    )
                
                await dc_inter.response.send_message(
                    f"✅ **{ticket_category}** tickets will now be created in **📁 {discord_category.name}**",
                    ephemeral=True
                )
            
            discord_dropdown.callback = discord_category_selected
            
            # Create view for Discord category selection
            discord_view = disnake.ui.View()
            discord_view.add_item(discord_dropdown)
            
            await select_inter.response.send_message(
                f"**Setting Discord category for:** {ticket_category}\n\nSelect which Discord category these tickets should be created in:",
                view=discord_view,
                ephemeral=True
            )
        
        dropdown.callback = category_selected
        
        # Create view for ticket category selection
        view = disnake.ui.View()
        view.add_item(dropdown)
        
        await inter.response.send_message(
            "**🔧 Set Discord Categories for Tickets**\n\nSelect which ticket category you want to assign a Discord category to:",
            view=view,
            ephemeral=True
        )

    @commands.slash_command(
        description="View current ticket category assignments (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def view_ticket_categories(self, inter: disnake.ApplicationCommandInteraction):
        """View current ticket category to Discord category assignments"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can view ticket category settings.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            assignments = await conn.fetch(
                """
                SELECT category_name, discord_category_id 
                FROM ticket_category_channels 
                WHERE guild_id = $1
                ORDER BY category_name
                """,
                str(inter.guild.id)
            )

        if not assignments:
            await inter.response.send_message(
                "❌ No ticket category assignments found. Use `/set_ticket_discord_categories` to set them up.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        embed = disnake.Embed(
            title="🎫 Ticket Category Assignments",
            description="Current Discord category assignments for ticket types:",
            color=disnake.Color.blue()
        )

        for assignment in assignments:
            category_name = assignment["category_name"]
            discord_category_id = assignment["discord_category_id"]
            discord_category = inter.guild.get_channel(int(discord_category_id))
            
            if discord_category:
                embed.add_field(
                    name=f"🎫 {category_name}",
                    value=f"📁 {discord_category.name}",
                    inline=True
                )
            else:
                embed.add_field(
                    name=f"🎫 {category_name}",
                    value="❌ Category not found",
                    inline=True
                )

        embed.set_footer(text="Use /set_ticket_discord_categories to modify assignments")
        
        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.slash_command(
        description="Remove Discord category assignment for a ticket type (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def remove_ticket_category_assignment(self, inter: disnake.ApplicationCommandInteraction):
        """Remove Discord category assignment for a ticket type"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can remove ticket category assignments.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            assignments = await conn.fetch(
                """
                SELECT category_name, discord_category_id 
                FROM ticket_category_channels 
                WHERE guild_id = $1
                ORDER BY category_name
                """,
                str(inter.guild.id)
            )

        if not assignments:
            await inter.response.send_message(
                "❌ No ticket category assignments found.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Create dropdown for assignments to remove
        options = []
        for assignment in assignments:
            category_name = assignment["category_name"]
            discord_category_id = assignment["discord_category_id"]
            discord_category = inter.guild.get_channel(int(discord_category_id))
            
            discord_name = discord_category.name if discord_category else "Category Not Found"
            
            options.append(disnake.SelectOption(
                label=category_name,
                value=category_name,
                description=f"Currently assigned to: {discord_name}"
            ))

        dropdown = disnake.ui.StringSelect(
            placeholder="Select ticket category to remove assignment...",
            options=options
        )
        
        async def assignment_selected(select_inter):
            category_name = select_inter.data["values"][0]
            
            async with (await get_database_pool()).acquire() as conn:
                await conn.execute(
                    "DELETE FROM ticket_category_channels WHERE guild_id = $1 AND category_name = $2",
                    str(inter.guild.id), category_name
                )
            
            await select_inter.response.send_message(
                f"✅ Removed Discord category assignment for **{category_name}**.\n"
                "These tickets will now be created in the default location.",
                ephemeral=True
            )
        
        dropdown.callback = assignment_selected
        
        view = disnake.ui.View()
        view.add_item(dropdown)
        
        await inter.response.send_message(
            "**🗑️ Remove Category Assignment**\n\nSelect which ticket category assignment to remove:",
            view=view,
            ephemeral=True
        )


def setup(bot):
    bot.add_cog(TicketSystem(bot))
