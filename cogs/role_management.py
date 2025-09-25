# Replace cogs/role_management.py with this enhanced version

import disnake
from disnake.ext import commands
from utils.database import get_database_pool
import config
import logging

logger = logging.getLogger(__name__)

class EnhancedRoleManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.setup_table())
        
    async def setup_table(self):
        """Creates tables for storing role permissions and auto-roles"""
        await self.bot.wait_until_ready()
        async with (await get_database_pool()).acquire() as conn:
            # Role permissions table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS role_permissions (
                    guild_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    permission_type TEXT NOT NULL,
                    PRIMARY KEY (guild_id, role_id, permission_type)
                );
            """)
            
            # Auto-roles table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS auto_roles (
                    guild_id TEXT NOT NULL,
                    role_type TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    product_name TEXT DEFAULT '',
                    PRIMARY KEY (guild_id, role_type, role_id, product_name)
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
        description="Set auto-roles for joining members and verified users (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def set_auto_roles(self, inter: disnake.ApplicationCommandInteraction):
        """Configure auto-role assignment"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can manage auto-roles.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        embed = disnake.Embed(
            title="⚙️ Auto-Role Configuration",
            description="Choose what type of auto-role you want to configure:",
            color=disnake.Color.blue()
        )

        class AutoRoleTypeView(disnake.ui.View):
            def __init__(self):
                super().__init__(timeout=180)

            @disnake.ui.button(label="👋 Join Role", style=disnake.ButtonStyle.secondary, emoji="👋")
            async def join_role(self, button, button_inter):
                await self.configure_role_type(button_inter, "join", "Join Role")

            @disnake.ui.button(label="✅ Verified Role", style=disnake.ButtonStyle.secondary, emoji="✅")
            async def verified_role(self, button, button_inter):
                await self.configure_role_type(button_inter, "verified", "Verified Role")

            @disnake.ui.button(label="📋 View Current Settings", style=disnake.ButtonStyle.primary, emoji="📋")
            async def view_settings(self, button, button_inter):
                await self.show_current_settings(button_inter)

            async def configure_role_type(self, button_inter, role_type, role_type_name):
                role_options = [
                    disnake.SelectOption(label="❌ Remove Auto-Role", value="remove", description="Disable auto-role assignment")
                ] + [
                    disnake.SelectOption(label=role.name, value=str(role.id), description=f"Set as {role_type_name}")
                    for role in inter.guild.roles 
                    if role != inter.guild.default_role and not role.managed and role < inter.guild.me.top_role
                ][:24]

                dropdown = disnake.ui.StringSelect(
                    placeholder=f"Select role for {role_type_name}...",
                    options=role_options
                )
                
                async def role_selected(select_inter):
                    selected_value = select_inter.data["values"][0]
                    
                    async with (await get_database_pool()).acquire() as conn:
                        if selected_value == "remove":
                            await conn.execute(
                                "DELETE FROM auto_roles WHERE guild_id = $1 AND role_type = $2 AND product_name = $3",
                                str(inter.guild.id), role_type, ''
                            )
                            await select_inter.response.send_message(
                                f"✅ {role_type_name} disabled.",
                                ephemeral=True
                            )
                        else:
                            role = inter.guild.get_role(int(selected_value))
                            await conn.execute(
                                """
                                INSERT INTO auto_roles (guild_id, role_type, role_id, product_name)
                                VALUES ($1, $2, $3, $4)
                                ON CONFLICT (guild_id, role_type, role_id, product_name)
                                DO NOTHING
                                """,
                                str(inter.guild.id), role_type, str(role.id), ''
                            )
                            await select_inter.response.send_message(
                                f"✅ {role_type_name} set to {role.mention}",
                                ephemeral=True
                            )

                dropdown.callback = role_selected
                view = disnake.ui.View()
                view.add_item(dropdown)

                await button_inter.response.send_message(
                    f"Select role for **{role_type_name}**:",
                    view=view,
                    ephemeral=True
                )

            async def show_current_settings(self, button_inter):
                async with (await get_database_pool()).acquire() as conn:
                    auto_roles = await conn.fetch(
                        "SELECT role_type, role_id FROM auto_roles WHERE guild_id = $1 AND product_name = $2",
                        str(inter.guild.id), ''
                    )

                embed = disnake.Embed(
                    title="📋 Current Auto-Role Settings",
                    color=disnake.Color.blue()
                )

                settings = {
                    "join": "👋 **Join Role:** ",
                    "verified": "✅ **Verified Role:** "
                }

                for role_type, description in settings.items():
                    role_data = next((r for r in auto_roles if r["role_type"] == role_type), None)
                    if role_data:
                        role = inter.guild.get_role(int(role_data["role_id"]))
                        description += role.mention if role else "*Role deleted*"
                    else:
                        description += "*Not set*"
                    
                    embed.add_field(name=role_type.title() + " Role", value=description, inline=False)

                await button_inter.response.send_message(embed=embed, ephemeral=True)

        view = AutoRoleTypeView()
        await inter.response.send_message(embed=embed, view=view, ephemeral=True)

    @commands.slash_command(
        description="View current role permissions and auto-role settings (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def view_role_settings(self, inter: disnake.ApplicationCommandInteraction):
        """View all role settings"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can view role settings.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            permissions = await conn.fetch(
                "SELECT role_id, permission_type FROM role_permissions WHERE guild_id = $1 ORDER BY role_id",
                str(inter.guild.id)
            )
            auto_roles = await conn.fetch(
                "SELECT role_type, role_id, product_name FROM auto_roles WHERE guild_id = $1",
                str(inter.guild.id)
            )

        embed = disnake.Embed(
            title="🛡️ Role Settings Overview",
            color=disnake.Color.blue()
        )

        # Role permissions
        if permissions:
            role_perms = {}
            for perm in permissions:
                role_id = perm["role_id"]
                if role_id not in role_perms:
                    role_perms[role_id] = []
                role_perms[role_id].append(perm["permission_type"])

            perm_text = []
            for role_id, perms in role_perms.items():
                role = inter.guild.get_role(int(role_id))
                if role:
                    perm_list = ", ".join([PERMISSION_NAMES.get(p, p) for p in perms])
                    perm_text.append(f"**{role.name}:** {perm_list}")

            embed.add_field(
                name="🎭 Role Permissions",
                value="\n".join(perm_text) if perm_text else "None set",
                inline=False
            )

        # Auto-roles
        auto_role_text = []
        for auto_role in auto_roles:
            role = inter.guild.get_role(int(auto_role["role_id"]))
            if role:
                role_type = auto_role["role_type"]
                if auto_role["product_name"]:
                    auto_role_text.append(f"**{role_type.title()} ({auto_role['product_name']}):** {role.mention}")
                else:
                    auto_role_text.append(f"**{role_type.title()}:** {role.mention}")

        embed.add_field(
            name="⚙️ Auto-Roles",
            value="\n".join(auto_role_text) if auto_role_text else "None set",
            inline=False
        )

        embed.set_footer(text="Server Owner has all permissions by default")
        await inter.response.send_message(embed=embed, ephemeral=True)


# Permission types
PERMISSIONS = {
    "manage_products": "Product Management",
    "manage_tickets": "Ticket Management", 
    "handle_tickets": "Handle Support Tickets",
    "manage_stock": "Stock Management",
    "manage_categories": "Ticket Categories",
    "manage_messages": "Custom Messages",
    "view_admin": "View Admin Commands",
    "manage_verification": "Verification System",
    "manage_auto_roles": "Auto-Role Management",
    "manage_bot_settings": "Bot Settings",
    "request_reviews": "Request Reviews"
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

    @disnake.ui.button(label="⚙️ Auto-Role Management", style=disnake.ButtonStyle.secondary, row=2)
    async def manage_auto_roles(self, button, inter):
        await self.toggle_permission(inter, "manage_auto_roles")

    @disnake.ui.button(label="🤖 Bot Settings", style=disnake.ButtonStyle.secondary, row=2)
    async def manage_bot_settings(self, button, inter):
        await self.toggle_permission(inter, "manage_bot_settings")

    @disnake.ui.button(label="⭐ Request Reviews", style=disnake.ButtonStyle.secondary, row=3)
    async def request_reviews(self, button, inter):
        await self.toggle_permission(inter, "request_reviews")

    @disnake.ui.button(label="✅ Save & Exit", style=disnake.ButtonStyle.green, row=4)
    async def save_exit(self, button, inter):
        await inter.response.send_message(
            f"✅ Permissions saved for **{self.role_name}**!",
            ephemeral=True
        )
        self.stop()

    async def toggle_permission(self, inter, permission_type):
        async with (await get_database_pool()).acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT 1 FROM role_permissions WHERE guild_id = $1 AND role_id = $2 AND permission_type = $3",
                str(inter.guild.id), self.role_id, permission_type
            )

            if existing:
                await conn.execute(
                    "DELETE FROM role_permissions WHERE guild_id = $1 AND role_id = $2 AND permission_type = $3",
                    str(inter.guild.id), self.role_id, permission_type
                )
                status = "❌ Removed"
            else:
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
    if user.id == guild.owner_id:
        return True

    async with (await get_database_pool()).acquire() as conn:
        user_role_ids = [str(role.id) for role in user.roles]
        if not user_role_ids:
            return False

        result = await conn.fetchrow(
            "SELECT 1 FROM role_permissions WHERE guild_id = $1 AND role_id = ANY($2) AND permission_type = $3",
            str(guild.id), user_role_ids, permission_type
        )
        return result is not None

def setup(bot):
    bot.add_cog(EnhancedRoleManagement(bot))
