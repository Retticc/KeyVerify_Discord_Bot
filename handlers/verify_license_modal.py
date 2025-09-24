# Update handlers/verify_license_modal.py

import disnake
import requests
from utils.database import get_database_pool
from utils.validation import validate_license_key
import config
from utils.database import save_verified_license

import logging

logger = logging.getLogger(__name__)

# This modal is shown to users when they select a product to verify.
# It prompts them to enter a license key, validates it via Payhip, and assigns the appropriate role if valid.
class VerifyLicenseModal(disnake.ui.Modal):
    def __init__(self, product_name, product_secret_key):
        self.product_name = product_name
        self.product_secret_key = product_secret_key
        components = [
            disnake.ui.TextInput(
                label="License Key",
                custom_id="license_key",
                placeholder="Enter your license key",
                style=disnake.TextInputStyle.short,
                max_length=50,
            )
        ]
        super().__init__(title=f"Verify {product_name}", custom_id="verify_license_modal", components=components)
        
    # Handles what happens after the user submits the modal.
    # It checks the license with Payhip, assigns a role, and logs the action if everything is valid.
    async def callback(self, interaction: disnake.ModalInteraction):
        license_key = interaction.text_values["license_key"].strip()

        # Validate license key format
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
            # Verify license key with Payhip
            response = requests.get(PAYHIP_VERIFY_URL, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json().get("data")

            if not data or not data.get("enabled"):
                logger.warning(f"[Invalid License] {interaction.user} tried to use a disabled or invalid license in '{interaction.guild.name}'.")
                await interaction.response.send_message("❌ This license is not valid or has been disabled.", ephemeral=True,delete_after=config.message_timeout)
                return

            if data.get("uses", 0) > 0:
                logger.warning(f"[Already Used] {interaction.user} tried a used license ({data['uses']} uses) in '{interaction.guild.name}'.")
                await interaction.response.send_message(
                    f"❌ This license has already been used {data['uses']} times.",
                    ephemeral=True,delete_after=config.message_timeout
                )
                return

            # Mark the license as used in Payhip
            increment_response = requests.put(
                PAYHIP_INCREMENT_USAGE_URL,
                headers=headers,
                data={"license_key": license_key},
                timeout=10
            )

            if increment_response.status_code != 200:
                await interaction.response.send_message("❌ Failed to mark the license as used.", ephemeral=True,delete_after=config.message_timeout)
                return

            # Assign role to the user
            user = interaction.author
            guild = interaction.guild

            async with (await get_database_pool()).acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT role_id FROM products WHERE guild_id = $1 AND product_name = $2",
                    str(guild.id), self.product_name
                )
                if not row:
                    await interaction.response.send_message(
                        f"❌ Role information for '{self.product_name}' is missing.",
                        ephemeral=True,delete_after=config.message_timeout
                    )
                    return

                role_id = row["role_id"]
                role = disnake.utils.get(guild.roles, id=int(role_id))

                if not role:
                    await interaction.response.send_message(
                        "❌ The role associated with this product is missing or deleted.",
                        ephemeral=True,delete_after=config.message_timeout
                    )
                    return

            await user.add_roles(role)
            logger.info(f"[Role Assigned] Gave role '{role.name}' to {user} in '{guild.name}' for product '{self.product_name}'.")

            # Assign verified auto-roles
            from cogs.member_events import assign_verified_auto_roles
            auto_roles = await assign_verified_auto_roles(user, self.product_name)
            
            # Prepare success message
            success_msg = f"✅🎉 {user.mention}, your license for '{self.product_name}' is verified! Role '{role.name}' has been assigned."
            
            if auto_roles:
                auto_role_names = [r.name for r in auto_roles]
                success_msg += f"\n\n🎭 **Additional roles assigned:** {', '.join(auto_role_names)}"
            
            await interaction.response.send_message(
                success_msg,
                ephemeral=True,
                delete_after=config.message_timeout
            )
            
            await save_verified_license(interaction.author.id, interaction.guild.id, self.product_name, license_key) # Save the license in the local database
            
            # Optionally log the event in the server's log channel
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
                logger.error(f"[Log Error] Failed to log license for {user}: {e}") # Fails silently so user still gets a role even if logging fails

        except requests.exceptions.RequestException as e:
            await interaction.response.send_message(
                "❌ Unable to contact the verification server. Please try again later.",
                ephemeral=True,delete_after=config.message_timeout
            )
