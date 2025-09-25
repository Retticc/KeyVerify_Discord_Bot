# Updated utils/permissions.py

import functools
from utils.database import get_database_pool
import disnake
from disnake.ext import commands
import config

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

def requires_permission(permission_type):
    """Decorator to check permissions for slash commands"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, inter, *args, **kwargs):
            if not await has_permission(inter.author, inter.guild, permission_type):
                await inter.response.send_message(
                    f"❌ You don't have permission to use this command. Required permission: **{permission_type.replace('_', ' ').title()}**",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return
            return await func(self, inter, *args, **kwargs)
        return wrapper
    return decorator

def owner_or_permission(permission_type):
    """Decorator for commands that require either server owner OR specific permission"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, inter, *args, **kwargs):
            # Always allow server owner
            if inter.author.id == inter.guild.owner_id:
                return await func(self, inter, *args, **kwargs)
            
            # Check permission for non-owners
            if not await has_permission(inter.author, inter.guild, permission_type):
                await inter.response.send_message(
                    f"❌ You don't have permission to use this command. Required: **Server Owner** or **{permission_type.replace('_', ' ').title()}** permission.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return
            return await func(self, inter, *args, **kwargs)
        return wrapper
    return decorator

async def get_user_permissions(user, guild):
    """Get all permissions for a specific user"""
    permissions = set()
    
    # Server owner gets all permissions
    if user.id == guild.owner_id:
        return {
            "manage_products", "manage_tickets", "handle_tickets", 
            "manage_stock", "manage_categories", "manage_messages", 
            "view_admin", "manage_verification", "manage_auto_roles", 
            "manage_bot_settings", "request_reviews"
        }
    
    async with (await get_database_pool()).acquire() as conn:
        user_role_ids = [str(role.id) for role in user.roles]
        if user_role_ids:
            results = await conn.fetch(
                "SELECT permission_type FROM role_permissions WHERE guild_id = $1 AND role_id = ANY($2)",
                str(guild.id), user_role_ids
            )
            permissions = {row["permission_type"] for row in results}
    
    return permissions

class PermissionView(disnake.ui.View):
    """A view for displaying user permissions"""
    def __init__(self, user, permissions):
        super().__init__(timeout=180)
        self.user = user
        self.permissions = permissions
        
    @disnake.ui.button(label="📋 View Permissions", style=disnake.ButtonStyle.secondary)
    async def show_permissions(self, button, inter):
        permission_names = {
            "manage_products": "🎁 Product Management",
            "manage_tickets": "🎫 Ticket Management", 
            "handle_tickets": "🛠️ Handle Support Tickets",
            "manage_stock": "📦 Stock Management",
            "manage_categories": "📂 Ticket Categories",
            "manage_messages": "📝 Custom Messages",
            "view_admin": "👁️ View Admin Commands",
            "manage_verification": "🔑 Verification System",
            "manage_auto_roles": "⚙️ Auto-Role Management",
            "manage_bot_settings": "🤖 Bot Settings",
            "request_reviews": "⭐ Request Reviews"
        }
        
        embed = disnake.Embed(
            title=f"🛡️ Permissions for {self.user.display_name}",
            color=disnake.Color.blue()
        )
        
        if self.user.id == inter.guild.owner_id:
            embed.description = "👑 **Server Owner** - Has all permissions"
        elif self.permissions:
            perm_list = [permission_names.get(perm, perm) for perm in self.permissions]
            embed.description = "\n".join(perm_list)
        else:
            embed.description = "No special permissions assigned"
            
        embed.set_thumbnail(url=self.user.display_avatar.url)
        await inter.response.send_message(embed=embed, ephemeral=True)

async def check_ticket_access(user, guild):
    """Check if user can access/handle tickets"""
    return (
        user.id == guild.owner_id or
        await has_permission(user, guild, "handle_tickets") or
        await has_permission(user, guild, "manage_tickets") or
        any(role.permissions.manage_channels for role in user.roles)
    )
