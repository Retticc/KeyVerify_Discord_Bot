import disnake
from disnake.ext import commands
import config

class HelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name="help",
        description="Show KeyVerify commands (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def help(self, inter: disnake.ApplicationCommandInteraction):
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can use this command.",
                ephemeral=True
            )
            return

        embed = disnake.Embed(
            title="🔑 KeyVerify — Quick Help",
            description="Core commands grouped by feature. Use the docs for full details.",
            color=disnake.Color.blurple()
        )

        # Keep fields short; comma-separated lists fit < 1024 chars easily.

        embed.add_field(
            name="🛠️ Verification",
            value="`/start_verification`",
            inline=False
        )

        embed.add_field(
            name="🎁 Products & Sales",
            value="`/add_product`, `/list_products`, `/remove_product`, `/set_product_sales`, `/adjust_product_sales`, `/view_sales_stats`",
            inline=False
        )

        embed.add_field(
            name="📦 Stock",
            value="`/set_stock`, `/adjust_stock`, `/view_stock`, `/create_stock_channel`, `/delete_stock_channel`",
            inline=False
        )

        embed.add_field(
            name="🎫 Tickets",
            value=(
                "`/create_ticket_box`, `/customize_ticket_box`, `/update_ticket_boxes`, `/reset_ticket_box`, "
                "`/ticket_variables`, `/list_tickets`, `/close_ticket`, `/force_close_ticket`, `/add_to_ticket`, "
                "`/set_ticket_discord_categories`"
            ),
            inline=False
        )

        embed.add_field(
            name="📂 Ticket Categories",
            value="`/add_ticket_category`, `/edit_ticket_category`, `/remove_ticket_category`, `/list_ticket_categories`, `/reorder_ticket_categories`",
            inline=False
        )

        embed.add_field(
            name="⭐ Reviews",
            value="`/set_review_channel`, `/request_review`",
            inline=False
        )

        embed.add_field(
            name="🛡️ Roles & Permissions",
            value="`/set_role_permissions`, `/set_auto_roles`, `/set_product_auto_roles`, `/view_all_auto_roles`, `/view_role_settings`, `/check_permissions`",
            inline=False
        )

        embed.add_field(
            name="🤖 Bot & Utilities",
            value="`/set_bot_status`, `/reset_bot_status`, `/view_bot_settings`, `/toggle_welcome_messages`, `/server_stats`, `/cleanup_data`, `/export_config`, `/set_lchannel`",
            inline=False
        )

        embed.add_field(
            name="🔁 Licenses",
            value="`/reset_key`, `/remove_user`",
            inline=False
        )

        embed.add_field(
            name="🔧 Variables (quick)",
            value="Use `/ticket_variables` for all options. Common: `{SERVER_NAME}`, `{TOTAL_SALES}`, `{CURRENT_DATE}`",
            inline=False
        )

        embed.add_field(
            name="🚀 Getting Started",
            value=(
                "`/add_product` → `/set_auto_roles` → `/set_role_permissions` → "
                "`/create_ticket_box` → `/set_review_channel` → `/start_verification`"
            ),
            inline=False
        )

        embed.add_field(
            name="📚 Links",
            value="[Support](https://discord.com/oauth2/authorize?client_id=1314098590951673927) • "
                  "[Docs](https://docs.keyverify.bot) • "
                  "[Issues](https://github.com/keyverify/issues)",
            inline=False
        )

        embed.set_footer(text="KeyVerify — Use /server_stats for an overview")
        if inter.guild.icon:
            embed.set_thumbnail(url=inter.guild.icon.url)

        await inter.response.send_message(embed=embed, ephemeral=True)

def setup(bot):
    bot.add_cog(HelpCommand(bot))
