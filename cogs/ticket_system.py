# cogs/ticket_system.py
import disnake
from disnake.ext import commands
from utils.database import get_database_pool, fetch_products
from handlers.ticket_handler import (
    create_ticket_embed,
    create_ticket_view,
    fetch_ticket_categories,  # used by mapping command
)
import config
import logging
import asyncio

logger = logging.getLogger(__name__)

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Ensure tables exist after the bot is ready
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

            # Table for mapping custom ticket categories -> Discord category IDs
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_category_channels (
                    guild_id TEXT NOT NULL,
                    category_name TEXT NOT NULL,
                    discord_category_id TEXT NOT NULL,
                    PRIMARY KEY (guild_id, category_name)
                );
            """)

    # -------------------------------
    # Ticket Box: create/update
    # -------------------------------
    @commands.slash_command(
        description="Create a ticket system box for users to create support tickets.",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def create_ticket_box(self, inter: disnake.ApplicationCommandInteraction):
        """Creates a ticket box that users can interact with to create support tickets"""
        if not inter.author.guild_permissions.manage_guild:
            await inter.response.send_message(
                "❌ You need **Manage Server** to use this.",
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
            embed.description = (embed.description or "") + "\n\n⚠️ *Note: No categories or products are configured yet. Use `/add_ticket_category` or `/add_product` to add options.*"
        
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
                """
                INSERT INTO ticket_boxes (guild_id, message_id, channel_id)
                VALUES ($1, $2, $3)
                """,
                str(inter.guild.id), str(message.id), str(inter.channel.id)
            )

        logger.info(f"[Ticket Box Created] {inter.author} created a ticket box in '{inter.guild.name}'")
        
        success_msg = "✅ Ticket box created successfully!"
        if not categories and not products:
            success_msg += "\n💡 **Tip:** Add categories with `/add_ticket_category` or products with `/add_product` to give users ticket options."
        else:
            success_msg += "\n💡 **Tip:** Use `/customize_ticket_box` to personalize the text and `/ticket_variables` to see available variables."
        
        await inter.response.send_message(
            success_msg,
            ephemeral=True,
            delete_after=config.message_timeout
        )

    @commands.slash_command(
        description="Update all existing ticket boxes with new customization.",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def update_ticket_boxes(self, inter: disnake.ApplicationCommandInteraction):
        """Updates all existing ticket boxes in the server"""
        if not inter.author.guild_permissions.manage_guild:
            await inter.response.send_message(
                "❌ You need **Manage Server** to do this.",
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

    # -------------------------------
    # Ticket Close
    # -------------------------------
    @commands.slash_command(
        description="Close the current ticket channel.",
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
                    "Are you sure you want to close this ticket?\n\n"
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
                        
                        logger.info(f"[Ticket Closed] Ticket #{ticket['ticket_number']} closed by {button_inter.author} in '{inter.guild.name}'")
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

    # -------------------------------
    # Map custom ticket categories to Discord categories (one-to-one)
    # NOTE: Name is UNIQUE to avoid clashing with other cogs.
    # -------------------------------
    @commands.slash_command(
        name="map_ticket_categories",  # <— RENAMED to avoid conflicts
        description="Map custom ticket categories to specific Discord categories.",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def map_ticket_categories(self, inter: disnake.ApplicationCommandInteraction):
        """Map each custom ticket category to a Discord category (one-to-one)."""
        if not inter.author.guild_permissions.manage_guild:
            await inter.response.send_message(
                "❌ You need **Manage Server** to set mappings.",
                ephemeral=True
            )
            return

        # Ensure mapping table exists
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_category_channels (
                    guild_id TEXT NOT NULL,
                    category_name TEXT NOT NULL,
                    discord_category_id TEXT NOT NULL,
                    PRIMARY KEY (guild_id, category_name)
                );
            """)

        # Fetch your custom ticket categories
        categories = await fetch_ticket_categories(str(inter.guild.id))
        if not categories:
            await inter.response.send_message(
                "❌ No custom ticket categories found. Use `/add_ticket_category` first.",
                ephemeral=True
            )
            return

        async def show_ticket_category_picker():
            options = [
                disnake.SelectOption(
                    label=cat["category_name"],
                    value=cat["category_name"],
                    description=f"Set Discord category for {cat['category_name']}"
                )
                for cat in categories
            ][:25]

            view = disnake.ui.View(timeout=180)
            cat_select = disnake.ui.StringSelect(
                placeholder="Select a TICKET CATEGORY to map…",
                min_values=1,
                max_values=1,
                options=options
            )

            async def on_ticket_category(select_inter: disnake.MessageInteraction):
                if select_inter.author.id != inter.author.id:
                    await select_inter.response.send_message("❌ Only the command invoker can use this menu.", ephemeral=True)
                    return

                ticket_category = select_inter.data["values"][0]

                # Build Discord category options (plus an option to clear mapping back to Default)
                dc_options = [
                    disnake.SelectOption(
                        label="🔄 Default (no Discord category)",
                        value="__DEFAULT__",
                        description="Clear mapping so tickets are created outside of any category."
                    )
                ]
                for dc_cat in inter.guild.categories:
                    dc_options.append(
                        disnake.SelectOption(
                            label=f"📁 {dc_cat.name}",
                            value=str(dc_cat.id),
                            description=f"{len(dc_cat.channels)} channels"
                        )
                    )
                dc_options = dc_options[:25]

                if len(dc_options) == 1:
                    await select_inter.response.send_message(
                        "❌ No Discord categories found. Create some categories first.",
                        ephemeral=True
                    )
                    return

                dc_view = disnake.ui.View(timeout=180)
                dc_select = disnake.ui.StringSelect(
                    placeholder=f"Select a DISCORD CATEGORY for “{ticket_category}”…",
                    min_values=1,
                    max_values=1,
                    options=dc_options
                )

                async def on_dc_category(dc_inter: disnake.MessageInteraction):
                    if dc_inter.author.id != inter.author.id:
                        await dc_inter.response.send_message("❌ Only the command invoker can use this menu.", ephemeral=True)
                        return

                    chosen = dc_inter.data["values"][0]
                    if chosen == "__DEFAULT__":
                        # Clear mapping by deleting any row for this ticket_category
                        async with (await get_database_pool()).acquire() as conn:
                            await conn.execute(
                                "DELETE FROM ticket_category_channels WHERE guild_id = $1 AND category_name = $2",
                                str(inter.guild.id), ticket_category
                            )
                        await dc_inter.response.send_message(
                            f"✅ **{ticket_category}** → **Default** (no Discord category).",
                            ephemeral=True
                        )
                    else:
                        # Upsert mapping to specific Discord category
                        discord_category = inter.guild.get_channel(int(chosen))
                        if not discord_category or discord_category.type != disnake.ChannelType.category:
                            await dc_inter.response.send_message("❌ That selection is not a valid Discord category.", ephemeral=True)
                            return

                        async with (await get_database_pool()).acquire() as conn:
                            await conn.execute(
                                """
                                INSERT INTO ticket_category_channels (guild_id, category_name, discord_category_id)
                                VALUES ($1, $2, $3)
                                ON CONFLICT (guild_id, category_name)
                                DO UPDATE SET discord_category_id = $3
                                """,
                                str(inter.guild.id), ticket_category, str(discord_category.id)
                            )

                        await dc_inter.response.send_message(
                            f"✅ **{ticket_category}** tickets will go in **📁 {discord_category.name}**.",
                            ephemeral=True
                        )

                    # After saving one mapping, re-show the first menu so the admin can map more
                    await show_next_step(dc_inter)

                dc_select.callback = on_dc_category
                dc_view.add_item(dc_select)
                await select_inter.response.send_message(
                    f"Now pick a **Discord category** for **{ticket_category}**:",
                    view=dc_view,
                    ephemeral=True
                )

            cat_select.callback = on_ticket_category
            view.add_item(cat_select)

            @disnake.ui.button(label="📋 View current mappings", style=disnake.ButtonStyle.secondary)
            async def view_mappings_btn(btn: disnake.ui.Button, btn_inter: disnake.MessageInteraction):
                if btn_inter.author.id != inter.author.id:
                    await btn_inter.response.send_message("❌ Only the command invoker can use this button.", ephemeral=True)
                    return

                # Load current mappings from DB
                async with (await get_database_pool()).acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT category_name, discord_category_id FROM ticket_category_channels WHERE guild_id = $1",
                        str(inter.guild.id)
                    )
                mapping = {r["category_name"]: r["discord_category_id"] for r in rows}

                # Build a simple text list
                if not mapping:
                    await btn_inter.response.send_message("No mappings set. All categories use **Default**.", ephemeral=True)
                    return

                lines = []
                cat_names = [c["category_name"] for c in categories]
                for name in cat_names:
                    dc_id = mapping.get(name)
                    if dc_id:
                        dc_cat = inter.guild.get_channel(int(dc_id))
                        dc_name = f"📁 {dc_cat.name}" if dc_cat else f"(missing category {dc_id})"
                    else:
                        dc_name = "Default"
                    lines.append(f"• **{name}** → {dc_name}")

                await btn_inter.response.send_message("\n".join(lines), ephemeral=True)

            await inter.response.send_message(
                "Select a **ticket category** to map to a **Discord category**:",
                view=view,
                ephemeral=True
            )

        async def show_next_step(source_inter: disnake.MessageInteraction):
            # Re-open the first picker so you can map another without re-running the command
            await show_ticket_category_picker()

        # Kick off the UI
        await show_ticket_category_picker()


def setup(bot):
    bot.add_cog(TicketSystem(bot))
