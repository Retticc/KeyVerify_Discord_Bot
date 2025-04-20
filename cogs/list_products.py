import disnake
from disnake.ext import commands
from utils.database import get_database_pool
import config

# This cog provides a slash command to list all products configured for the current Discord server
class ListProducts(commands.Cog):
    @commands.slash_command(
        description="List all products configured for this server (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True)
    ) # Slash command to display a list of all registered products and their assigned roles
    
    async def list_products(self, inter: disnake.ApplicationCommandInteraction):
        if inter.author.id != inter.guild.owner_id:         # Only the server owner is allowed to view the product list
            await inter.response.send_message(
                "❌ Only the server owner can use this command.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return
        
        # Query the database for all products registered in this server
        async with (await get_database_pool()).acquire() as conn:
            rows = await conn.fetch(
                "SELECT product_name, role_id FROM products WHERE guild_id = $1",
                str(inter.guild.id)
            )

        # If there are no products, notify the user
        if not rows:
            await inter.response.send_message(
                "📦 No products have been added to this server yet.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Format the list with role mentions
        lines = []
        for row in rows:
            role = inter.guild.get_role(int(row["role_id"]))
            role_display = role.mention if role else "*⚠️ Missing Role*"
            lines.append(f"• **{row['product_name']}** → {role_display}")
            
        # Create and send an embed containing the formatted product list
        embed = disnake.Embed(
            title="🧾 Products in This Server",
            description="\n".join(lines),
            color=disnake.Color.blurple()
        )
        embed.set_footer(text="Only visible to the server owner.")

        await inter.response.send_message(embed=embed, ephemeral=True,delete_after=config.message_timeout)
        
# Registers the cog with the bot
def setup(bot):
    bot.add_cog(ListProducts(bot))
