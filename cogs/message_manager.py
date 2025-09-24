import disnake
from disnake.ext import commands
from utils.database import get_database_pool
import config
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class MessageManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.setup_table())
        
    async def setup_table(self):
        """Creates table for storing custom messages"""
        await self.bot.wait_until_ready()
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS custom_messages (
                    guild_id TEXT NOT NULL,
                    message_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    color INTEGER DEFAULT 5793266,
                    fields TEXT,
                    footer TEXT,
                    timestamp BOOLEAN DEFAULT FALSE,
                    channel_id TEXT,
                    message_id TEXT,
                    PRIMARY KEY (guild_id, message_name)
                );
            """)

    @commands.slash_command(
        description="Create a custom embed message (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def create_message(self, inter: disnake.ApplicationCommandInteraction):
        """Creates a custom embed message"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can create messages.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        await inter.response.send_modal(CreateMessageModal())

    @commands.slash_command(
        description="Edit an existing custom message (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def edit_message(self, inter: disnake.ApplicationCommandInteraction):
        """Edits an existing custom message"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can edit messages.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Get existing messages
        async with (await get_database_pool()).acquire() as conn:
            messages = await conn.fetch(
                "SELECT message_name FROM custom_messages WHERE guild_id = $1",
                str(inter.guild.id)
            )

        if not messages:
            await inter.response.send_message(
                "❌ No custom messages found. Use `/create_message` first.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Create dropdown for message selection
        options = [
            disnake.SelectOption(label=msg["message_name"], value=msg["message_name"])
            for msg in messages[:25]  # Discord limit
        ]

        dropdown = disnake.ui.StringSelect(
            placeholder="Select a message to edit...",
            options=options
        )
        
        async def edit_selected(select_inter):
            message_name = select_inter.data["values"][0]
            
            # Get message data
            async with (await get_database_pool()).acquire() as conn:
                msg_data = await conn.fetchrow(
                    "SELECT * FROM custom_messages WHERE guild_id = $1 AND message_name = $2",
                    str(inter.guild.id), message_name
                )
            
            if msg_data:
                await select_inter.response.send_modal(EditMessageModal(msg_data))
            else:
                await select_inter.response.send_message("❌ Message not found.", ephemeral=True)

        dropdown.callback = edit_selected
        view = disnake.ui.View()
        view.add_item(dropdown)

        await inter.response.send_message(
            "📝 Select a message to edit:",
            view=view,
            ephemeral=True,
            delete_after=config.message_timeout
        )

    @commands.slash_command(
        description="Delete a custom message (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def delete_message(self, inter: disnake.ApplicationCommandInteraction):
        """Deletes a custom message"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can delete messages.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        # Get existing messages
        async with (await get_database_pool()).acquire() as conn:
            messages = await conn.fetch(
                "SELECT message_name FROM custom_messages WHERE guild_id = $1",
                str(inter.guild.id)
            )

        if not messages:
            await inter.response.send_message(
                "❌ No custom messages found.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        options = [
            disnake.SelectOption(label=msg["message_name"], value=msg["message_name"])
            for msg in messages[:25]
        ]

        dropdown = disnake.ui.StringSelect(
            placeholder="Select a message to delete...",
            options=options
        )
        
        async def delete_selected(select_inter):
            message_name = select_inter.data["values"][0]
            
            class ConfirmDeleteView(disnake.ui.View):
                def __init__(self):
                    super().__init__(timeout=30)

                @disnake.ui.button(label="✅ Confirm Delete", style=disnake.ButtonStyle.danger)
                async def confirm(self, button, button_inter):
                    async with (await get_database_pool()).acquire() as conn:
                        # Get message info to delete from Discord
                        msg_data = await conn.fetchrow(
                            "SELECT channel_id, message_id FROM custom_messages WHERE guild_id = $1 AND message_name = $2",
                            str(inter.guild.id), message_name
                        )
                        
                        if msg_data and msg_data["channel_id"] and msg_data["message_id"]:
                            try:
                                channel = inter.guild.get_channel(int(msg_data["channel_id"]))
                                if channel:
                                    message = await channel.fetch_message(int(msg_data["message_id"]))
                                    await message.delete()
                            except:
                                pass  # Message might already be deleted
                        
                        # Remove from database
                        await conn.execute(
                            "DELETE FROM custom_messages WHERE guild_id = $1 AND message_name = $2",
                            str(inter.guild.id), message_name
                        )
                    
                    await button_inter.response.send_message(f"✅ Message '{message_name}' deleted.", ephemeral=True)
                    self.stop()

                @disnake.ui.button(label="❌ Cancel", style=disnake.ButtonStyle.secondary)
                async def cancel(self, button, button_inter):
                    await button_inter.response.send_message("Deletion cancelled.", ephemeral=True)
                    self.stop()
            
            view = ConfirmDeleteView()
            await select_inter.response.send_message(
                f"⚠️ Are you sure you want to delete **'{message_name}'**?",
                view=view,
                ephemeral=True
            )

        dropdown.callback = delete_selected
        view = disnake.ui.View()
        view.add_item(dropdown)

        await inter.response.send_message(
            "🗑️ Select a message to delete:",
            view=view,
            ephemeral=True,
            delete_after=config.message_timeout
        )

    @commands.slash_command(
        description="List all custom messages (server owner only).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    async def list_messages(self, inter: disnake.ApplicationCommandInteraction):
        """Lists all custom messages"""
        if inter.author.id != inter.guild.owner_id:
            await inter.response.send_message(
                "❌ Only the server owner can list messages.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        async with (await get_database_pool()).acquire() as conn:
            messages = await conn.fetch(
                "SELECT message_name, title, channel_id, message_id FROM custom_messages WHERE guild_id = $1",
                str(inter.guild.id)
            )

        if not messages:
            await inter.response.send_message(
                "📝 No custom messages found.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        embed = disnake.Embed(
            title="📝 Custom Messages",
            color=disnake.Color.blurple()
        )

        message_list = []
        for msg in messages:
            status = "📍 Posted" if msg["channel_id"] else "📄 Draft"
            channel_info = ""
            if msg["channel_id"]:
                channel = inter.guild.get_channel(int(msg["channel_id"]))
                channel_info = f" in {channel.mention}" if channel else " (channel deleted)"
            
            message_list.append(f"**{msg['message_name']}** - {status}{channel_info}")

        embed.description = "\n".join(message_list)
        await inter.response.send_message(embed=embed, ephemeral=True)

class CreateMessageModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Message Name",
                custom_id="message_name",
                placeholder="e.g., 'terms-of-service'",
                style=disnake.TextInputStyle.short,
                max_length=50,
            ),
            disnake.ui.TextInput(
                label="Title",
                custom_id="title",
                placeholder="e.g., 'Game Templates — Terms of Service'",
                style=disnake.TextInputStyle.short,
                max_length=256,
            ),
            disnake.ui.TextInput(
                label="Description (Optional)",
                custom_id="description",
                placeholder="Main description text",
                style=disnake.TextInputStyle.paragraph,
                max_length=2000,
                required=False
            ),
            disnake.ui.TextInput(
                label="Fields (JSON Format)",
                custom_id="fields",
                placeholder='[{"name": "🔒 Section", "value": "Content here", "inline": false}]',
                style=disnake.TextInputStyle.paragraph,
                max_length=3000,
                required=False
            ),
            disnake.ui.TextInput(
                label="Footer (Optional)",
                custom_id="footer",
                placeholder="Footer text",
                style=disnake.TextInputStyle.short,
                max_length=200,
                required=False
            )
        ]
        super().__init__(title="Create Custom Message", components=components)

    async def callback(self, interaction: disnake.ModalInteraction):
        message_name = interaction.text_values["message_name"].strip()
        title = interaction.text_values["title"].strip()
        description = interaction.text_values.get("description", "").strip()
        fields_json = interaction.text_values.get("fields", "").strip()
        footer = interaction.text_values.get("footer", "").strip()

        # Validate fields JSON
        fields = []
        if fields_json:
            try:
                fields = json.loads(fields_json)
                if not isinstance(fields, list):
                    raise ValueError("Fields must be a list")
            except Exception as e:
                await interaction.response.send_message(
                    f"❌ Invalid fields JSON: {str(e)}\n\n"
                    "Example: `[{\"name\": \"🔒 Section\", \"value\": \"Content\", \"inline\": false}]`",
                    ephemeral=True
                )
                return

        # Save to database
        async with (await get_database_pool()).acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO custom_messages (guild_id, message_name, title, description, fields, footer)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    str(interaction.guild.id), message_name, title,
                    description or None, json.dumps(fields) if fields else None, footer or None
                )
            except:
                await interaction.response.send_message(
                    f"❌ A message named '{message_name}' already exists.",
                    ephemeral=True
                )
                return

        # Create and send the embed
        embed = disnake.Embed(
            title=title,
            description=description or None,
            color=disnake.Color.blurple()
        )

        if fields:
            for field in fields:
                embed.add_field(
                    name=field.get("name", ""),
                    value=field.get("value", ""),
                    inline=field.get("inline", False)
                )

        if footer:
            embed.set_footer(text=footer)

        embed.timestamp = datetime.utcnow()

        try:
            sent_message = await interaction.channel.send(embed=embed)
            
            # Update database with message location
            async with (await get_database_pool()).acquire() as conn:
                await conn.execute(
                    "UPDATE custom_messages SET channel_id = $1, message_id = $2 WHERE guild_id = $3 AND message_name = $4",
                    str(interaction.channel.id), str(sent_message.id), str(interaction.guild.id), message_name
                )
            
            await interaction.response.send_message(f"✅ Message '{message_name}' created!", ephemeral=True)
        except disnake.Forbidden:
            await interaction.response.send_message(
                f"✅ Message '{message_name}' saved as draft. I don't have permission to post here.",
                ephemeral=True
            )

class EditMessageModal(disnake.ui.Modal):
    def __init__(self, msg_data):
        self.message_name = msg_data["message_name"]
        self.channel_id = msg_data["channel_id"]
        self.message_id = msg_data["message_id"]
        
        components = [
            disnake.ui.TextInput(
                label="Title",
                custom_id="title",
                value=msg_data["title"],
                style=disnake.TextInputStyle.short,
                max_length=256,
            ),
            disnake.ui.TextInput(
                label="Description (Optional)",
                custom_id="description",
                value=msg_data["description"] or "",
                style=disnake.TextInputStyle.paragraph,
                max_length=2000,
                required=False
            ),
            disnake.ui.TextInput(
                label="Fields (JSON Format)",
                custom_id="fields",
                value=msg_data["fields"] or "",
                style=disnake.TextInputStyle.paragraph,
                max_length=3000,
                required=False
            ),
            disnake.ui.TextInput(
                label="Footer (Optional)",
                custom_id="footer",
                value=msg_data["footer"] or "",
                style=disnake.TextInputStyle.short,
                max_length=200,
                required=False
            )
        ]
        super().__init__(title=f"Edit: {self.message_name}", components=components)

    async def callback(self, interaction: disnake.ModalInteraction):
        title = interaction.text_values["title"].strip()
        description = interaction.text_values.get("description", "").strip()
        fields_json = interaction.text_values.get("fields", "").strip()
        footer = interaction.text_values.get("footer", "").strip()

        # Validate fields JSON
        fields = []
        if fields_json:
            try:
                fields = json.loads(fields_json)
            except Exception as e:
                await interaction.response.send_message(f"❌ Invalid fields JSON: {str(e)}", ephemeral=True)
                return

        # Update database
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute(
                """
                UPDATE custom_messages 
                SET title = $1, description = $2, fields = $3, footer = $4
                WHERE guild_id = $5 AND message_name = $6
                """,
                title, description or None, json.dumps(fields) if fields else None,
                footer or None, str(interaction.guild.id), self.message_name
            )

        # Create updated embed
        embed = disnake.Embed(
            title=title,
            description=description or None,
            color=disnake.Color.blurple()
        )

        if fields:
            for field in fields:
                embed.add_field(
                    name=field.get("name", ""),
                    value=field.get("value", ""),
                    inline=field.get("inline", False)
                )

        if footer:
            embed.set_footer(text=footer)

        embed.timestamp = datetime.utcnow()

        # Try to update existing message
        if self.channel_id and self.message_id:
            try:
                channel = interaction.guild.get_channel(int(self.channel_id))
                if channel:
                    message = await channel.fetch_message(int(self.message_id))
                    await message.edit(embed=embed)
                    await interaction.response.send_message(f"✅ Message '{self.message_name}' updated!", ephemeral=True)
                    return
            except:
                pass

        # Post new message if updating failed
        try:
            sent_message = await interaction.channel.send(embed=embed)
            async with (await get_database_pool()).acquire() as conn:
                await conn.execute(
                    "UPDATE custom_messages SET channel_id = $1, message_id = $2 WHERE guild_id = $3 AND message_name = $4",
                    str(interaction.channel.id), str(sent_message.id), str(interaction.guild.id), self.message_name
                )
            await interaction.response.send_message(f"✅ Message '{self.message_name}' updated and reposted!", ephemeral=True)
        except:
            await interaction.response.send_message(f"✅ Message '{self.message_name}' updated in database!", ephemeral=True)

def setup(bot):
    bot.add_cog(MessageManager(bot))
