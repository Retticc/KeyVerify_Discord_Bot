# Create cogs/enhanced_auto_roles.py

import disnake
from disnake.ext import commands
from utils.database import get_database_pool, fetch_products
from utils.permissions import requires_permission, owner_or_permission
import config
import logging

logger = logging.getLogger(__name__)

class EnhancedAutoRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    @commands.slash_command(
        description="Set product-specific auto-roles for verified users (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @owner_or_permission("manage_auto_roles")
    async def set_product_auto_roles(self, inter: disnake.ApplicationCommandInteraction):
        """Configure product-specific auto-roles"""
        # Get all products for this guild
        products = await fetch_products(str(inter.guild.id))
        
        if not products:
            await inter.response.send_message(
                "❌ No products found. Add products first with `/add_product`.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Create product selection dropdown
        product_options = [
            disnake.SelectOption(
                label=product_name, 
                value=product_name,
                description=f"Configure auto-roles for {product_name}"
            )
            for product_name in products.keys()
        ][:25]  # Discord limit

        dropdown = disnake.ui.StringSelect(
            placeholder="Select a product to configure auto-roles...",
            options=product_options
        )
        
        async def product_selected(select_inter):
            product_name = select_inter.data["values"][0]
            await select_inter.response.send_message(
                f"Configure auto-roles for **{product_name}**:",
                view=ProductAutoRoleView(product_name),
                ephemeral=True
            )

        dropdown.callback = product_selected
        view = disnake.ui.View()
        view.add_item(dropdown)

        await inter.response.send_message(
            "🎁 **Product Auto-Role Configuration**\nSelect a product:",
            view=view,
            ephemeral=True,
            delete_after=config.message_timeout
        )

    @commands.slash_command(
        description="View all auto-role configurations (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @owner_or_permission("manage_auto_roles")
    async def view_all_auto_roles(self, inter: disnake.ApplicationCommandInteraction):
        """View comprehensive auto-role settings"""
        async with (await get_database_pool()).acquire() as conn:
            auto_roles = await conn.fetch(
                "SELECT role_type, role_id, product_name FROM auto_roles WHERE guild_id = $1 ORDER BY role_type, product_name",
                str(inter.guild.id)
            )

        if not auto_roles:
            await inter.response.send_message(
                "📋 No auto-roles configured. Use `/set_auto_roles` or `/set_product_auto_roles` to set them up.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        embed = disnake.Embed(
            title="⚙️ All Auto-Role Configurations",
            color=disnake.Color.blue()
        )

        # Group by role type
        role_groups = {}
        for auto_role in auto_roles:
            role_type = auto_role["role_type"]
            if role_type not in role_groups:
                role_groups[role_type] = []
            role_groups[role_type].append(auto_role)

        for role_type, roles in role_groups.items():
            role_texts = []
            for role_data in roles:
                role = inter.guild.get_role(int(role_data["role_id"]))
                if role:
                    if role_data["product_name"]:
                        role_texts.append(f"**{role_data['product_name']}:** {role.mention}")
                    else:
                        role_texts.append(f"**General:** {role.mention}")

            if role_texts:
                emoji = "👋" if role_type == "join" else "✅"
                embed.add_field(
                    name=f"{emoji} {role_type.title()} Roles",
                    value="\n".join(role_texts),
                    inline=False
                )

        embed.set_footer(text="Use the respective commands to modify these settings")
        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.slash_command(
        description="Remove product-specific auto-roles (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @owner_or_permission("manage_auto_roles")
    async def remove_product_auto_roles(self, inter: disnake.ApplicationCommandInteraction):
        """Remove product-specific auto-roles"""
        async with (await get_database_pool()).acquire() as conn:
            product_auto_roles = await conn.fetch(
                "SELECT DISTINCT product_name FROM auto_roles WHERE guild_id = $1 AND product_name IS NOT NULL",
                str(inter.guild.id)
            )

        if not product_auto_roles:
            await inter.response.send_message(
                "❌ No product-specific auto-roles found.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        product_options = [
            disnake.SelectOption(
                label=row["product_name"], 
                value=row["product_name"],
                description="Remove auto-roles for this product"
            )
            for row in product_auto_roles
        ]

        dropdown = disnake.ui.StringSelect(
            placeholder="Select product to remove auto-roles from...",
            options=product_options
        )
        
        async def remove_selected(select_inter):
            product_name = select_inter.data["values"][0]
            
            class ConfirmRemoveView(disnake.ui.View):
                def __init__(self):
                    super().__init__(timeout=30)

                @disnake.ui.button(label="✅ Confirm Remove", style=disnake.ButtonStyle.danger)
                async def confirm(self, button, button_inter):
                    async with (await get_database_pool()).acquire() as conn:
                        await conn.execute(
                            "DELETE FROM auto_roles WHERE guild_id = $1 AND product_name = $2",
                            str(inter.guild.id), product_name
                        )
                    
                    await button_inter.response.send_message(
                        f"✅ Removed all auto-roles for **{product_name}**.",
                        ephemeral=True
                    )
                    self.stop()

                @disnake.ui.button(label="❌ Cancel", style=disnake.ButtonStyle.secondary)
                async def cancel(self, button, button_inter):
                    await button_inter.response.send_message("Removal cancelled.", ephemeral=True)
                    self.stop()
            
            view = ConfirmRemoveView()
            await select_inter.response.send_message(
                f"⚠️ Remove all auto-roles for **{product_name}**?",
                view=view,
                ephemeral=True
            )

        dropdown.callback = remove_selected
        view = disnake.ui.View()
        view.add_item(dropdown)

        await inter.response.send_message(
            "🗑️ Remove product auto-roles:",
            view=view,
            ephemeral=True,
            delete_after=config.message_timeout
        )

class ProductAutoRoleView(disnake.ui.View):
    def __init__(self, product_name):
        super().__init__(timeout=300)
        self.product_name = product_name

    @disnake.ui.button(label="➕ Add Auto-Role", style=disnake.ButtonStyle.green)
    async def add_auto_role(self, button, inter):
        await self.configure_auto_role(inter, "add")

    @disnake.ui.button(label="➖ Remove Auto-Role", style=disnake.ButtonStyle.red)
    async def remove_auto_role(self, button, inter):
        await self.configure_auto_role(inter, "remove")

    @disnake.ui.button(label="📋 View Current", style=disnake.ButtonStyle.secondary)
    async def view_current(self, button, inter):
        async with (await get_database_pool()).acquire() as conn:
            auto_roles = await conn.fetch(
                "SELECT role_id FROM auto_roles WHERE guild_id = $1 AND product_name = $2 AND role_type = $3",
                str(inter.guild.id), self.product_name, "verified"
            )

        if not auto_roles:
            await inter.response.send_message(
                f"📋 No auto-roles set for **{self.product_name}**.",
                ephemeral=True
            )
            return

        role_mentions = []
        for auto_role in auto_roles:
            role = inter.guild.get_role(int(auto_role["role_id"]))
            if role:
                role_mentions.append(role.mention)

        embed = disnake.Embed(
            title=f"🎁 Auto-Roles for {self.product_name}",
            description="\n".join(role_mentions),
            color=disnake.Color.blue()
        )

        await inter.response.send_message(embed=embed, ephemeral=True)

    async def configure_auto_role(self, inter, action):
        if action == "add":
            # Show roles to add
            role_options = [
                disnake.SelectOption(
                    label=role.name, 
                    value=str(role.id),
                    description=f"Add {role.name} as auto-role"
                )
                for role in inter.guild.roles 
                if role != inter.guild.default_role and not role.managed and role < inter.guild.me.top_role
            ][:25]

            dropdown = disnake.ui.StringSelect(
                placeholder="Select role to add as auto-role...",
                options=role_options
            )
            
            async def add_role_selected(select_inter):
                role_id = select_inter.data["values"][0]
                role = inter.guild.get_role(int(role_id))
                
                async with (await get_database_pool()).acquire() as conn:
                    try:
                        await conn.execute(
                            """
                            INSERT INTO auto_roles (guild_id, role_type, role_id, product_name)
                            VALUES ($1, $2, $3, $4)
                            """,
                            str(inter.guild.id), "verified", str(role.id), self.product_name
                        )
                        
                        await select_inter.response.send_message(
                            f"✅ Added {role.mention} as auto-role for **{self.product_name}**",
                            ephemeral=True
                        )
                    except:
                        await select_inter.response.send_message(
                            f"❌ {role.mention} is already an auto-role for **{self.product_name}**",
                            ephemeral=True
                        )

            dropdown.callback = add_role_selected
            
        else:  # remove
            # Show current auto-roles to remove
            async with (await get_database_pool()).acquire() as conn:
                auto_roles = await conn.fetch(
                    "SELECT role_id FROM auto_roles WHERE guild_id = $1 AND product_name = $2 AND role_type = $3",
                    str(inter.guild.id), self.product_name, "verified"
                )

            if not auto_roles:
                await inter.response.send_message(
                    f"❌ No auto-roles to remove for **{self.product_name}**.",
                    ephemeral=True
                )
                return

            role_options = []
            for auto_role in auto_roles:
                role = inter.guild.get_role(int(auto_role["role_id"]))
                if role:
                    role_options.append(disnake.SelectOption(
                        label=role.name,
                        value=str(role.id),
                        description=f"Remove {role.name} from auto-roles"
                    ))

            dropdown = disnake.ui.StringSelect(
                placeholder="Select role to remove from auto-roles...",
                options=role_options
            )
            
            async def remove_role_selected(select_inter):
                role_id = select_inter.data["values"][0]
                role = inter.guild.get_role(int(role_id))
                
                async with (await get_database_pool()).acquire() as conn:
                    await conn.execute(
                        "DELETE FROM auto_roles WHERE guild_id = $1 AND role_type = $2 AND role_id = $3 AND product_name = $4",
                        str(inter.guild.id), "verified", str(role_id), self.product_name
                    )
                
                await select_inter.response.send_message(
                    f"✅ Removed {role.mention} from auto-roles for **{self.product_name}**",
                    ephemeral=True
                )

            dropdown.callback = remove_role_selected

        view = disnake.ui.View()
        view.add_item(dropdown)
        
        action_text = "add to" if action == "add" else "remove from"
        await inter.response.send_message(
            f"Select role to {action_text} **{self.product_name}** auto-roles:",
            view=view,
            ephemeral=True
        )

def setup(bot):
    bot.add_cog(EnhancedAutoRoles(bot))
