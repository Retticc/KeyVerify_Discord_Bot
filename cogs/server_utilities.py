# Create cogs/server_utilities.py

import disnake
from disnake.ext import commands
from utils.database import get_database_pool
from utils.permissions import owner_or_permission, has_permission, get_user_permissions, PermissionView
import config
import logging

logger = logging.getLogger(__name__)

class ServerUtilities(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        description="Check permissions for a specific user (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @owner_or_permission("view_admin")
    async def check_permissions(
        self, 
        inter: disnake.ApplicationCommandInteraction,
        user: disnake.Member
    ):
        """Check what permissions a user has"""
        permissions = await get_user_permissions(user, inter.guild)
        
        embed = disnake.Embed(
            title=f"🛡️ Permissions for {user.display_name}",
            color=disnake.Color.blue()
        )
        
        if user.id == inter.guild.owner_id:
            embed.description = "👑 **Server Owner** - Has all permissions"
        elif permissions:
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
                "manage_bot_settings": "🤖 Bot Settings"
            }
            
            perm_list = [permission_names.get(perm, perm) for perm in permissions]
            embed.description = "\n".join(perm_list)
        else:
            embed.description = "No special permissions assigned"
        
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text="Use /set_role_permissions to modify permissions")
        
        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.slash_command(
        description="Enable or disable welcome messages (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @owner_or_permission("manage_bot_settings")
    async def toggle_welcome_messages(
        self,
        inter: disnake.ApplicationCommandInteraction,
        enabled: bool
    ):
        """Toggle welcome messages on member join"""
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute(
                """
                INSERT INTO bot_settings (guild_id, setting_name, setting_value)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id, setting_name)
                DO UPDATE SET setting_value = $3
                """,
                str(inter.guild.id), "welcome_message", "enabled" if enabled else "disabled"
            )

        status = "enabled" if enabled else "disabled"
        await inter.response.send_message(
            f"✅ Welcome messages have been **{status}**.",
            ephemeral=True,
            delete_after=config.message_timeout
        )

    @commands.slash_command(
        description="Get server statistics and bot usage info (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @owner_or_permission("view_admin")
    async def server_stats(self, inter: disnake.ApplicationCommandInteraction):
        """Display comprehensive server statistics"""
        guild = inter.guild
        
        # Get database stats
        async with (await get_database_pool()).acquire() as conn:
            # Products
            products = await conn.fetch("SELECT product_name, stock FROM products WHERE guild_id = $1", str(guild.id))
            
            # Active tickets
            active_tickets = await conn.fetchval("SELECT COUNT(*) FROM active_tickets WHERE guild_id = $1", str(guild.id))
            
            # Verified licenses
            verified_licenses = await conn.fetchval("SELECT COUNT(*) FROM verified_licenses WHERE guild_id = $1", str(guild.id))
            
            # Auto-roles
            auto_roles = await conn.fetch("SELECT role_type, product_name FROM auto_roles WHERE guild_id = $1", str(guild.id))
            
            # Custom messages
            custom_messages = await conn.fetchval("SELECT COUNT(*) FROM custom_messages WHERE guild_id = $1", str(guild.id))

        # Create comprehensive stats embed
        embed = disnake.Embed(
            title=f"📊 Server Statistics - {guild.name}",
            color=disnake.Color.green()
        )

        # Basic server info
        embed.add_field(
            name="🏠 Server Info",
            value=(
                f"**Members:** {guild.member_count:,}\n"
                f"**Channels:** {len(guild.channels)}\n"
                f"**Roles:** {len(guild.roles)}\n"
                f"**Created:** <t:{int(guild.created_at.timestamp())}:R>"
            ),
            inline=True
        )

        # Product stats
        if products:
            total_stock = sum(p["stock"] for p in products if p["stock"] != -1)
            unlimited_products = sum(1 for p in products if p["stock"] == -1)
            sold_out = sum(1 for p in products if p["stock"] == 0)
            
            product_info = (
                f"**Products:** {len(products)}\n"
                f"**Total Stock:** {total_stock}\n"
                f"**Unlimited:** {unlimited_products}\n"
                f"**Sold Out:** {sold_out}"
            )
        else:
            product_info = "**Products:** 0\n*No products configured*"

        embed.add_field(
            name="🎁 Products",
            value=product_info,
            inline=True
        )

        # Bot usage stats
        embed.add_field(
            name="🤖 Bot Usage",
            value=(
                f"**Active Tickets:** {active_tickets}\n"
                f"**Verified Licenses:** {verified_licenses}\n"
                f"**Custom Messages:** {custom_messages}\n"
                f"**Auto-Roles:** {len(auto_roles)}"
            ),
            inline=True
        )

        # Auto-role breakdown
        if auto_roles:
            join_roles = len([r for r in auto_roles if r["role_type"] == "join"])
            verified_roles = len([r for r in auto_roles if r["role_type"] == "verified"])
            product_specific = len([r for r in auto_roles if r["product_name"]])
            
            embed.add_field(
                name="⚙️ Auto-Role Details",
                value=(
                    f"**Join Roles:** {join_roles}\n"
                    f"**Verified Roles:** {verified_roles}\n"
                    f"**Product-Specific:** {product_specific}"
                ),
                inline=True
            )

        # Bot permissions check
        bot_member = guild.me
        important_perms = [
            ("Manage Roles", bot_member.guild_permissions.manage_roles),
            ("Manage Channels", bot_member.guild_permissions.manage_channels),
            ("Send Messages", bot_member.guild_permissions.send_messages),
            ("Embed Links", bot_member.guild_permissions.embed_links),
        ]
        
        perm_status = []
        for perm_name, has_perm in important_perms:
            emoji = "✅" if has_perm else "❌"
            perm_status.append(f"{emoji} {perm_name}")
        
        embed.add_field(
            name="🔐 Bot Permissions",
            value="\n".join(perm_status),
            inline=True
        )

        # Recent activity summary (if we have timestamps)
        embed.add_field(
            name="📈 Quick Actions",
            value=(
                "`/view_role_settings` - Role overview\n"
                "`/list_tickets` - Active support\n"
                "`/view_stock` - Inventory status\n"
                "`/help` - Full command list"
            ),
            inline=True
        )

        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.set_footer(text=f"Requested by {inter.author.display_name}")
        embed.timestamp = inter.created_at

        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.slash_command(
        description="Cleanup and optimize bot data for this server (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @owner_or_permission("manage_bot_settings")
    async def cleanup_data(self, inter: disnake.ApplicationCommandInteraction):
        """Clean up stale data and optimize database"""
        await inter.response.defer(ephemeral=True)
        
        cleanup_results = []
        
        async with (await get_database_pool()).acquire() as conn:
            # Clean up stale ticket records
            stale_tickets = await conn.fetch(
                "SELECT channel_id FROM active_tickets WHERE guild_id = $1",
                str(inter.guild.id)
            )
            
            removed_tickets = 0
            for ticket in stale_tickets:
                channel = inter.guild.get_channel(int(ticket["channel_id"]))
                if not channel:
                    await conn.execute(
                        "DELETE FROM active_tickets WHERE guild_id = $1 AND channel_id = $2",
                        str(inter.guild.id), ticket["channel_id"]
                    )
                    removed_tickets += 1
            
            if removed_tickets > 0:
                cleanup_results.append(f"🧹 Removed {removed_tickets} stale ticket records")

            # Clean up verification messages for deleted channels
            verification_messages = await conn.fetch(
                "SELECT message_id, channel_id FROM verification_message WHERE guild_id = $1",
                str(inter.guild.id)
            )
            
            removed_verifications = 0
            for vm in verification_messages:
                channel = inter.guild.get_channel(int(vm["channel_id"]))
                if not channel:
                    await conn.execute(
                        "DELETE FROM verification_message WHERE guild_id = $1",
                        str(inter.guild.id)
                    )
                    removed_verifications += 1
            
            if removed_verifications > 0:
                cleanup_results.append(f"📝 Cleaned up {removed_verifications} verification message records")

            # Clean up auto-roles for deleted roles
            auto_roles = await conn.fetch(
                "SELECT role_id, role_type, product_name FROM auto_roles WHERE guild_id = $1",
                str(inter.guild.id)
            )
            
            removed_auto_roles = 0
            for ar in auto_roles:
                role = inter.guild.get_role(int(ar["role_id"]))
                if not role:
                    await conn.execute(
                        "DELETE FROM auto_roles WHERE guild_id = $1 AND role_id = $2",
                        str(inter.guild.id), ar["role_id"]
                    )
                    removed_auto_roles += 1
            
            if removed_auto_roles > 0:
                cleanup_results.append(f"🎭 Removed {removed_auto_roles} auto-roles for deleted roles")

            # Clean up stock channels for deleted channels
            stock_channels = await conn.fetch(
                "SELECT channel_id, product_name FROM stock_channels WHERE guild_id = $1",
                str(inter.guild.id)
            )
            
            removed_stock_channels = 0
            for sc in stock_channels:
                channel = inter.guild.get_channel(int(sc["channel_id"]))
                if not channel:
                    await conn.execute(
                        "DELETE FROM stock_channels WHERE guild_id = $1 AND channel_id = $2",
                        str(inter.guild.id), sc["channel_id"]
                    )
                    removed_stock_channels += 1
            
            if removed_stock_channels > 0:
                cleanup_results.append(f"📦 Removed {removed_stock_channels} stock channel records")

        if cleanup_results:
            embed = disnake.Embed(
                title="🧹 Data Cleanup Complete",
                description="\n".join(cleanup_results),
                color=disnake.Color.green()
            )
        else:
            embed = disnake.Embed(
                title="✅ No Cleanup Needed",
                description="All bot data is up to date and properly configured!",
                color=disnake.Color.blue()
            )

        embed.set_footer(text="Regular cleanup helps maintain optimal bot performance")
        await inter.followup.send(embed=embed, ephemeral=True)

    @commands.slash_command(
        description="Export server configuration as a backup (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @owner_or_permission("view_admin")
    async def export_config(self, inter: disnake.ApplicationCommandInteraction):
        """Export server configuration for backup purposes"""
        await inter.response.defer(ephemeral=True)
        
        config_data = {}
        
        async with (await get_database_pool()).acquire() as conn:
            # Export products (without secrets for security)
            products = await conn.fetch(
                "SELECT product_name, role_id, stock FROM products WHERE guild_id = $1",
                str(inter.guild.id)
            )
            config_data["products"] = [
                {
                    "name": p["product_name"],
                    "role_id": p["role_id"],
                    "stock": p["stock"]
                } for p in products
            ]
            
            # Export auto-roles
            auto_roles = await conn.fetch(
                "SELECT role_type, role_id, product_name FROM auto_roles WHERE guild_id = $1",
                str(inter.guild.id)
            )
            config_data["auto_roles"] = [
                {
                    "type": ar["role_type"],
                    "role_id": ar["role_id"],
                    "product": ar["product_name"]
                } for ar in auto_roles
            ]
            
            # Export role permissions
            role_perms = await conn.fetch(
                "SELECT role_id, permission_type FROM role_permissions WHERE guild_id = $1",
                str(inter.guild.id)
            )
            config_data["role_permissions"] = [
                {
                    "role_id": rp["role_id"],
                    "permission": rp["permission_type"]
                } for rp in role_perms
            ]
            
            # Export bot settings
            bot_settings = await conn.fetch(
                "SELECT setting_name, setting_value FROM bot_settings WHERE guild_id = $1",
                str(inter.guild.id)
            )
            config_data["bot_settings"] = {
                bs["setting_name"]: bs["setting_value"] for bs in bot_settings
            }

        # Create summary embed
        embed = disnake.Embed(
            title="📄 Configuration Export",
            description=(
                f"**Products:** {len(config_data['products'])}\n"
                f"**Auto-Roles:** {len(config_data['auto_roles'])}\n"
                f"**Role Permissions:** {len(config_data['role_permissions'])}\n"
                f"**Bot Settings:** {len(config_data['bot_settings'])}"
            ),
            color=disnake.Color.blue()
        )
        
        embed.add_field(
            name="⚠️ Security Notice",
            value="This export does NOT include sensitive data like product secrets or license keys for security reasons.",
            inline=False
        )
        
        embed.add_field(
            name="💡 Usage",
            value="This configuration can be used as a reference for server setup or migration planning.",
            inline=False
        )

        embed.set_footer(text=f"Export generated for {inter.guild.name}")
        embed.timestamp = inter.created_at

        await inter.followup.send(embed=embed, ephemeral=True)

def setup(bot):
    bot.add_cog(ServerUtilities(bot))
