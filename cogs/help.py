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
                "KeyVerify is your complete Discord server management solution for digital product sales, customer support, and community management.\n\n"
                "Here's everything you can do:"
            ),
            color=disnake.Color.blurple()
        )

        embed.add_field(
            name="🛠️ Verification System",
            value="/start_verification — Post or update the license verification message",
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
            name="📊 Sales Management",
            value=(
                "/set_product_sales — Manually set total sales count for products\n"
                "/adjust_product_sales — Add or subtract from sales totals\n"
                "/view_sales_stats — View comprehensive sales statistics"
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
                "/add_to_ticket — Add a user to the current ticket\n"
                "/set_ticket_discord_categories — Assign Discord categories for tickets"
            ),
            inline=False
        )

        embed.add_field(
            name="📂 Ticket Categories",
            value=(
                "/add_ticket_category — Add custom ticket categories\n"
                "/edit_ticket_category — Edit existing ticket categories\n"
                "/remove_ticket_category — Remove ticket categories\n"
                "/list_ticket_categories — View all categories and their order\n"
                "/reorder_ticket_categories — Change the display order of categories"
            ),
            inline=False
        )

        embed.add_field(
            name="⭐ Review System",
            value=(
                "/set_review_channel — Set channel where customer reviews are posted\n"
                "/request_review — Request a review from a customer (staff only)\n"
                "• Customers rate products 1-5 stars with optional descriptions\n"
                "• Only users with ticket permissions can request reviews"
            ),
            inline=False
        )

        embed.add_field(
            name="🛡️ Role & Permission Management",
            value=(
                "/set_role_permissions — Configure role permissions for bot functions\n"
                "/set_auto_roles — Set roles for joining members and verified users\n"
                "/set_product_auto_roles — Configure product-specific auto-roles\n"
                "/view_all_auto_roles — View all auto-role configurations\n"
                "/view_role_settings — View current role permissions and auto-roles\n"
                "/check_permissions — Check what permissions a user has"
            ),
            inline=False
        )

        embed.add_field(
            name="🤖 Bot Settings & Utilities",
            value=(
                "/set_bot_status — Customize the bot's status message\n"
                "/reset_bot_status — Reset bot status to default\n"
                "/view_bot_settings — View current bot configuration\n"
                "/toggle_welcome_messages — Enable/disable member welcome messages\n"
                "/server_stats — Comprehensive server and bot usage statistics\n"
                "/cleanup_data — Clean up stale database entries\n"
                "/export_config — Export configuration backup"
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
            name="📜 Utility Commands",
            value="/set_lchannel — Set a channel for verification log messages",
            inline=False
        )

        embed.add_field(
            name="🛡️ Advanced Security & Features",
            value=(
                "• **Encrypted Data Storage** - All license keys and secrets are AES encrypted\n"
                "• **Role-Based Permissions** - 10 different permission types for granular control\n"
                "• **Private Ticket System** - Only authorized staff can access support tickets\n"
                "• **Smart Auto-Roles** - Automatic role assignment on join and verification\n"
                "• **Product-Specific Roles** - Different roles for different products\n"
                "• **Discord Category Integration** - Organize tickets into specific categories\n"
                "• **Real-Time Stock Tracking** - Live inventory management with indicators\n"
                "• **Sales Analytics** - Manual sales tracking with comprehensive statistics\n"
                "• **Customer Review System** - Professional 5-star rating system\n"
                "• **Cooldown Protection** - Built-in abuse prevention\n"
                "• **Activity Logging** - Comprehensive audit trails"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Auto-Role Features",
            value=(
                "• **Join Roles** - Automatically assign roles when users join your server\n"
                "• **Verified Roles** - Assign roles when users verify ANY product\n"
                "• **Product-Specific Roles** - Different roles for each product verified\n"
                "• **Multiple Roles** - Assign multiple roles per event\n"
                "• **Smart Permissions** - Role-based access to bot commands\n"
                "• **Welcome Messages** - Greet new members with role information"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎫 Professional Ticket System",
            value=(
                "• **100% Private Tickets** - Only authorized staff and the user can access\n"
                "• **Custom Categories** - Create your own support categories\n"
                "• **Discord Integration** - Tickets appear in specified Discord categories\n"
                "• **Permission-Based Access** - Control who can handle tickets\n"
                "• **Stock Status Integration** - Shows real-time product availability\n"
                "• **Automatic License Requests** - Streamlined verification process\n"
                "• **Ticket Numbering** - Professional tracking system\n"
                "• **Staff Management** - Add users to specific tickets\n"
                "• **Custom Variables** - Dynamic content in ticket messages"
            ),
            inline=False
        )

        embed.add_field(
            name="📊 Sales & Analytics Features",
            value=(
                "• **Manual Sales Tracking** - Full control over sales numbers\n"
                "• **Cross-Product Analytics** - Total sales across all products\n"
                "• **Variable Integration** - Use `{TOTAL_SALES}` in messages\n"
                "• **Professional Reviews** - 5-star rating system with descriptions\n"
                "• **Staff-Requested Reviews** - Only authorized users can request\n"
                "• **Channel-Based Reviews** - Reviews post to your chosen channel\n"
                "• **Anti-Spam Protection** - One review request per user per product"
            ),
            inline=False
        )

        embed.add_field(
            name="🔧 Available Variables",
            value=(
                "**Server:** `{SERVER_NAME}` `{SERVER_MEMBER_COUNT}` `{SERVER_OWNER}`\n"
                "**Products:** `{PRODUCT_COUNT}` `{PRODUCTS_IN_STOCK}` `{PRODUCTS_SOLD_OUT}`\n"
                "**Stock:** `{PRODUCTNAME.STOCK}` `{TOTAL_STOCK}` \n"
                "**Sales:** `{TOTAL_SALES}` (NEW!)\n"
                "**Time:** `{CURRENT_DATE}` `{CURRENT_TIME}`\n\n"
                "Use `/ticket_variables` to see all available options with examples."
            ),
            inline=False
        )

        embed.add_field(
            name="🎯 Permission Types Available",
            value=(
                "**🎁 Product Management** - Add, remove, manage products\n"
                "**🎫 Ticket Management** - Create and configure ticket systems\n"
                "**🛠️ Handle Tickets** - Access and respond to support tickets\n"
                "**📦 Stock Management** - Manage product inventory\n"
                "**📂 Ticket Categories** - Manage support categories\n"
                "**📝 Custom Messages** - Create embed messages\n"
                "**🔑 Verification System** - Manage license verification\n"
                "**⚙️ Auto-Role Management** - Configure automatic roles\n"
                "**🤖 Bot Settings** - Customize bot behavior\n"
                "**👁️ View Admin Commands** - Access administrative tools"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🚀 Getting Started",
            value=(
                "**New Server Setup:**\n"
                "1. `/add_product` - Add your first product\n"
                "2. `/set_auto_roles` - Configure member roles\n"
                "3. `/set_role_permissions` - Set up staff permissions\n"
                "4. `/create_ticket_box` - Deploy support system\n"
                "5. `/set_review_channel` - Enable customer reviews\n"
                "6. `/start_verification` - Launch verification system"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Need Support?",
            value=(
                "[📞 Join Support Server](https://discord.com/oauth2/authorize?client_id=1314098590951673927)\n"
                "[📚 Full Documentation](https://docs.keyverify.bot)\n"
                "[🐛 Report Issues](https://github.com/keyverify/issues)"
            ),
            inline=False
        )

        embed.set_footer(text="KeyVerify - Complete Discord Server Management Solution | Use /server_stats for quick overview")
        embed.set_thumbnail(url=inter.guild.icon.url if inter.guild.icon else None)
        
        await inter.response.send_message(embed=embed, ephemeral=True, delete_after=config.message_timeout)

def setup(bot):
    bot.add_cog(HelpCommand(bot))
