import disnake
from disnake.ext import commands
from utils.database import get_database_pool, fetch_products
import config
import logging

logger = logging.getLogger(__name__)

class StockManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Schedule the database table creation as a background task after the bot is ready
        self.bot.loop.create_task(self.setup_table())
        
    async def setup_table(self):
        """Ensures the required tables exist for stock management"""
        await self.bot.wait_until_ready()
        async with (await get_database_pool()).acquire() as conn:
            # Add stock column to products table
            await conn.execute("""
                ALTER TABLE products 
                ADD COLUMN IF NOT EXISTS stock INTEGER DEFAULT -1
            """)
            
            # Table for stock display channels
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_channels (
                    guild_id TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    category_id TEXT,
                    PRIMARY KEY (guild_id, product_name)
                );
            """)

    @commands.slash_command(
        description="Set the stock amount for a product (server owner only). Use -1 for unlimited stock.",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def set_stock(
        self,
        inter: disnake.ApplicationCommandInteraction,
        product_name: str,
        amount: int
    ):
        """Sets the stock amount for a specific product"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can manage stock.",
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

            # Update stock
            await conn.execute(
                "UPDATE products SET stock = $1 WHERE guild_id = $2 AND product_name = $3",
                amount, str(inter.guild.id), product_name
            )

        stock_display = "Unlimited" if amount == -1 else str(amount)
        await inter.response.send_message(
            f"✅ Stock for **{product_name}** set to: {stock_display}",
            ephemeral=True,
            delete_after=config.message_timeout
        )

        # Update stock channel if it exists
        await self.update_stock_channel(inter.guild.id, product_name, amount)
        logger.info(f"[Stock Set] {inter.author} set stock for '{product_name}' to {amount} in '{inter.guild.name}'")

    @commands.slash_command(
        description="Add or remove stock from a product (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def adjust_stock(
        self,
        inter: disnake.ApplicationCommandInteraction,
        product_name: str,
        change: int
    ):
        """Adjusts stock by adding or subtracting from current amount"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can manage stock.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            # Get current stock
            product = await conn.fetchrow(
                "SELECT stock FROM products WHERE guild_id = $1 AND product_name = $2",
                str(inter.guild.id), product_name
            )
            
            if not product:
                await inter.response.send_message(
                    f"❌ Product '{product_name}' not found.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

            current_stock = product["stock"]
            
            # Can't adjust unlimited stock
            if current_stock == -1:
                await inter.response.send_message(
                    f"❌ Cannot adjust unlimited stock. Use `/set_stock` instead.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

            new_stock = max(0, current_stock + change)
            
            # Update stock
            await conn.execute(
                "UPDATE products SET stock = $1 WHERE guild_id = $2 AND product_name = $3",
                new_stock, str(inter.guild.id), product_name
            )

        change_text = f"+{change}" if change > 0 else str(change)
        await inter.response.send_message(
            f"✅ **{product_name}** stock adjusted by {change_text}. New stock: {new_stock}",
            ephemeral=True,
            delete_after=config.message_timeout
        )

        # Update stock channel if it exists
        await self.update_stock_channel(inter.guild.id, product_name, new_stock)
        logger.info(f"[Stock Adjusted] {inter.author} adjusted '{product_name}' stock by {change} in '{inter.guild.name}'")

    @commands.slash_command(
        description="View stock levels for all products (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def view_stock(self, inter: disnake.ApplicationCommandInteraction):
        """Displays stock levels for all products"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can view stock.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            products = await conn.fetch(
                "SELECT product_name, stock FROM products WHERE guild_id = $1 ORDER BY product_name",
                str(inter.guild.id)
            )

        if not products:
            await inter.response.send_message(
                "📦 No products found in this server.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        embed = disnake.Embed(
            title="📊 Product Stock Levels",
            color=disnake.Color.blurple()
        )

        stock_lines = []
        for product in products:
            stock = product["stock"]
            if stock == -1:
                status = "♾️ Unlimited"
            elif stock == 0:
                status = "🔴 SOLD OUT"
            elif stock <= 5:
                status = f"🟡 {stock} left"
            else:
                status = f"🟢 {stock} in stock"
            
            stock_lines.append(f"**{product['product_name']}** - {status}")

        embed.description = "\n".join(stock_lines)
        embed.set_footer(text="Use /set_stock or /adjust_stock to manage inventory")

        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.slash_command(
        description="Create a private stock display channel for a product (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def create_stock_channel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        product_name: str,
        category: disnake.CategoryChannel = None
    ):
        """Creates a private channel that displays stock count in the channel name"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can create stock channels.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            # Check if product exists and get current stock
            product = await conn.fetchrow(
                "SELECT stock FROM products WHERE guild_id = $1 AND product_name = $2",
                str(inter.guild.id), product_name
            )
            
            if not product:
                await inter.response.send_message(
                    f"❌ Product '{product_name}' not found.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

            # Check if stock channel already exists
            existing = await conn.fetchrow(
                "SELECT channel_id FROM stock_channels WHERE guild_id = $1 AND product_name = $2",
                str(inter.guild.id), product_name
            )
            
            if existing:
                old_channel = inter.guild.get_channel(int(existing["channel_id"]))
                if old_channel:
                    await inter.response.send_message(
                        f"❌ Stock channel for '{product_name}' already exists: {old_channel.mention}",
                        ephemeral=True,
                        delete_after=config.message_timeout
                    )
                    return
                else:
                    # Clean up stale record
                    await conn.execute(
                        "DELETE FROM stock_channels WHERE guild_id = $1 AND product_name = $2",
                        str(inter.guild.id), product_name
                    )

            stock = product["stock"]
            
            # Create channel name based on stock
            if stock == -1:
                channel_name = f"♾️┃{product_name.lower().replace(' ', '-')}"
            elif stock == 0:
                channel_name = f"🔴┃sold-out-{product_name.lower().replace(' ', '-')}"
            else:
                channel_name = f"📦┃{stock}-{product_name.lower().replace(' ', '-')}"

            # Set up permissions (private channel)
            overwrites = {
                inter.guild.default_role: disnake.PermissionOverwrite(read_messages=False),
                inter.guild.me: disnake.PermissionOverwrite(read_messages=True, send_messages=True),
                inter.guild.owner: disnake.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            # Add permissions for roles with manage_guild permission
            for role in inter.guild.roles:
                if role.permissions.manage_guild:
                    overwrites[role] = disnake.PermissionOverwrite(read_messages=True, send_messages=True)

            try:
                # Create the channel
                channel = await inter.guild.create_text_channel(
                    name=channel_name,
                    category=category,
                    overwrites=overwrites,
                    reason=f"Stock display channel for {product_name}"
                )

                # Save to database
                await conn.execute(
                    """
                    INSERT INTO stock_channels (guild_id, product_name, channel_id, category_id)
                    VALUES ($1, $2, $3, $4)
                    """,
                    str(inter.guild.id), product_name, str(channel.id), str(category.id) if category else None
                )

                # Send info message to the channel
                embed = disnake.Embed(
                    title=f"📊 {product_name} - Stock Monitor",
                    description=(
                        "This channel displays the current stock level for this product.\n\n"
                        f"**Current Stock:** {stock if stock != -1 else 'Unlimited'}\n"
                        f"**Last Updated:** <t:{int(inter.created_at.timestamp())}:F>\n\n"
                        "*This channel updates automatically when stock changes.*"
                    ),
                    color=disnake.Color.green() if stock > 0 or stock == -1 else disnake.Color.red()
                )
                embed.set_footer(text="Stock management powered by KeyVerify")
                
                await channel.send(embed=embed)

                await inter.response.send_message(
                    f"✅ Stock channel created: {channel.mention}",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )

                logger.info(f"[Stock Channel Created] {inter.author} created stock channel for '{product_name}' in '{inter.guild.name}'")

            except disnake.Forbidden:
                await inter.response.send_message(
                    "❌ I don't have permission to create channels.",
                    ephemeral=True
                )

    @commands.slash_command(
        description="Delete a stock display channel for a product (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def delete_stock_channel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        product_name: str
    ):
        """Deletes the stock display channel for a product"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can delete stock channels.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            stock_channel = await conn.fetchrow(
                "SELECT channel_id FROM stock_channels WHERE guild_id = $1 AND product_name = $2",
                str(inter.guild.id), product_name
            )
            
            if not stock_channel:
                await inter.response.send_message(
                    f"❌ No stock channel found for '{product_name}'.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

            channel = inter.guild.get_channel(int(stock_channel["channel_id"]))
            
            try:
                if channel:
                    await channel.delete(reason=f"Stock channel deleted by {inter.author}")
                
                # Remove from database
                await conn.execute(
                    "DELETE FROM stock_channels WHERE guild_id = $1 AND product_name = $2",
                    str(inter.guild.id), product_name
                )

                await inter.response.send_message(
                    f"✅ Stock channel for '{product_name}' has been deleted.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )

                logger.info(f"[Stock Channel Deleted] {inter.author} deleted stock channel for '{product_name}' in '{inter.guild.name}'")

            except disnake.Forbidden:
                await inter.response.send_message(
                    "❌ I don't have permission to delete that channel.",
                    ephemeral=True
                )

    async def update_stock_channel(self, guild_id, product_name, new_stock):
        """Updates the stock display channel name and embed when stock changes"""
        async with (await get_database_pool()).acquire() as conn:
            stock_channel_data = await conn.fetchrow(
                "SELECT channel_id FROM stock_channels WHERE guild_id = $1 AND product_name = $2",
                str(guild_id), product_name
            )
            
            if not stock_channel_data:
                return

            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return

            channel = guild.get_channel(int(stock_channel_data["channel_id"]))
            if not channel:
                # Clean up stale record
                await conn.execute(
                    "DELETE FROM stock_channels WHERE guild_id = $1 AND product_name = $2",
                    str(guild_id), product_name
                )
                return

            # Update channel name
            if new_stock == -1:
                new_name = f"♾️┃{product_name.lower().replace(' ', '-')}"
            elif new_stock == 0:
                new_name = f"🔴┃sold-out-{product_name.lower().replace(' ', '-')}"
            else:
                new_name = f"📦┃{new_stock}-{product_name.lower().replace(' ', '-')}"

            try:
                if channel.name != new_name:
                    await channel.edit(name=new_name)

                # Update the embed in the channel
                embed = disnake.Embed(
                    title=f"📊 {product_name} - Stock Monitor",
                    description=(
                        "This channel displays the current stock level for this product.\n\n"
                        f"**Current Stock:** {new_stock if new_stock != -1 else 'Unlimited'}\n"
                        f"**Last Updated:** <t:{int(disnake.utils.utcnow().timestamp())}:F>\n\n"
                        "*This channel updates automatically when stock changes.*"
                    ),
                    color=disnake.Color.green() if new_stock > 0 or new_stock == -1 else disnake.Color.red()
                )
                embed.set_footer(text="Stock management powered by KeyVerify")
                
                # Try to edit the first message (the stock info message)
                async for message in channel.history(limit=10, oldest_first=True):
                    if message.author == guild.me and message.embeds:
                        await message.edit(embed=embed)
                        break

            except disnake.Forbidden:
                logger.warning(f"[Stock Channel Update Failed] No permission to update stock channel for '{product_name}' in '{guild.name}'")
            except Exception as e:
                logger.error(f"[Stock Channel Update Error] Failed to update stock channel: {e}")

def setup(bot):
    bot.add_cog(StockManagement(bot))
