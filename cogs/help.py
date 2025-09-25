import disnake
from disnake.ext import commands
import config

class HelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name="help",
        description="Displays information about what the KeyVerify bot can do (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def help(self, inter: disnake.ApplicationCommandInteraction):
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can use this command.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        embed = disnake.Embed(
            title="🔑 Welcome to KeyVerify",
            description=(
                "KeyVerify helps you manage Payhip license verification, role assignment, customer support, and product stock.\n\n"
                "Here's what you can do:"
            ),
            color=disnake.Color.blurple()
        )

        embed.add_field(
            name="🛠️ Verification",
            value="/start_verification — Post or update the verification message",
            inline=False
        )

        embed.add_field(
            name="🎁 Product Management",
            value=(
                "/add_product — Add a product with role assignment\n"
                "/list_products — View all added products\n"
                "/remove_product — Delete a product from the server"
            ),
            inline=False
        )

        embed.add_field(
            name="📦 Stock Management",
            value=(
                "/set_stock — Set stock amount for a product (-1 for unlimited)\n"
                "/adjust_stock — Add or remove stock from a product\n"
                "/view_stock — View stock levels for all products\n"
                "/create_stock_channel — Create a private stock display channel\n"
                "/delete_stock_channel — Delete a stock display channel"
            ),
            inline=False
        )

        embed.add_field(
            name="🎫 Ticket System",
            value=(
                "/create_ticket_box — Create a ticket system for customer support\n"
                "/customize_ticket_box — Customize ticket box text and appearance\n"
                "/update_ticket_boxes — Update all existing ticket boxes\n"
                "/ticket_variables — Show available variables for customization\n"
                "/reset_ticket_box — Reset ticket box to default settings\n"
                "/list_tickets — View all active support tickets\n"
                "/close_ticket — Close the current ticket (in ticket channel)\n"
                "/force_close_ticket — Force close a ticket by number\n"
                "/add_to_ticket — Add a user to the current ticket"
            ),
            inline=False
        )

        embed.add_field(
            name="📂 Ticket Categories & Organization",
            value=(
                "/add_ticket_category — Add custom ticket categories\n"
                "/edit_ticket_category — Edit existing ticket categories\n"
                "/remove_ticket_category — Remove ticket categories\n"
                "/list_ticket_categories — View all categories and their order\n"
                "/reorder_ticket_categories — Change the display order of categories\n"
                "**🏷️ /set_ticket_categories — Assign Discord categories to ticket types**\n"
                "/remove_ticket_category_assignment — Remove category assignments"
            ),
            inline=False
        )

        embed.add_field(
            name="🛡️ Role & Permission Management",
            value=(
                "/set_role_permissions — Configure role permissions for bot functions\n"
                "/set_auto_roles — Set roles for joining members and verified users\n"
                "/set_product_auto_roles — Set product-specific auto-roles\n"
                "/view_role_settings — View current role permissions and auto-roles\n"
                "/view_all_auto_roles — View comprehensive auto-role settings"
            ),
            inline=False
        )

        embed.add_field(
            name="🤖 Bot Settings",
            value=(
                "/set_bot_status — Customize the bot's status message\n"
                "/reset_bot_status — Reset bot status to default\n"
                "/view_bot_settings — View current bot configuration\n"
                "/toggle_welcome_messages — Enable/disable welcome messages"
            ),
            inline=False
        )

        embed.add_field(
            name="📝 Message Management",
            value=(
                "/create_message — Create custom embed messages (like ToS)\n"
                "/edit_message — Edit existing custom messages\n"
                "/delete_message — Delete custom messages\n"
                "/list_messages — View all custom messages"
            ),
            inline=False
        )

        embed.add_field(
            name="🔁 License Actions",
            value=(
                "/reset_key — Reset usage for a license key (Payhip API required)\n"
                "/remove_user — Blacklist a user and deactivate all used licenses"
            ),
            inline=False
        )

        embed.add_field(
            name="📊 Server Management",
            value=(
                "/server_stats — Get comprehensive server and bot usage statistics\n"
                "/cleanup_data — Clean up stale data and optimize database\n"
                "/export_config — Export server configuration as backup\n"
                "/check_permissions — Check permissions for a specific user"
            ),
            inline=False
        )

        embed.add_field(
            name="📜 Utility",
            value="/set_lchannel — Set a channel for verification log messages",
            inline=False
        )

        embed.add_field(
            name="🛡️ Security & Features",
            value=(
                "• Secure encrypted storage for license data\n"
                "• Role reassignment for rejoining users\n"
                "• Cooldown protection to prevent abuse\n"
                "• Activity logs and optional logging channel\n"
                "• **Private ticket channels with Discord category organization**\n"
                "• Product-specific support categorization\n"
                "• Real-time stock tracking and display\n"
                "• Automatic 'SOLD OUT' prevention in tickets\n"
                "• Custom ticket box text with dynamic variables\n"
                "• Professional message management system"
            ),
            inline=False
        )
        
