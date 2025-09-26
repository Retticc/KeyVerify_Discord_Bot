# Complete updated handlers/verify_license_modal.py with Roblox support

import disnake
import requests
from utils.database import get_database_pool
from utils.validation import validate_license_key
import config
from utils.database import save_verified_license
import json
import logging

logger = logging.getLogger(__name__)

class VerifyLicenseModal(disnake.ui.Modal):
    def __init__(self, product_name, product_secret_key, product_type="payhip", gamepass_id=None):
        self.product_name = product_name
        self.product_secret_key = product_secret_key
        self.product_type = product_type
        self.gamepass_id = gamepass_id
        self.is_test_product = (product_name == "Test")
        
        if product_type == "roblox" and not self.is_test_product:
            components = [
                disnake.ui.TextInput(
                    label="Roblox Username",
                    custom_id="roblox_username",
                    placeholder="Enter your Roblox username",
                    style=disnake.TextInputStyle.short,
                    max_length=20,
                )
            ]
            modal_title = f"🎮 Verify {product_name}"
        else:
            components = [
                disnake.ui.TextInput(
                    label="License Key" if not self.is_test_product else "Test License Key",
                    custom_id="license_key",
                    placeholder="Enter your license key" if not self.is_test_product else "Enter TEST-TEST-TEST-TEST for testing",
                    style=disnake.TextInputStyle.short,
                    max_length=50,
                )
            ]
            modal_title = f"Verify {product_name}"
            
        super().__init__(title=modal_title, custom_id="verify_license_modal", components=components)
        
    async def callback(self, interaction: disnake.ModalInteraction):
        if self.product_type == "roblox" and not self.is_test_product:
            await self.handle_roblox_verification(interaction)
        else:
            await self.handle_payhip_verification(interaction)

    async def handle_roblox_verification(self, interaction: disnake.ModalInteraction):
        roblox_username = interaction.text_values["roblox_username"].strip()
        
        if not roblox_username:
            await interaction.response.send_message(
                "❌ Please provide a valid Roblox username.",
                ephemeral=True,
                delete_after=config.message_timeout
            )
            return

        await interaction.response.defer(ephemeral=True)
        
        # Check if this Discord user already verified this product
        async with (await get_database_pool()).acquire() as conn:
            existing_verification = await conn.fetchrow(
                "SELECT roblox_username FROM roblox_verified_users WHERE guild_id = $1 AND product_name = $2 AND discord_user_id = $3",
                str(interaction.guild.id), self.product_name, str(interaction.user.id)
            )
            
            if existing_verification:
                await interaction.followup.send(
                    f"❌ You have already verified this product with username **{existing_verification['roblox_username']}**. Each Discord user can only verify once per product.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return
        
        try:
            # Step 1: Get Roblox User ID from username
            user_id_response = requests.get(
                f"https://api.roblox.com/users/get-by-username?username={roblox_username}",
                timeout=10
            )
            
            if user_id_response.status_code != 200:
                await interaction.followup.send(
                    f"❌ Could not find Roblox user **{roblox_username}**. Please check the username and try again.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return
                
            user_data = user_id_response.json()
            roblox_user_id = user_data.get("Id")
            
            if not roblox_user_id:
                await interaction.followup.send(
                    f"❌ Could not find Roblox user **{roblox_username}**. Please check the username and try again.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

            # Step 2: Check if this Roblox user already used for verification in this server
            async with (await get_database_pool()).acquire() as conn:
                existing_roblox_user = await conn.fetchrow(
                    "SELECT discord_user_id FROM roblox_verified_users WHERE guild_id = $1 AND roblox_user_id = $2",
                    str(interaction.guild.id), str(roblox_user_id)
                )
                
                if existing_roblox_user:
                    discord_user = interaction.guild.get_member(int(existing_roblox_user['discord_user_id']))
                    discord_mention = discord_user.mention if discord_user else f"<@{existing_roblox_user['discord_user_id']}>"
                    
                    await interaction.followup.send(
                        f"❌ The Roblox user **{roblox_username}** has already been used for verification by {discord_mention}. Each Roblox account can only be used once per server.",
                        ephemeral=True,
                        delete_after=config.message_timeout
                    )
                    return

            # Step 3: Check gamepass purchase using stored Roblox cookie
            roblox_cookie = self.product_secret_key  # Cookie is stored as "secret"
            
            headers = {
                'Cookie': f'.ROBLOSECURITY={roblox_cookie}',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }
            
            # Use Roblox API to check if user owns the gamepass
            ownership_response = requests.get(
                f"https://inventory.roblox.com/v1/users/{roblox_user_id}/items/GamePass/{self.gamepass_id}/is-owned",
                headers=headers,
                timeout=10
            )
            
            if ownership_response.status_code != 200:
                await interaction.followup.send(
                    "❌ Failed to verify gamepass ownership. Please try again later or contact an administrator.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                logger.error(f"[Roblox API Error] Status {ownership_response.status_code}: {ownership_response.text}")
                return
            
            ownership_data = ownership_response.json()
            owns_gamepass = ownership_data.get("isOwned", False)
            
            if not owns_gamepass:
                await interaction.followup.send(
                    f"❌ **{roblox_username}** does not own the required gamepass for **{self.product_name}**.\n\n"
                    f"🎮 **Gamepass ID:** {self.gamepass_id}\n"
                    f"Please purchase the gamepass first, then try verification again.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

            # Step 4: Successful verification - assign role and save data
            await self.handle_successful_roblox_verification(interaction, roblox_username, roblox_user_id)

        except requests.exceptions.RequestException as e:
            logger.error(f"[Roblox Verification Error] {e}")
            await interaction.followup.send(
                "❌ Unable to contact Roblox servers. Please try again later.",
                ephemeral=True,
                delete_after=config.message_timeout
            )

    async def handle_successful_roblox_verification(self, interaction, roblox_username, roblox_user_id):
        """Handle successful Roblox gamepass verification"""
        user = interaction.author
        guild = interaction.guild

        async with (await get_database_pool()).acquire() as conn:
            row = await conn.fetchrow(
                "SELECT role_id, price FROM products WHERE guild_id = $1 AND product_name = $2",
                str(guild.id), self.product_name
            )
            if not row:
                await interaction.followup.send(
                    f"❌ Role information for '{self.product_name}' is missing.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

            role_id = row["role_id"]
            product_price = row["price"]
            role = disnake.utils.get(guild.roles, id=int(role_id))

            if not role:
                await interaction.followup.send(
                    "❌ The role associated with this product is missing or deleted.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

        await user.add_roles(role)
        logger.info(f"[Roblox Role Assigned] Gave role '{role.name}' to {user} in '{guild.name}' for Roblox product '{self.product_name}'.")

        # Assign verified auto-roles
        from cogs.member_events import assign_verified_auto_roles
        auto_roles = await assign_verified_auto_roles(user, self.product_name)
        
        # Save verification data
        async with (await get_database_pool()).acquire() as conn:
            await conn.execute(
                """INSERT INTO roblox_verified_users (guild_id, product_name, discord_user_id, roblox_username, roblox_user_id)
                   VALUES ($1, $2, $3, $4, $5)""",
                str(guild.id), self.product_name, str(user.id), roblox_username, str(roblox_user_id)
            )
            
            # Also save in verified_licenses for compatibility
            await conn.execute(
                """INSERT INTO verified_licenses (user_id, guild_id, product_name, license_key)
                   VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING""",
                str(user.id), str(guild.id), self.product_name, f"ROBLOX_{roblox_username}"
            )
        
        # Create success embed that matches your image style
        embed = disnake.Embed(
            title="🎮 Roblox Verification Successful!",
            description=f"✅ **{user.mention}**, your Roblox gamepass has been verified!",
            color=disnake.Color.green()
        )
        
        embed.add_field(
            name="🎁 Product",
            value=f"**{self.product_name}**",
            inline=True
        )
        
        embed.add_field(
            name="🎮 Roblox User",
            value=f"**{roblox_username}**",
            inline=True
        )
        
        embed.add_field(
            name="🏷️ Role Assigned",
            value=role.mention,
            inline=True
        )
        
        if product_price:
            embed.add_field(
                name="💰 Price",
                value=f"**{product_price}**",
                inline=True
            )
            
        embed.add_field(
            name="🎫 Gamepass ID",
            value=f"**{self.gamepass_id}**",
            inline=True
        )
        
        if auto_roles:
            auto_role_names = [r.mention for r in auto_roles]
            embed.add_field(
                name="🎭 Additional Roles",
                value=" ".join(auto_role_names),
                inline=False
            )
        
        embed.set_thumbnail(url=f"https://www.roblox.com/headshot-thumbnail/image?userId={roblox_user_id}&width=420&height=420&format=png")
        embed.set_footer(text="Powered by KeyVerify • Roblox Integration")
        embed.timestamp = interaction.created_at
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Log the event in the server's log channel
        await self.log_roblox_verification(guild, user, role, auto_roles, roblox_username, embed)

    async def log_roblox_verification(self, guild, user, role, auto_roles, roblox_username, embed):
        """Log the Roblox verification in the server log channel"""
        try:
            async with (await get_database_pool()).acquire() as conn:
                log_row = await conn.fetchrow(
                    "SELECT channel_id FROM server_log_channels WHERE guild_id = $1",
                    str(guild.id)
                )

            if log_row:
                log_channel = guild.get_channel(int(log_row["channel_id"]))
                if log_channel:
                    log_embed = disnake.Embed(
                        title="🎮 Roblox Gamepass Verification",
                        description=f"{user.mention} has verified their Roblox gamepass for **{self.product_name}**",
                        color=disnake.Color.green()
                    )
                    
                    all_roles = [role] + auto_roles
                    role_mentions = [r.mention for r in all_roles]
                    log_embed.add_field(name="🏷️ Roles Assigned", value=" ".join(role_mentions), inline=False)
                    log_embed.add_field(name="🎮 Roblox User", value=f"**{roblox_username}**", inline=True)
                    log_embed.add_field(name="🎫 Gamepass ID", value=f"**{self.gamepass_id}**", inline=True)
                    
                    log_embed.set_footer(text="Powered by KeyVerify • Roblox Integration")
                    log_embed.timestamp = disnake.utils.utcnow()
                    await log_channel.send(embed=log_embed)
        except Exception as e:               
            logger.error(f"[Roblox Log Error] Failed to log verification for {user}: {e}")

    async def handle_payhip_verification(self, interaction):
        """Handle the original Payhip verification (keep existing logic)"""
        license_key = interaction.text_values["license_key"].strip()

        # Handle Test product specially
        if self.is_test_product:
            if license_key.upper() == "TEST-TEST-TEST-TEST":
                await self.handle_test_product_success(interaction, license_key)
                return
            else:
                await interaction.response.send_message(
                    "❌ For the Test product, please enter `TEST-TEST-TEST-TEST` to simulate a successful verification.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

        # Continue with existing Payhip verification logic...
        try:
            validate_license_key(license_key)
        except ValueError as e:
            logger.warning(f"[Validation Failed] {interaction.user} provided invalid key in '{interaction.guild.name}': {str(e)}")
            await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True,delete_after=config.message_timeout)
            return

        PAYHIP_VERIFY_URL = f"https://payhip.com/api/v2/license/verify?license_key={license_key}"
        PAYHIP_INCREMENT_USAGE_URL = "https://payhip.com/api/v2/license/usage"

        headers = {"product-secret-key": self.product_secret_key}

        try:
            await interaction.response.defer(ephemeral=True)
            
            response = requests.get(PAYHIP_VERIFY_URL, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json().get("data")

            if not data or not data.get("enabled"):
                logger.warning(f"[Invalid License] {interaction.user} tried to use a disabled or invalid license in '{interaction.guild.name}'.")
                await interaction.followup.send("❌ This license is not valid or has been disabled.", ephemeral=True,delete_after=config.message_timeout)
                return

            if data.get("uses", 0) > 0:
                logger.warning(f"[Already Used] {interaction.user} tried a used license ({data['uses']} uses) in '{interaction.guild.name}'.")
                await interaction.followup.send(
                    f"❌ This license has already been used {data['uses']} times.",
                    ephemeral=True,delete_after=config.message_timeout
                )
                return

            increment_response = requests.put(
                PAYHIP_INCREMENT_USAGE_URL,
                headers=headers,
                data={"license_key": license_key},
                timeout=10
            )

            if increment_response.status_code != 200:
                await interaction.followup.send("❌ Failed to mark the license as used.", ephemeral=True,delete_after=config.message_timeout)
                return

            await self.handle_successful_verification(interaction, license_key)

        except requests.exceptions.RequestException as e:
            await interaction.followup.send(
                "❌ Unable to contact the verification server. Please try again later.",
                ephemeral=True,delete_after=config.message_timeout
            )

    async def handle_test_product_success(self, interaction, license_key):
        """Keep existing test product logic"""
        user = interaction.author
        guild = interaction.guild

        from cogs.member_events import assign_verified_auto_roles
        auto_roles = await assign_verified_auto_roles(user, self.product_name)
        
        success_msg = f"✅🧪 {user.mention}, your **Test** product verification is complete! This was a simulation - no real role was assigned since 'Test' is not a real product."
        
        if auto_roles:
            auto_role_names = [r.name for r in auto_roles]
            success_msg += f"\n\n🎭 **Auto-roles assigned:** {', '.join(auto_role_names)}"
        
        success_msg += f"\n\n💡 **Note:** This Test product is perfect for:\n• Testing review requests\n• Testing ticket systems\n• Training staff on bot features"
        
        await interaction.response.send_message(
            success_msg,
            ephemeral=True,
            delete_after=config.message_timeout
        )
        
        await save_verified_license(interaction.author.id, interaction.guild.id, self.product_name, license_key)
        
        # Log test verification
        try:
            async with (await get_database_pool()).acquire() as conn:
                log_row = await conn.fetchrow(
                    "SELECT channel_id FROM server_log_channels WHERE guild_id = $1",
                    str(guild.id)
                )

            if log_row:
                log_channel = guild.get_channel(int(log_row["channel_id"]))
                if log_channel:
                    embed = disnake.Embed(
                        title="🧪 Test License Verification",
                        description=f"{user.mention} has successfully tested the **Test** product verification system!",
                        color=disnake.Color.orange()
                    )
                    
                    if auto_roles:
                        role_mentions = [r.mention for r in auto_roles]
                        embed.add_field(name="• Auto-Roles Assigned", value=" ".join(role_mentions), inline=False)
                    
                    embed.add_field(name="💡 Purpose", value="This was a test verification using the built-in Test product.", inline=False)
                    embed.set_footer(text="Powered by KeyVerify • Test Mode")
                    embed.timestamp = interaction.created_at
                    await log_channel.send(embed=embed)
        except Exception as e:               
            logger.error(f"[Test Log Error] Failed to log test verification for {user}: {e}")

        logger.info(f"[Test Verification] {user} successfully completed test verification in '{guild.name}'")

    async def handle_successful_verification(self, interaction, license_key):
        """Keep existing Payhip verification success logic"""
        user = interaction.author
        guild = interaction.guild

        async with (await get_database_pool()).acquire() as conn:
            row = await conn.fetchrow(
                "SELECT role_id FROM products WHERE guild_id = $1 AND product_name = $2",
                str(guild.id), self.product_name
            )
            if not row:
                await interaction.followup.send(
                    f"❌ Role information for '{self.product_name}' is missing.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

            role_id = row["role_id"]
            role = disnake.utils.get(guild.roles, id=int(role_id))

            if not role:
                await interaction.followup.send(
                    "❌ The role associated with this product is missing or deleted.",
                    ephemeral=True,
                    delete_after=config.message_timeout
                )
                return

        await user.add_roles(role)
        logger.info(f"[Role Assigned] Gave role '{role.name}' to {user} in '{guild.name}' for product '{self.product_name}'.")

        from cogs.member_events import assign_verified_auto_roles
        auto_roles = await assign_verified_auto_roles(user, self.product_name)
        
        success_msg = f"✅🎉 {user.mention}, your license for '{self.product_name}' is verified! Role '{role.name}' has been assigned."
        
        if auto_roles:
            auto_role_names = [r.name for r in auto_roles]
            success_msg += f"\n\n🎭 **Additional roles assigned:** {', '.join(auto_role_names)}"
        
        await interaction.followup.send(
            success_msg,
            ephemeral=True,
            delete_after=config.message_timeout
        )
        
        await save_verified_license(interaction.author.id, interaction.guild.id, self.product_name, license_key)
        
        # Log the event in the server's log channel
        try:
            async with (await get_database_pool()).acquire() as conn:
                log_row = await conn.fetchrow(
                    "SELECT channel_id FROM server_log_channels WHERE guild_id = $1",
                    str(guild.id)
                )

            if log_row:
                log_channel = guild.get_channel(int(log_row["channel_id"]))
                if log_channel:
                    embed = disnake.Embed(
                        title="License Activation",
                        description=f"{user.mention} has registered the **{self.product_name}** product and has been granted the following roles:",
                        color=disnake.Color.green()
                    )
                    
                    all_roles = [role] + auto_roles
                    role_mentions = [r.mention for r in all_roles]
                    embed.add_field(name="• Roles", value=" ".join(role_mentions), inline=False)
                    
                    embed.set_footer(text="Powered by KeyVerify")
                    embed.timestamp = interaction.created_at
                    await log_channel.send(embed=embed)
        except Exception as e:               
            logger.error(f"[Log Error] Failed to log license for {user}: {e}")
