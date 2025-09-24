# Add this new file: cogs/ticket_categories.py

import disnake
from disnake.ext import commands
from utils.database import get_database_pool
import config
import logging

logger = logging.getLogger(__name__)

class TicketCategories(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.setup_table())
        
    async def setup_table(self):
        """Creates table for storing custom ticket categories"""
        await self.bot.wait_until_ready()
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_categories (
                    guild_id TEXT NOT NULL,
                    category_name TEXT NOT NULL,
                    category_description TEXT NOT NULL,
                    display_order INTEGER NOT NULL DEFAULT 0,
                    emoji TEXT DEFAULT '🎫',
                    PRIMARY KEY (guild_id, category_name)
                );
            """)

    @commands.slash_command(
        description="Add a custom ticket category (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def add_ticket_category(self, inter: disnake.ApplicationCommandInteraction):
        """Add a new custom ticket category"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can manage ticket categories.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        await inter.response.send_modal(AddCategoryModal())

    @commands.slash_command(
        description="Edit an existing ticket category (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def edit_ticket_category(self, inter: disnake.ApplicationCommandInteraction):
        """Edit an existing ticket category"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can manage ticket categories.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Get existing categories
        async with (await get_database_pool()).acquire() as conn:
            categories = await conn.fetch(
                "SELECT category_name FROM ticket_categories WHERE guild_id = $1 ORDER BY display_order",
                str(inter.guild.id)
            )

        if not categories:
            await inter.response.send_message(
                "❌ No custom ticket categories found. Use `/add_ticket_category` first.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Create dropdown for category selection
        options = [
            disnake.SelectOption(label=cat["category_name"], value=cat["category_name"])
            for cat in categories[:25]  # Discord limit
        ]

        dropdown = disnake.ui.StringSelect(
            placeholder="Select a category to edit...",
            options=options
        )
        
        async def edit_selected(select_inter):
            category_name = select_inter.data["values"][0]
            
            # Get category data
            async with (await get_database_pool()).acquire() as conn:
                cat_data = await conn.fetchrow(
                    "SELECT * FROM ticket_categories WHERE guild_id = $1 AND category_name = $2",
                    str(inter.guild.id), category_name
                )
            
            if cat_data:
                await select_inter.response.send_modal(EditCategoryModal(cat_data))
            else:
                await select_inter.response.send_message("❌ Category not found.", ephemeral=True)

        dropdown.callback = edit_selected
        view = disnake.ui.View()
        view.add_item(dropdown)

        await inter.response.send_message(
            "📝 Select a category to edit:",
            view=view,
            ephemeral=True,
            delete_after=config.message_timeout
        )

    @commands.slash_command(
        description="Remove a ticket category (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def remove_ticket_category(self, inter: disnake.ApplicationCommandInteraction):
        """Remove a ticket category"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can manage ticket categories.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Get existing categories
        async with (await get_database_pool()).acquire() as conn:
            categories = await conn.fetch(
                "SELECT category_name FROM ticket_categories WHERE guild_id = $1 ORDER BY display_order",
                str(inter.guild.id)
            )

        if not categories:
            await inter.response.send_message(
                "❌ No custom ticket categories found.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        options = [
            disnake.SelectOption(label=cat["category_name"], value=cat["category_name"])
            for cat in categories[:25]
        ]

        dropdown = disnake.ui.StringSelect(
            placeholder="Select a category to remove...",
            options=options
        )
        
        async def remove_selected(select_inter):
            category_name = select_inter.data["values"][0]
            
            class ConfirmRemoveView(disnake.ui.View):
                def __init__(self):
                    super().__init__(timeout=30)

                @disnake.ui.button(label="✅ Confirm Remove", style=disnake.ButtonStyle.danger)
                async def confirm(self, button, button_inter):
                    async with (await get_database_pool()).acquire() as conn:
                        await conn.execute(
                            "DELETE FROM ticket_categories WHERE guild_id = $1 AND category_name = $2",
                            str(inter.guild.id), category_name
                        )
                    
                    await button_inter.response.send_message(f"✅ Category '{category_name}' removed.", ephemeral=True)
                    self.stop()

                @disnake.ui.button(label="❌ Cancel", style=disnake.ButtonStyle.secondary)
                async def cancel(self, button, button_inter):
                    await button_inter.response.send_message("Removal cancelled.", ephemeral=True)
                    self.stop()
            
            view = ConfirmRemoveView()
            await select_inter.response.send_message(
                f"⚠️ Are you sure you want to remove **'{category_name}'**?",
                view=view,
                ephemeral=True
            )

        dropdown.callback = remove_selected
        view = disnake.ui.View()
        view.add_item(dropdown)

        await inter.response.send_message(
            "🗑️ Select a category to remove:",
            view=view,
            ephemeral=True,
            delete_after=config.message_timeout
        )

    @commands.slash_command(
        description="List all ticket categories and their display order (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def list_ticket_categories(self, inter: disnake.ApplicationCommandInteraction):
        """List all ticket categories"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can view ticket categories.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            categories = await conn.fetch(
                "SELECT category_name, category_description, display_order, emoji FROM ticket_categories WHERE guild_id = $1 ORDER BY display_order",
                str(inter.guild.id)
            )

        if not categories:
            await inter.response.send_message(
                "📝 No custom ticket categories found.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        embed = disnake.Embed(
            title="🎫 Ticket Categories",
            description="Categories are shown in this order in the ticket dropdown:",
            color=disnake.Color.blurple()
        )

        category_list = []
        for i, cat in enumerate(categories, 1):
            emoji = cat["emoji"] or "🎫"
            category_list.append(
                f"**{i}.** {emoji} **{cat['category_name']}**\n"
                f"└ {cat['category_description']}"
            )

        embed.add_field(
            name="Custom Categories",
            value="\n\n".join(category_list) if category_list else "None",
            inline=False
        )

        embed.add_field(
            name="📋 Note",
            value="Products (if any) will appear after these categories in the dropdown.",
            inline=False
        )

        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.slash_command(
        description="Reorder ticket categories (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def reorder_ticket_categories(self, inter: disnake.ApplicationCommandInteraction):
        """Reorder ticket categories"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can reorder ticket categories.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        await inter.response.send_modal(ReorderCategoriesModal())


class AddCategoryModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Category Name",
                custom_id="category_name",
                placeholder="e.g., 'General Support' or 'Bug Reports'",
                style=disnake.TextInputStyle.short,
                max_length=50,
            ),
            disnake.ui.TextInput(
                label="Category Description",
                custom_id="category_description",
                placeholder="e.g., 'General questions or issues'",
                style=disnake.TextInputStyle.short,
                max_length=100,
            ),
            disnake.ui.TextInput(
                label="Display Order",
                custom_id="display_order",
                placeholder="Lower numbers appear first (e.g., 1, 2, 3...)",
                style=disnake.TextInputStyle.short,
                max_length=3,
            ),
            disnake.ui.TextInput(
                label="Emoji (Optional)",
                custom_id="emoji",
                placeholder="e.g., ❓ or 🐛 or 💬",
                style=disnake.TextInputStyle.short,
                max_length=10,
                required=False
            )
        ]
        super().__init__(title="Add Ticket Category", components=components)

    async def callback(self, interaction: disnake.ModalInteraction):
        category_name = interaction.text_values["category_name"].strip()
        category_description = interaction.text_values["category_description"].strip()
        display_order_str = interaction.text_values["display_order"].strip()
        emoji = interaction.text_values.get("emoji", "🎫").strip() or "🎫"

        # Validate display order
        try:
            display_order = int(display_order_str)
        except ValueError:
            await interaction.response.send_message(
                "❌ Display order must be a number (e.g., 1, 2, 3).",
                ephemeral=True
            )
            return

        # Save to database
        async with (await get_database_pool()).acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO ticket_categories (guild_id, category_name, category_description, display_order, emoji)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    str(interaction.guild.id), category_name, category_description, display_order, emoji
                )
                
                await interaction.response.send_message(
                    f"✅ Category **'{category_name}'** added successfully!\n"
                    f"📋 Use `/update_ticket_boxes` to refresh existing ticket boxes.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                
                logger.info(f"[Category Added] '{category_name}' added to '{interaction.guild.name}' by {interaction.author}")
                
            except Exception as e:
                await interaction.response.send_message(
                    f"❌ A category named '{category_name}' already exists.",
                    ephemeral=True
                )


class EditCategoryModal(disnake.ui.Modal):
    def __init__(self, cat_data):
        self.category_name = cat_data["category_name"]
        
        components = [
            disnake.ui.TextInput(
                label="Category Description",
                custom_id="category_description",
                value=cat_data["category_description"],
                style=disnake.TextInputStyle.short,
                max_length=100,
            ),
            disnake.ui.TextInput(
                label="Display Order",
                custom_id="display_order",
                value=str(cat_data["display_order"]),
                style=disnake.TextInputStyle.short,
                max_length=3,
            ),
            disnake.ui.TextInput(
                label="Emoji",
                custom_id="emoji",
                value=cat_data["emoji"] or "🎫",
                style=disnake.TextInputStyle.short,
                max_length=10,
            )
        ]
        super().__init__(title=f"Edit: {self.category_name}", components=components)

    async def callback(self, interaction: disnake.ModalInteraction):
        category_description = interaction.text_values["category_description"].strip()
        display_order_str = interaction.text_values["display_order"].strip()
        emoji = interaction.text_values["emoji"].strip() or "🎫"

        # Validate display order
        try:
            display_order = int(display_order_str)
        except ValueError:
            await interaction.response.send_message(
                "❌ Display order must be a number.",
                ephemeral=True
            )
            return

        # Update database
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute(
                """
                UPDATE ticket_categories 
                SET category_description = $1, display_order = $2, emoji = $3
                WHERE guild_id = $4 AND category_name = $5
                """,
                category_description, display_order, emoji, str(interaction.guild.id), self.category_name
            )

        await interaction.response.send_message(
            f"✅ Category **'{self.category_name}'** updated!\n"
            f"📋 Use `/update_ticket_boxes` to refresh existing ticket boxes.",
            ephemeral=True,
            delete_after=config.message_timeout
        )


class ReorderCategoriesModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Category Order",
                custom_id="category_order",
                placeholder="Enter category names in order, separated by commas",
                style=disnake.TextInputStyle.paragraph,
                max_length=1000,
            )
        ]
        super().__init__(title="Reorder Categories", components=components)

    async def callback(self, interaction: disnake.ModalInteraction):
        category_order = interaction.text_values["category_order"].strip()
        category_names = [name.strip() for name in category_order.split(",") if name.strip()]

        if not category_names:
            await interaction.response.send_message(
                "❌ Please provide at least one category name.",
                ephemeral=True
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            # Get existing categories
            existing_cats = await conn.fetch(
                "SELECT category_name FROM ticket_categories WHERE guild_id = $1",
                str(interaction.guild.id)
            )
            existing_names = {cat["category_name"] for cat in existing_cats}

            # Check if all provided names exist
            invalid_names = [name for name in category_names if name not in existing_names]
            if invalid_names:
                await interaction.response.send_message(
                    f"❌ Invalid category names: {', '.join(invalid_names)}",
                    ephemeral=True
                )
                return

            # Update display orders
            for i, category_name in enumerate(category_names, 1):
                await conn.execute(
                    "UPDATE ticket_categories SET display_order = $1 WHERE guild_id = $2 AND category_name = $3",
                    i, str(interaction.guild.id), category_name
                )

        await interaction.response.send_message(
            f"✅ Categories reordered successfully!\n"
            f"📋 Use `/update_ticket_boxes` to refresh existing ticket boxes.",
            ephemeral=True,
            delete_after=config.message_timeout
        )


def setup(bot):
    bot.add_cog(TicketCategories(bot))
