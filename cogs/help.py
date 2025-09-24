import disnake
from disnake.ext import commands
import config

# Help command providing a full overview of KeyVerify's capabilities (server owner only).
class HelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name="help",
        description="Displays information about what the KeyVerify bot can do (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def help(self, inter: disnake.ApplicationCommandInteraction):
        # Restrict usage to the server owner
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
                "• Private ticket channels with automatic license requests\n"
                "• Product-specific support categorization\n"
                "• Real-time stock tracking and display\n"
                "• Automatic 'SOLD OUT' prevention in tickets\n"
                "• Custom ticket box text with dynamic variables\n"
                "• Professional message management system"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎫 Ticket System Features",
            value=(
                "• Customizable ticket box text with variables like `{PRODUCT_COUNT}`\n"
                "• Custom ticket categories with display order control\n"
                "• Dynamic stock status indicators (🟢🟡🔴♾️)\n"
                "• Private channels with proper permissions\n"
                "• Automatic license verification requests\n"
                "• Ticket numbering and tracking\n"
                "• Staff management tools\n"
                "• Sold out products blocked from ticket creation"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📊 Stock Management Features",
            value=(
                "• Set unlimited (-1) or specific stock amounts\n"
                "• Real-time stock display channels with emoji indicators\n"
                "• Stock status shown in ticket product selection\n"
                "• Automatic channel name updates when stock changes\n"
                "• Private stock monitoring channels\n"
                "• Variables for ticket customization: `{PRODUCTNAME.STOCK}`"
            ),
            inline=False
        )

        embed.add_field(
            name="📝 Message Management Features",
            value=(
                "• Create professional embed messages like Terms of Service\n"
                "• JSON-based field system for complex layouts\n"
                "• Automatic timestamps and formatting\n"
                "• Edit and update existing messages\n"
                "• Draft system for messages not yet posted\n"
                "• Easy deletion with confirmation"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔧 Variables Available",
            value=(
                "• `{SERVER_NAME}` `{SERVER_MEMBER_COUNT}` `{PRODUCT_COUNT}`\n"
                "• `{PRODUCTNAME.STOCK}` `{TOTAL_STOCK}` `{CURRENT_DATE}`\n"
                "• `{PRODUCTS_IN_STOCK}` `{PRODUCTS_SOLD_OUT}` and more!\n"
                "Use `/ticket_variables` to see all available options."
            ),
            inline=False
        )
        
        embed.add_field(
            name="Need support?",
            value="[Click here to join the support server](https://discord.com/oauth2/authorize?client_id=1314098590951673927&integration_type=0&permissions=268446720&redirect_uri=https%3A%2F%2Fdiscord.com%2Foauth2%2Fauthorize%3Fclient_id%3D1314098590951673927&response_type=code&scope=guilds.join+bot)",
            inline=False
        )
        await inter.response.send_message(embed=embed, ephemeral=True, delete_after=config.message_timeout)

def setup(bot):
    bot.add_cog(HelpCommand(bot))
