import disnake
from disnake.ext import commands
from utils.database import get_database_pool
import config
import logging
import asyncio

logger = logging.getLogger(__name__)

class TicketManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        description="List all active tickets in the server (server owner/moderators only).",
        default_member_permissions=disnake.Permissions(manage_channels=True),
    )
    async def list_tickets(self, inter: disnake.ApplicationCommandInteraction):
        """Lists all active tickets in the server"""
        async with (await get_database_pool()).acquire() as conn:
            tickets = await conn.fetch(
                """
                SELECT channel_id, user_id, product_name, ticket_number, created_at
                FROM active_tickets 
                WHERE guild_id = $1 
                ORDER BY ticket_number DESC
                """,
                str(inter.guild.id)
            )
            
        if not tickets:
            await inter.response.send_message(
                "📋 No active tickets found in this server.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        embed = disnake.Embed(
            title="🎫 Active Tickets",
            color=disnake.Color.blurple()
        )

        ticket_list = []
        for ticket in tickets:
            channel = inter.guild.get_channel(int(ticket["channel_id"]))
            user = inter.guild.get_member(int(ticket["user_id"]))
            
            if channel:  # Only show if channel still exists
                channel_mention = channel.mention
                user_display = user.display_name if user else "Unknown User"
                product = ticket["product_name"] or "General Support"
                created = f"<t:{int(ticket['created_at'].timestamp())}:R>"
                
                ticket_list.append(
                    f"**#{ticket['ticket_number']:04d}** - {channel_mention}\n"
                    f"└ User: {user_display} | Product: {product} | Created: {created}"
                )
            else:
                # Clean up stale ticket records
                async with (await get_database_pool()).acquire() as conn:
                    await conn.execute(
                        "DELETE FROM active_tickets WHERE guild_id = $1 AND channel_id = $2",
                        str(inter.guild.id), ticket["channel_id"]
                    )

        if not ticket_list:
            await inter.response.send_message(
                "📋 No active tickets found (cleaned up stale records).",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Split into pages if too long
        description = "\n\n".join(ticket_list)
        if len(description) > 4096:
            description = description[:4093] + "..."
            
        embed.description = description
        embed.set_footer(text=f"Total: {len(ticket_list)} active tickets")

        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.slash_command(
        description="Force close a ticket by ticket number (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def force_close_ticket(
        self, 
        inter: disnake.ApplicationCommandInteraction,
        ticket_number: int
    ):
        """Force closes a ticket by its number"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can force close tickets.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            ticket = await conn.fetchrow(
                "SELECT channel_id, user_id, product_name FROM active_tickets WHERE guild_id = $1 AND ticket_number = $2",
                str(inter.guild.id), ticket_number
            )
            
            if not ticket:
                await inter.response.send_message(
                    f"❌ No active ticket found with number #{ticket_number:04d}.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

            channel = inter.guild.get_channel(int(ticket["channel_id"]))
            user = inter.guild.get_member(int(ticket["user_id"]))
            
            if not channel:
                # Clean up stale record
                await conn.execute(
                    "DELETE FROM active_tickets WHERE guild_id = $1 AND ticket_number = $2",
                    str(inter.guild.id), ticket_number
                )
                await inter.response.send_message(
                    f"❌ Ticket #{ticket_number:04d} channel no longer exists (cleaned up record).",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

            try:
                # Send closure notice to the ticket channel
                closure_embed = disnake.Embed(
                    title="🔒 Ticket Force Closed",
                    description=f"This ticket has been force closed by {inter.author.mention}.\nChannel will be deleted in 10 seconds.",
                    color=disnake.Color.red()
                )
                await channel.send(embed=closure_embed)
                
                # Remove from database
                await conn.execute(
                    "DELETE FROM active_tickets WHERE guild_id = $1 AND ticket_number = $2",
                    str(inter.guild.id), ticket_number
                )
                
                await inter.response.send_message(
                    f"✅ Ticket #{ticket_number:04d} will be deleted in 10 seconds.",
                    ephemeral=True
                )
                
                # Delete channel after delay
                await asyncio.sleep(10)
                await channel.delete(reason=f"Ticket force closed by {inter.author}")
                
                logger.info(f"[Ticket Force Closed] #{ticket_number:04d} force closed by {inter.author} in '{inter.guild.name}'")
                
            except disnake.Forbidden:
                await inter.followup.send(
                    "❌ I don't have permission to delete the ticket channel.",
                    ephemeral=True
                )
            except disnake.NotFound:
                # Channel already deleted
                pass

    @commands.slash_command(
        description="Add a user to the current ticket (moderators only).",
        default_member_permissions=disnake.Permissions(manage_channels=True),
    )
    async def add_to_ticket(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user: disnake.Member
    ):
        """Adds a user to the current ticket channel"""
        async with (await get_database_pool()).acquire() as conn:
            ticket = await conn.fetchrow(
                "SELECT user_id, ticket_number FROM active_tickets WHERE guild_id = $1 AND channel_id = $2",
                str(inter.guild.id), str(inter.channel.id)
            )
            
            if not ticket:
                await inter.response.send_message(
                    "❌ This is not a ticket channel.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

        try:
            await inter.channel.set_permissions(
                user,
                read_messages=True,
                send_messages=True,
                attach_files=True,
                embed_links=True
            )
            
            embed = disnake.Embed(
                title="👥 User Added to Ticket",
                description=f"{user.mention} has been added to this ticket by {inter.author.mention}.",
                color=disnake.Color.green()
            )
            
            await inter.response.send_message(embed=embed)
            logger.info(f"[User Added] {user} added to ticket #{ticket['ticket_number']:04d} by {inter.author} in '{inter.guild.name}'")
            
        except disnake.Forbidden:
            await inter.response.send_message(
                "❌ I don't have permission to modify channel permissions.",
                ephemeral=True
            )

def setup(bot):
    bot.add_cog(TicketManagement(bot))
