import disnake
from disnake.ext import commands
from utils.database import get_database_pool
from utils.permissions import owner_or_permission
import config
import logging

logger = logging.getLogger(__name__)

class SalesManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        description="Set total sales count for a product (server owner/authorized only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @owner_or_permission("manage_products")
    async def set_product_sales(
        self,
        inter: disnake.ApplicationCommandInteraction,
        product_name: str,
        total_sold: int
    ):
        """Manually set the total sales count for a product"""
        if total_sold < 0:
            await inter.response.send_message(
                "❌ Sales count cannot be negative.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            # Check if product exists
            product = await conn.fetchrow(
                "SELECT product_name FROM products WHERE guild_id = $1 AND product_name = $2",
                str(inter.guild.id), product_name
            )
            
            if not product:
                await inter.response.send_message(
                    f"❌ Product '{product_name}' not found.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

            # Update or insert sales count
            await conn.execute(
                """
                INSERT INTO product_sales (guild_id, product_name, total_sold)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id, product_name)
                DO UPDATE SET total_sold = $3
                """,
                str(inter.guild.id), product_name, total_sold
            )

        await inter.response.send_message(
            f"✅ Total sales for **{product_name}** set to: {total_sold:,}",
            ephemeral=True,
            delete_after=config.message_timeout
        )

        logger.info(f"[Sales Updated] {inter.author} set sales for '{product_name}' to {total_sold} in '{inter.guild.name}'")

    @commands.slash_command(
        description="Adjust sales count for a product (add or subtract).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @owner_or_permission("manage_products")
    async def adjust_product_sales(
        self,
        inter: disnake.ApplicationCommandInteraction,
        product_name: str,
        change: int
    ):
        """Adjust sales count by adding or subtracting"""
        async with (await get_database_pool()).acquire() as conn:
            # Get current sales
            current_sales = await conn.fetchrow(
                "SELECT total_sold FROM product_sales WHERE guild_id = $1 AND product_name = $2",
                str(inter.guild.id), product_name
            )
            
            if not current_sales:
                # Initialize with 0 if doesn't exist
                current_count = 0
            else:
                current_count = current_sales["total_sold"]

            new_count = max(0, current_count + change)
            
            # Update sales count
            await conn.execute(
                """
                INSERT INTO product_sales (guild_id, product_name, total_sold)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id, product_name)
                DO UPDATE SET total_sold = $3
                """,
                str(inter.guild.id), product_name, new_count
            )

        change_text = f"+{change}" if change > 0 else str(change)
        await inter.response.send_message(
            f"✅ **{product_name}** sales adjusted by {change_text}. New total: {new_count:,}",
            ephemeral=True,
            delete_after=config.message_timeout
        )

        logger.info(f"[Sales Adjusted] {inter.author} adjusted '{product_name}' sales by {change} in '{inter.guild.name}'")

    @commands.slash_command(
        description="View sales statistics for all products.",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @owner_or_permission("view_admin")
    async def view_sales_stats(self, inter: disnake.ApplicationCommandInteraction):
        """Display sales statistics for all products"""
        async with (await get_database_pool()).acquire() as conn:
            sales_data = await conn.fetch(
                "SELECT product_name, total_sold FROM product_sales WHERE guild_id = $1 ORDER BY total_sold DESC",
                str(inter.guild.id)
            )

        if not sales_data:
            await inter.response.send_message(
                "📊 No sales data found. Use `/set_product_sales` to track sales.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        embed = disnake.Embed(
            title="📊 Product Sales Statistics",
            color=disnake.Color.green()
        )

        total_sales = 0
        sales_lines = []
        for sale in sales_data:
            total_sales += sale["total_sold"]
            sales_lines.append(f"**{sale['product_name']}** - {sale['total_sold']:,} sold")

        embed.description = "\n".join(sales_lines)
        embed.add_field(
            name="📈 Total Sales Across All Products",
            value=f"**{total_sales:,}** products sold",
            inline=False
        )
        embed.set_footer(text="Use /set_product_sales or /adjust_product_sales to manage")

        await inter.response.send_message(embed=embed, ephemeral=True)

def setup(bot):
    bot.add_cog(SalesManagement(bot))
