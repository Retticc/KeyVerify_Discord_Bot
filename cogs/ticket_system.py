import disnake
from disnake.ext import commands
from utils.database import get_database_pool, fetch_products
from handlers.ticket_handler import create_ticket_embed, create_ticket_view
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
            embed.description += "\n\n⚠️ *Note: No categories or products are configured yet. Use `/add_ticket_category` or `/add_product` to add options.*"
        
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
                description=f"Are you sure you want to close this ticket?\n\n"
                           f"**User:** {user_display}\n"
                           f"**Product:** {ticket['product_name'] or 'Not specified'}\n"
                           f"**Ticket #:** {ticket['ticket_number']}",
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

def setup(bot):
    bot.add_cog(TicketSystem(bot))
