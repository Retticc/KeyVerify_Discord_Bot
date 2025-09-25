import disnake
from disnake.ext import commands
from utils.database import get_database_pool, fetch_products
from utils.permissions import owner_or_permission, has_permission
import config
import logging
import asyncio

logger = logging.getLogger(__name__)

class ReviewSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.setup_tables())
        
    async def setup_tables(self):
        """Creates tables for the review system"""
        await self.bot.wait_until_ready()
        async with (await get_database_pool()).acquire() as conn:
            # Review settings table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS review_settings (
                    guild_id TEXT PRIMARY KEY,
                    review_channel_id TEXT NOT NULL
                );
            """)
            
            # Pending reviews table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_reviews (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id, product_name)
                );
            """)

    @commands.slash_command(
        description="Set the channel where reviews will be posted (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @owner_or_permission("manage_bot_settings")
    async def set_review_channel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        channel: disnake.TextChannel
    ):
        """Set the channel where reviews will be posted"""
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute(
                """
                INSERT INTO review_settings (guild_id, review_channel_id)
                VALUES ($1, $2)
                ON CONFLICT (guild_id)
                DO UPDATE SET review_channel_id = $2
                """,
                str(inter.guild.id), str(channel.id)
            )

        await inter.response.send_message(
            f"✅ Review channel set to {channel.mention}",
            ephemeral=True,
            delete_after=config.message_timeout
        )

    @commands.slash_command(
        description="Request a review from a user for a specific product (staff only).",
        default_member_permissions=disnake.Permissions(manage_channels=True),
    )
    async def request_review(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user: disnake.Member,
        product_name: str
    ):
        """Request a review from a user - can only be used by staff with permissions"""
        # Check if user has permission to request reviews
        if not (inter.author.id == inter.guild.owner_id or 
                await has_permission(inter.author, inter.guild, "handle_tickets") or
                await has_permission(inter.author, inter.guild, "manage_tickets")):
            await inter.response.send_message(
                "❌ You don't have permission to request reviews. Required: **Handle Tickets** or **Ticket Management** permission.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Check if review channel is set
        async with (await get_database_pool()).acquire() as conn:
            review_channel_data = await conn.fetchrow(
                "SELECT review_channel_id FROM review_settings WHERE guild_id = $1",
                str(inter.guild.id)
            )

        if not review_channel_data:
            await inter.response.send_message(
                "❌ No review channel set. Use `/set_review_channel` first.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        review_channel = inter.guild.get_channel(int(review_channel_data["review_channel_id"]))
        if not review_channel:
            await inter.response.send_message(
                "❌ Review channel no longer exists. Please set a new one.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Check if product exists
        products = await fetch_products(str(inter.guild.id))
        if product_name not in products:
            await inter.response.send_message(
                f"❌ Product '{product_name}' not found.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Check if user already has a pending review for this product
        async with (await get_database_pool()).acquire() as conn:
            existing_review = await conn.fetchrow(
                "SELECT 1 FROM pending_reviews WHERE guild_id = $1 AND user_id = $2 AND product_name = $3",
                str(inter.guild.id), str(user.id), product_name
            )

            if existing_review:
                await inter.response.send_message(
                    f"❌ {user.mention} already has a pending review request for **{product_name}**.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

            # Store pending review
            await conn.execute(
                """
                INSERT INTO pending_reviews (guild_id, user_id, product_name, requested_by)
                VALUES ($1, $2, $3, $4)
                """,
                str(inter.guild.id), str(user.id), product_name, str(inter.author.id)
            )

        # Create review request embed
        embed = disnake.Embed(
            title="⭐ Review Request",
            description=(
                f"Hey {user.mention}! 🎉\n\n"
                f"We'd love to hear about your experience with **{product_name}**!\n"
                f"Your feedback helps us improve and helps other customers make informed decisions."
            ),
            color=disnake.Color.gold()
        )
        embed.add_field(
            name="📝 How to Review",
            value=(
                "Click the **Leave Review** button below to:\n"
                "• Rate your experience (1-5 stars)\n"
                "• Share your thoughts (optional)\n"
                "• Help our community!"
            ),
            inline=False
        )
        embed.add_field(
            name="🎁 Product",
            value=f"**{product_name}**",
            inline=True
        )
        embed.add_field(
            name="👤 Requested by",
            value=f"{inter.author.mention}",
            inline=True
        )
        embed.set_footer(text="Your review will be posted in this channel • Powered by KeyVerify")

        # Create review button
        view = ReviewRequestView(str(inter.guild.id), str(user.id), product_name)
        
        try:
            await review_channel.send(embed=embed, view=view)
            
            await inter.response.send_message(
                f"✅ Review request sent to {user.mention} in {review_channel.mention} for **{product_name}**",
                ephemeral=True,
                delete_after=config.message_timeout
            )

            logger.info(f"[Review Requested] {inter.author} requested review from {user} for '{product_name}' in '{inter.guild.name}'")

        except disnake.Forbidden:
            await inter.response.send_message(
                "❌ I don't have permission to send messages in the review channel.",
                ephemeral=True
            )

class ReviewRequestView(disnake.ui.View):
    def __init__(self, guild_id, user_id, product_name):
        super().__init__(timeout=None)  # Persistent view
        self.guild_id = guild_id
        self.user_id = user_id
        self.product_name = product_name

    @disnake.ui.button(label="⭐ Leave Review", style=disnake.ButtonStyle.primary, emoji="⭐")
    async def leave_review(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        # Only allow the specific user to review
        if str(inter.author.id) != self.user_id:
            await inter.response.send_message(
                "❌ This review request is not for you.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Check if review is still pending
        async with (await get_database_pool()).acquire() as conn:
            pending = await conn.fetchrow(
                "SELECT 1 FROM pending_reviews WHERE guild_id = $1 AND user_id = $2 AND product_name = $3",
                self.guild_id, self.user_id, self.product_name
            )

        if not pending:
            await inter.response.send_message(
                "❌ This review request has expired or been completed.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Open review modal
        await inter.response.send_modal(ReviewModal(self.guild_id, self.user_id, self.product_name))

class ReviewModal(disnake.ui.Modal):
    def __init__(self, guild_id, user_id, product_name):
        self.guild_id = guild_id
        self.user_id = user_id
        self.product_name = product_name

        components = [
            disnake.ui.TextInput(
                label="Rating (1-5 stars)",
                custom_id="rating",
                placeholder="Enter a number from 1 to 5",
                style=disnake.TextInputStyle.short,
                max_length=1,
            ),
            disnake.ui.TextInput(
                label="Review Description (Optional)",
                custom_id="description",
                placeholder="Tell us about your experience with this product...",
                style=disnake.TextInputStyle.paragraph,
                max_length=1000,
                required=False
            )
        ]
        super().__init__(title=f"Review: {product_name}", components=components)

    async def callback(self, interaction: disnake.ModalInteraction):
        rating_str = interaction.text_values["rating"].strip()
        description = interaction.text_values.get("description", "").strip()

        # Validate rating
        try:
            rating = int(rating_str)
            if rating < 1 or rating > 5:
                raise ValueError("Rating must be between 1 and 5")
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid rating (1, 2, 3, 4, or 5).",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Remove from pending reviews
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute(
                "DELETE FROM pending_reviews WHERE guild_id = $1 AND user_id = $2 AND product_name = $3",
                self.guild_id, self.user_id, self.product_name
            )

        # Create star display
        stars = "⭐" * rating + "☆" * (5 - rating)
        
        # Create review embed
        embed = disnake.Embed(
            title="⭐ New Customer Review",
            color=disnake.Color.gold()
        )
        embed.add_field(
            name="🎁 Product",
            value=f"**{self.product_name}**",
            inline=True
        )
        embed.add_field(
            name="⭐ Rating",
            value=f"{stars} ({rating}/5)",
            inline=True
        )
        embed.add_field(
            name="👤 Reviewer",
            value=f"{interaction.author.mention}",
            inline=True
        )
        
        if description:
            embed.add_field(
                name="💭 Review",
                value=f'"{description}"',
                inline=False
            )
        
        embed.set_thumbnail(url=interaction.author.display_avatar.url)
        embed.set_footer(text="Powered by KeyVerify")
        embed.timestamp = interaction.created_at

        # Post the review
        await interaction.channel.send(embed=embed)
        
        await interaction.response.send_message(
            f"✅ Thank you for your {rating}-star review of **{self.product_name}**! 🎉",
            ephemeral=True,
            delete_after=config.message_timeout
        )

        logger.info(f"[Review Posted] {interaction.author} left {rating}-star review for '{self.product_name}' in '{interaction.guild.name}'")

def setup(bot):
    bot.add_cog(ReviewSystem(bot))
