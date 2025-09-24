# Create this new file: cogs/role_management.py

import disnake
from disnake.ext import commands
from utils.database import get_database_pool
import config
import logging

logger = logging.getLogger(__name__)

class RoleManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.setup_table())
        
    async def setup_table(self):
        """Creates table for storing role permissions"""
        await self.bot.wait_until_ready()
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS role_permissions (
                    guild_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    permission_type TEXT NOT NULL,
                    PRIMARY KEY (guild_id, role_id, permission_type)
                );
            """)

    @commands.slash_command(
        description="Set role permissions for bot functions (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def set_role_permissions(self, inter: disnake.ApplicationCommandInteraction):
        """Set permissions for roles"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can manage role permissions.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Get all roles (excluding @everyone and bot roles)
        role_options = [
            disnake.SelectOption(label=role.name, value=str(role.id), description=f"Members: {len(role.members)}")
            for role in inter.guild.roles 
            if role != inter.guild.default_role and not role.managed and role < inter.guild.me.top_role
        ][:25]  # Discord limit

        if not role_options:
            await inter.response.send_message(
                "❌ No suitable roles found. Create some roles first.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        dropdown = disnake.ui.StringSelect(
            placeholder="Select a role to configure...",
            options=role_options
        )
        
        async def role_selected(select_inter):
            role_id = select_inter.data["values"][0]
            role = inter.guild.get_role(int(role_id))
            await select_inter.response.send_message(
                f"Configure permissions for **{role.name}**:",
                view=PermissionConfigView(role_id, role.name),
                ephemeral=True
            )

        dropdown.callback = role_selected
        view = disnake.ui.View()
        view.add_item(dropdown)

        await inter.response.send_message(
            "🛡️ **Role Permission Manager**\nSelect a role to configure:",
            view=view,
            ephemeral=True,
            delete_after=config.message_timeout
        )

    @commands.slash_command(
        description="View current role permissions (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def view_role_permissions(self, inter: disnake.ApplicationCommandInteraction):
        """View all role permissions"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can view role permissions.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            permissions = await conn.fetch(
                "SELECT role_id, permission_type FROM role_permissions WHERE guild_id = $1 ORDER BY role_id",
                str(inter.guild.id)
            )

        if not permissions:
            await inter.response.send_message(
                "📋 No role permissions set. Use `/set_role_permissions` to configure roles.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        embed = disnake.Embed(
            title="🛡️ Role Permissions Overview",
            color=disnake.Color.blue()
        )

        # Group by role
        role_perms = {}
        for perm in permissions:
            role_id = perm["role_id"]
            if role_id not in role_perms:
                role_perms[role_id] = []
            role_perms[role_id].append(perm["permission_type"])

        # Format for display
        for role_id, perms in role_perms.items():
            role = inter.guild.get_role(int(role_id))
            if role:
                perm_list = ", ".join([PERMISSION_NAMES.get(p, p) for p in perms])
                embed.add_field(
                    name=f"🎭 {role.name}",
                    value=perm_list,
                    inline=False
                )

        embed.set_footer(text="Server Owner has all permissions by default")
        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.slash_command(
        description="Remove all permissions from a role (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def remove_role_permissions(self, inter: disnake.ApplicationCommandInteraction):
        """Remove permissions from a role"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can remove role permissions.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Get roles with permissions
        async with (await get_database_pool()).acquire() as conn:
            role_ids = await conn.fetch(
                "SELECT DISTINCT role_id FROM role_permissions WHERE guild_id = $1",
                str(inter.guild.id)
            )

        if not role_ids:
            await inter.response.send_message(
                "❌ No roles have permissions set.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        role_options = []
        for row in role_ids:
            role = inter.guild.get_role(int(row["role_id"]))
            if role:
                role_options.append(disnake.SelectOption(
                    label=role.name, 
                    value=str(role.id),
                    description="Remove all permissions"
                ))

        dropdown = disnake.ui.StringSelect(
            placeholder="Select role to remove permissions from...",
            options=role_options[:25]
        )
        
        async def remove_selected(select_inter):
            role_id = select_inter.data["values"][0]
            role = inter.guild.get_role(int(role_id))
            
            class ConfirmRemoveView(disnake.ui.View):
                def __init__(self):
                    super().__init__(timeout=30)

                @disnake.ui.button(label="✅ Remove All Permissions", style=disnake.ButtonStyle.danger)
                async def confirm(self, button, button_inter):
                    async with (await get_database_pool()).acquire() as conn:
                        await conn.execute(
                            "DELETE FROM role_permissions WHERE guild_id = $1 AND role_id = $2",
                            str(inter.guild.id), role_id
                        )
                    
                    await button_inter.response.send_message(
                        f"✅ Removed all permissions from **{role.name}**.",
                        ephemeral=True
                    )
                    self.stop()

                @disnake.ui.button(label="❌ Cancel", style=disnake.ButtonStyle.secondary)
                async def cancel(self, button, button_inter):
                    await button_inter.response.send_message("Cancelled.", ephemeral=True)
                    self.stop()
            
            view = ConfirmRemoveView()
            await select_inter.response.send_message(
                f"⚠️ Remove all permissions from **{role.name}**?",
                view=view,
                ephemeral=True
            )

        dropdown.callback = remove_selected
        view = disnake.ui.View()
        view.add_item(dropdown)

        await inter.response.send_message(
            "🗑️ Select role to remove permissions from:",
            view=view,
            ephemeral=True,
            delete_after=config.message_timeout
        )


# Permission types
PERMISSIONS = {
    "manage_products": "Product Management",
    "manage_tickets": "Ticket Management", 
    "handle_tickets": "Handle Support Tickets",
    "manage_stock": "Stock Management",
    "manage_categories": "Ticket Categories",
    "manage_messages": "Custom Messages",
    "view_admin": "View Admin Commands",
    "manage_verification": "Verification System"
}

PERMISSION_NAMES = PERMISSIONS

class PermissionConfigView(disnake.ui.View):
    def __init__(self, role_id, role_name):
        super().__init__(timeout=300)
        self.role_id = role_id
        self.role_name = role_name

    @disnake.ui.button(label="🎁 Product Management", style=disnake.ButtonStyle.secondary, row=0)
    async def manage_products(self, button, inter):
        await self.toggle_permission(inter, "manage_products")

    @disnake.ui.button(label="🎫 Ticket Management", style=disnake.ButtonStyle.secondary, row=0)
    async def manage_tickets(self, button, inter):
        await self.toggle_permission(inter, "manage_tickets")

    @disnake.ui.button(label="🛠️ Handle Tickets", style=disnake.ButtonStyle.secondary, row=0)
    async def handle_tickets(self, button, inter):
        await self.toggle_permission(inter, "handle_tickets")

    @disnake.ui.button(label="📦 Stock Management", style=disnake.ButtonStyle.secondary, row=1)
    async def manage_stock(self, button, inter):
        await self.toggle_permission(inter, "manage_stock")

    @disnake.ui.button(label="📂 Ticket Categories", style=disnake.ButtonStyle.secondary, row=1)
    async def manage_categories(self, button, inter):
        await self.toggle_permission(inter, "manage_categories")

    @disnake.ui.button(label="📝 Custom Messages", style=disnake.ButtonStyle.secondary, row=1)
    async def manage_messages(self, button, inter):
        await self.toggle_permission(inter, "manage_messages")

    @disnake.ui.button(label="🔑 Verification System", style=disnake.ButtonStyle.secondary, row=2)
    async def manage_verification(self, button, inter):
        await self.toggle_permission(inter, "manage_verification")

    @disnake.ui.button(label="👁️ View Admin Commands", style=disnake.ButtonStyle.secondary, row=2)
    async def view_admin(self, button, inter):
        await self.toggle_permission(inter, "view_admin")

    @disnake.ui.button(label="✅ Save & Exit", style=disnake.ButtonStyle.green, row=3)
    async def save_exit(self, button, inter):
        await inter.response.send_message(
            f"✅ Permissions saved for **{self.role_name}**!",
            ephemeral=True
        )
        self.stop()

    async def toggle_permission(self, inter, permission_type):
        async with (await get_database_pool()).acquire() as conn:
            # Check if permission exists
            existing = await conn.fetchrow(
                "SELECT 1 FROM role_permissions WHERE guild_id = $1 AND role_id = $2 AND permission_type = $3",
                str(inter.guild.id), self.role_id, permission_type
            )

            if existing:
                # Remove permission
                await conn.execute(
                    "DELETE FROM role_permissions WHERE guild_id = $1 AND role_id = $2 AND permission_type = $3",
                    str(inter.guild.id), self.role_id, permission_type
                )
                status = "❌ Removed"
            else:
                # Add permission
                await conn.execute(
                    "INSERT INTO role_permissions (guild_id, role_id, permission_type) VALUES ($1, $2, $3)",
                    str(inter.guild.id), self.role_id, permission_type
                )
                status = "✅ Added"

        await inter.response.send_message(
            f"{status} **{PERMISSIONS[permission_type]}** for **{self.role_name}**",
            ephemeral=True,
            delete_after=3
        )


# Utility function to check permissions
async def has_permission(user, guild, permission_type):
    """Check if user has specific permission"""
    # Server owner always has all permissions
    if user.id == guild.owner_id:
        return True

    async with (await get_database_pool()).acquire() as conn:
        # Check if any of user's roles have the permission
        user_role_ids = [str(role.id) for role in user.roles]
        if not user_role_ids:
            return False

        result = await conn.fetchrow(
            "SELECT 1 FROM role_permissions WHERE guild_id = $1 AND role_id = ANY($2) AND permission_type = $3",
            str(guild.id), user_role_ids, permission_type
        )
        return result is not None


def setup(bot):
    bot.add_cog(RoleManagement(bot))
