# Fixed cogs/member_events.py with circular import resolution

import disnake
from disnake.ext import commands
from utils.database import get_database_pool
import logging

logger = logging.getLogger(__name__)

class EnhancedMemberEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Handle member joining - assign auto-roles"""
        if member.bot:
            return  # Don't process bots

        try:
            # Get join auto-roles for this guild
            async with (await get_database_pool()).acquire() as conn:
                auto_roles = await conn.fetch(
                    "SELECT role_id FROM auto_roles WHERE guild_id = $1 AND role_type = $2 AND product_name IS NULL",
                    str(member.guild.id), "join"
                )

            if not auto_roles:
                return  # No auto-roles set

            roles_to_add = []
            failed_roles = []
            
            for auto_role in auto_roles:
                role = member.guild.get_role(int(auto_role["role_id"]))
                if role and role < member.guild.me.top_role:
                    roles_to_add.append(role)
                elif role:
                    failed_roles.append(role.name)
                    logger.warning(f"[Auto-Role Skipped] Can't assign '{role.name}' to {member} in '{member.guild.name}' (role too high)")

            if roles_to_add:
                await member.add_roles(*roles_to_add, reason="Auto-role on join")
                role_names = [role.name for role in roles_to_add]
                logger.info(f"[Auto-Role Join] Assigned {', '.join(role_names)} to {member} in '{member.guild.name}'")

                # Optional: Send welcome message with role info
                await self.send_welcome_message(member, roles_to_add, failed_roles)

        except Exception as e:
            logger.error(f"[Member Join Error] Failed to handle member join for {member}: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Handle member leaving - optional logging"""
        if member.bot:
            return

        try:
            # Check if logging is enabled
            async with (await get_database_pool()).acquire() as conn:
                log_channel = await conn.fetchrow(
                    "SELECT channel_id FROM server_log_channels WHERE guild_id = $1",
                    str(member.guild.id)
                )

            if log_channel:
                channel = member.guild.get_channel(int(log_channel["channel_id"]))
                if channel:
                    embed = disnake.Embed(
                        title="Member Left",
                        description=f"{member.mention} has left the server.",
                        color=disnake.Color.red()
                    )
                    embed.add_field(name="User", value=f"{member} (ID: {member.id})", inline=False)
                    embed.add_field(name="Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "Unknown", inline=True)
                    embed.add_field(name="Left", value=f"<t:{int(disnake.utils.utcnow().timestamp())}:R>", inline=True)
                    
                    # Show roles they had
                    roles = [role.mention for role in member.roles if role != member.guild.default_role]
                    if roles:
                        embed.add_field(name="Roles", value=" ".join(roles), inline=False)
                    
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.set_footer(text="Powered by KeyVerify")
                    
                    try:
                        await channel.send(embed=embed)
                    except disnake.Forbidden:
                        pass  # No permission to send

        except Exception as e:
            logger.error(f"[Member Leave Error] Failed to handle member leave for {member}: {e}")

    async def send_welcome_message(self, member, assigned_roles, failed_roles):
        """Send welcome message if enabled"""
        try:
            async with (await get_database_pool()).acquire() as conn:
                welcome_setting = await conn.fetchrow(
                    "SELECT setting_value FROM bot_settings WHERE guild_id = $1 AND setting_name = $2",
                    str(member.guild.id), "welcome_message"
                )

            if welcome_setting and welcome_setting["setting_value"] == "enabled":
                embed = disnake.Embed(
                    title=f"Welcome to {member.guild.name}!",
                    description=f"{member.mention}, welcome to our server!",
                    color=disnake.Color.green()
                )
                
                if assigned_roles:
                    embed.add_field(
                        name="🎭 Roles Assigned",
                        value=" ".join([role.mention for role in assigned_roles]),
                        inline=False
                    )
                
                if failed_roles:
                    embed.add_field(
                        name="⚠️ Role Assignment Issues",
                        value=f"Could not assign: {', '.join(failed_roles)}\n*Please contact an administrator.*",
                        inline=False
                    )
                
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text="Powered by KeyVerify")

                # Try to send to system channel or first available channel
                channel = member.guild.system_channel
                if not channel:
                    channel = next((c for c in member.guild.text_channels if c.permissions_for(member.guild.me).send_messages), None)
                
                if channel:
                    await channel.send(embed=embed)

        except Exception as e:
            logger.error(f"[Welcome Message Error] Failed to send welcome message: {e}")

# Utility function to assign verified auto-roles - FIXED to avoid circular imports
async def assign_verified_auto_roles(member, product_name=None):
    """Utility function to assign auto-roles when user verifies a product"""
    try:
        # Get both general and product-specific verified auto-roles
        async with (await get_database_pool()).acquire() as conn:
            # General verified auto-roles
            general_auto_roles = await conn.fetch(
                "SELECT role_id FROM auto_roles WHERE guild_id = $1 AND role_type = $2 AND product_name IS NULL",
                str(member.guild.id), "verified"
            )
            
            # Product-specific auto-roles
            product_auto_roles = []
            if product_name:
                product_auto_roles = await conn.fetch(
                    "SELECT role_id FROM auto_roles WHERE guild_id = $1 AND role_type = $2 AND product_name = $3",
                    str(member.guild.id), "verified", product_name
                )

        all_auto_roles = general_auto_roles + product_auto_roles

        if not all_auto_roles:
            return []  # No auto-roles set

        roles_to_add = []
        failed_roles = []
        
        for auto_role in all_auto_roles:
            role = member.guild.get_role(int(auto_role["role_id"]))
            if role and role not in member.roles and role < member.guild.me.top_role:
                roles_to_add.append(role)
            elif role and role >= member.guild.me.top_role:
                failed_roles.append(role.name)
                logger.warning(f"[Auto-Role Skipped] Can't assign '{role.name}' to {member} in '{member.guild.name}' (role too high)")

        if roles_to_add:
            await member.add_roles(*roles_to_add, reason=f"Auto-role on verification: {product_name or 'General'}")
            role_names = [role.name for role in roles_to_add]
            logger.info(f"[Auto-Role Verified] Assigned {', '.join(role_names)} to {member} in '{member.guild.name}' for {product_name or 'verification'}")

        if failed_roles:
            logger.warning(f"[Auto-Role Failed] Could not assign {', '.join(failed_roles)} to {member} in '{member.guild.name}' - roles too high")

        return roles_to_add

    except Exception as e:
        logger.error(f"[Auto-Role Error] Failed to assign verified auto-roles to {member}: {e}")
        return []

async def get_auto_role_summary(guild_id):
    """Get a summary of all auto-roles for a guild"""
    async with (await get_database_pool()).acquire() as conn:
        auto_roles = await conn.fetch(
            "SELECT role_type, role_id, product_name FROM auto_roles WHERE guild_id = $1",
            guild_id
        )
    
    summary = {
        "join": {"general": [], "product_specific": {}},
        "verified": {"general": [], "product_specific": {}}
    }
    
    for auto_role in auto_roles:
        role_type = auto_role["role_type"]
        product_name = auto_role["product_name"]
        role_id = auto_role["role_id"]
        
        if product_name:
            if product_name not in summary[role_type]["product_specific"]:
                summary[role_type]["product_specific"][product_name] = []
            summary[role_type]["product_specific"][product_name].append(role_id)
        else:
            summary[role_type]["general"].append(role_id)
    
    return summary

def setup(bot):
    bot.add_cog(EnhancedMemberEvents(bot))
