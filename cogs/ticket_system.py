# Complete the set_ticket_discord_categories command

@commands.slash_command(
    description="Set Discord categories for ticket types (server owner only).",
    default_member_permissions=disnake.Permissions(manage_guild=True),
)
async def set_ticket_discord_categories(self, inter: disnake.ApplicationCommandInteraction):
    """Set which Discord category each ticket type goes into"""
    if inter.author.id != inter.guild.owner_id:
        await inter.response.send_message(
            "❌ Only the server owner can set ticket categories.",
            ephemeral=True,
            delete_after=config.message_timeout
        )
        return

    # Create table if it doesn't exist
    async with (await get_database_pool()).acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_category_channels (
                guild_id TEXT NOT NULL,
                category_name TEXT NOT NULL,
                discord_category_id TEXT NOT NULL,
                PRIMARY KEY (guild_id, category_name)
            );
        """)

    # Get custom ticket categories
    categories = await fetch_ticket_categories(str(inter.guild.id))
    
    if not categories:
        await inter.response.send_message(
            "❌ No custom ticket categories found. Use `/add_ticket_category` first.",
            ephemeral=True,
            delete_after=config.message_timeout
        )
        return

    # Create dropdown for ticket categories
    options = [
        disnake.SelectOption(
            label=cat["category_name"], 
            value=cat["category_name"],
            description=f"Set Discord category for {cat['category_name']}"
        )
        for cat in categories
    ]

    dropdown = disnake.ui.StringSelect(
        placeholder="Select ticket category to assign Discord category...",
        options=options
    )
    
    async def category_selected(select_inter):
        ticket_category = select_inter.data["values"][0]
        
        # Get Discord categories
        discord_categories = [
            disnake.SelectOption(
                label=f"📁 {category.name}", 
                value=str(category.id),
                description=f"{len(category.channels)} channels"
            )
            for category in inter.guild.categories
        ][:25]
        
        if not discord_categories:
            await select_inter.response.send_message(
                "❌ No Discord categories found. Create some categories first.",
                ephemeral=True
            )
            return
        
        discord_dropdown = disnake.ui.StringSelect(
            placeholder="Select Discord category...",
            options=discord_categories
        )
        
        async def discord_category_selected(dc_inter):
            discord_category_id = dc_inter.data["values"][0]
            discord_category = inter.guild.get_channel(int(discord_category_id))
            
            async with (await get_database_pool()).acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO ticket_category_channels (guild_id, category_name, discord_category_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id, category_name)
                    DO UPDATE SET discord_category_id = $3
                    """,
                    str(inter.guild.id), ticket_category, discord_category_id
                )
            
            await dc_inter.response.send_message(
                f"✅ **{ticket_category}** tickets will now be created in **📁 {discord_category.name}**",
                ephemeral=True
            )
        
        discord_dropdown.callback = discord_category_selected
        
        # Create view for Discord category selection
        discord_view = disnake.ui.View()
        discord_view.add_item(discord_dropdown)
        
        await select_inter.response.send_message(
            f"**Setting Discord category for:** {ticket_category}\n\nSelect which Discord category these tickets should be created in:",
            view=discord_view,
            ephemeral=True
        )
    
    dropdown.callback = category_selected
    
    # Create view for ticket category selection
    view = disnake.ui.View()
    view.add_item(dropdown)
    
    await inter.response.send_message(
        "**🔧 Set Discord Categories for Tickets**\n\nSelect which ticket category you want to assign a Discord category to:",
        view=view,
        ephemeral=True
    )

@commands.slash_command(
    description="View current ticket category assignments (server owner only).",
    default_member_permissions=disnake.Permissions(manage_guild=True),
)
async def view_ticket_categories(self, inter: disnake.ApplicationCommandInteraction):
    """View current ticket category to Discord category assignments"""
    if inter.author.id != inter.guild.owner_id:
        await inter.response.send_message(
            "❌ Only the server owner can view ticket category settings.",
            ephemeral=True,
            delete_after=config.message_timeout
        )
        return

    async with (await get_database_pool()).acquire() as conn:
        assignments = await conn.fetch(
            """
            SELECT category_name, discord_category_id 
            FROM ticket_category_channels 
            WHERE guild_id = $1
            ORDER BY category_name
            """,
            str(inter.guild.id)
        )

    if not assignments:
        await inter.response.send_message(
            "❌ No ticket category assignments found. Use `/set_ticket_discord_categories` to set them up.",
            ephemeral=True,
            delete_after=config.message_timeout
        )
        return

    embed = disnake.Embed(
        title="🎫 Ticket Category Assignments",
        description="Current Discord category assignments for ticket types:",
        color=disnake.Color.blue()
    )

    for assignment in assignments:
        category_name = assignment["category_name"]
        discord_category_id = assignment["discord_category_id"]
        discord_category = inter.guild.get_channel(int(discord_category_id))
        
        if discord_category:
            embed.add_field(
                name=f"🎫 {category_name}",
                value=f"📁 {discord_category.name}",
                inline=True
            )
        else:
            embed.add_field(
                name=f"🎫 {category_name}",
                value="❌ Category not found",
                inline=True
            )

    embed.set_footer(text="Use /set_ticket_discord_categories to modify assignments")
    
    await inter.response.send_message(embed=embed, ephemeral=True)

@commands.slash_command(
    description="Remove Discord category assignment for a ticket type (server owner only).",
    default_member_permissions=disnake.Permissions(manage_guild=True),
)
async def remove_ticket_category_assignment(self, inter: disnake.ApplicationCommandInteraction):
    """Remove Discord category assignment for a ticket type"""
    if inter.author.id != inter.guild.owner_id:
        await inter.response.send_message(
            "❌ Only the server owner can remove ticket category assignments.",
            ephemeral=True,
            delete_after=config.message_timeout
        )
        return

    async with (await get_database_pool()).acquire() as conn:
        assignments = await conn.fetch(
            """
            SELECT category_name, discord_category_id 
            FROM ticket_category_channels 
            WHERE guild_id = $1
            ORDER BY category_name
            """,
            str(inter.guild.id)
        )

    if not assignments:
        await inter.response.send_message(
            "❌ No ticket category assignments found.",
            ephemeral=True,
            delete_after=config.message_timeout
        )
        return

    # Create dropdown for assignments to remove
    options = []
    for assignment in assignments:
        category_name = assignment["category_name"]
        discord_category_id = assignment["discord_category_id"]
        discord_category = inter.guild.get_channel(int(discord_category_id))
        
        discord_name = discord_category.name if discord_category else "Category Not Found"
        
        options.append(disnake.SelectOption(
            label=category_name,
            value=category_name,
            description=f"Currently assigned to: {discord_name}"
        ))

    dropdown = disnake.ui.StringSelect(
        placeholder="Select ticket category to remove assignment...",
        options=options
    )
    
    async def assignment_selected(select_inter):
        category_name = select_inter.data["values"][0]
        
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute(
                "DELETE FROM ticket_category_channels WHERE guild_id = $1 AND category_name = $2",
                str(inter.guild.id), category_name
            )
        
        await select_inter.response.send_message(
            f"✅ Removed Discord category assignment for **{category_name}**.\n"
            "These tickets will now be created in the default location.",
            ephemeral=True
        )
    
    dropdown.callback = assignment_selected
    
    view = disnake.ui.View()
    view.add_item(dropdown)
    
    await inter.response.send_message(
        "**🗑️ Remove Category Assignment**\n\nSelect which ticket category assignment to remove:",
        view=view,
        ephemeral=True
    )
