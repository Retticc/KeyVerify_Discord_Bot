import disnake
from disnake.ext import commands
import requests
import sqlite3
from dotenv import load_dotenv
import os
from flask import Flask
import threading
from cryptography.fernet import Fernet
from datetime import datetime, timedelta
import logging

# Flask app for health check
app = Flask(__name__)

# Health check route
@app.route('/')
def health_check():
    return "OK", 200

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())

cipher_suite = Fernet(ENCRYPTION_KEY.encode())
rate_limits = {}

# Logging configuration
try:
    logging_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(level=logging_level, format="%(asctime)s - %(levelname)s - %(message)s")
except AttributeError:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Database setup
def get_database_connection(database_url):
    if database_url.startswith("sqlite"):
        db_file_path = database_url.split("sqlite:///")[1]
        if not os.path.exists(db_file_path):
            open(db_file_path, 'w').close()
            print(f"Database file created at: {db_file_path}")
        conn = sqlite3.connect(db_file_path)
        conn.row_factory = sqlite3.Row
    elif database_url.startswith("postgresql"):
        import psycopg2
        from psycopg2.extras import DictCursor
        conn = psycopg2.connect(database_url, cursor_factory=DictCursor)
    else:
        raise ValueError(f"Unsupported database type: {database_url}")
    return conn

try:
    conn = get_database_connection(DATABASE_URL)
    cursor = conn.cursor()

    # Create tables if they don't exist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        guild_id TEXT NOT NULL,
        product_name TEXT NOT NULL,
        product_secret TEXT NOT NULL,
        role_id TEXT,  -- New column to store the associated role ID
        PRIMARY KEY (guild_id, product_name)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS verification_message (
        guild_id TEXT NOT NULL PRIMARY KEY,
        message_id TEXT,
        channel_id TEXT
    )
    """)

    # Check if the 'role_id' column exists in the 'products' table
    cursor.execute("PRAGMA table_info(products)")
    products_columns = [col[1] for col in cursor.fetchall()]
    if "role_id" not in products_columns:
        cursor.execute("ALTER TABLE products ADD COLUMN role_id TEXT")

    # Check if the 'channel_id' column exists in the 'verification_message' table
    cursor.execute("PRAGMA table_info(verification_message)")
    verification_columns = [col[1] for col in cursor.fetchall()]
    if "channel_id" not in verification_columns:
        cursor.execute("ALTER TABLE verification_message ADD COLUMN channel_id TEXT")

    conn.commit()
    print("Database connected and ready.")
except Exception as e:
    print(f"Error initializing the database: {e}")
    exit(1)
    
intents = disnake.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.InteractionBot(
    intents=intents,
    sync_commands=True,
    sync_commands_debug=True
)


# Fetch products for a guild
def fetch_products(guild_id):
    cursor.execute("SELECT product_name, product_secret FROM products WHERE guild_id = ?", (guild_id,))
    return {row["product_name"]: cipher_suite.decrypt(row["product_secret"].encode()).decode() for row in cursor.fetchall()}

# Add a product
@bot.slash_command(
    guild_ids=[503325217133690895],
    description="Add a product to the server's list with an assigned role (server owner only).",
    default_member_permissions=disnake.Permissions(manage_guild=True),
)
async def add_product(
    inter: disnake.ApplicationCommandInteraction,
    product_secret: str,
    product_name: str,
    role: disnake.Role = None  # User selects a role from the dropdown
):
    if inter.author.id != inter.guild.owner_id:
        await inter.response.send_message("❌ Only the server owner can use this command.", ephemeral=True)
        return

    # Encrypt the product secret
    encrypted_secret = cipher_suite.encrypt(product_secret.encode()).decode()

    # Check if a role is provided
    if role:
        # If the role exists, use it directly
        role_name = role.name
    else:
        # Create a new role if none is provided
        role_name = f"Verified-{product_name}"
        role = await inter.guild.create_role(name=role_name)
        await inter.response.send_message(f"⚠️ Role '{role_name}' was created automatically.", ephemeral=True)

    try:
        # Insert the product into the database with the associated role ID
        cursor.execute(
            "INSERT INTO products (guild_id, product_name, product_secret, role_id) VALUES (?, ?, ?, ?)",
            (str(inter.guild.id), product_name, encrypted_secret, str(role.id))
        )
        conn.commit()

        await inter.response.send_message(
            f"✅ Product '{product_name}' added successfully with role '{role.name}'.",
            ephemeral=True
        )
    except sqlite3.IntegrityError:
        await inter.response.send_message(f"❌ Product '{product_name}' already exists.", ephemeral=True)
        
# Remove a product
@bot.slash_command(guild_ids=[503325217133690895],description="Remove a product from the server's list (server owner only).", default_member_permissions=disnake.Permissions(manage_guild=True))
async def remove_product(inter: disnake.ApplicationCommandInteraction, product_name: str):
    if inter.author.id != inter.guild.owner_id:
        await inter.response.send_message("❌ Only the server owner can use this command.", ephemeral=True)
        return

    cursor.execute("DELETE FROM products WHERE guild_id = ? AND product_name = ?", (str(inter.guild.id), product_name))
    conn.commit()
    await inter.response.send_message(f"✅ Product '{product_name}' removed successfully.", ephemeral=True)

# Reset a license key's usage count
@bot.slash_command(guild_ids=[503325217133690895],description="Reset a product license key's usage count (server owner only).", default_member_permissions=disnake.Permissions(manage_guild=True))
async def reset_key(inter: disnake.ApplicationCommandInteraction, product_name: str, license_key: str):
    if inter.author.id != inter.guild.owner_id:
        await inter.response.send_message("❌ Only the server owner can use this command.", ephemeral=True)
        return

    cursor.execute("SELECT product_secret FROM products WHERE guild_id = ? AND product_name = ?", (str(inter.guild.id), product_name))
    row = cursor.fetchone()

    if not row:
        await inter.response.send_message(f"❌ Product '{product_name}' not found.", ephemeral=True)
        return

    product_secret_key = cipher_suite.decrypt(row["product_secret"].encode()).decode()

    PAYHIP_RESET_USAGE_URL = "https://payhip.com/api/v2/license/decrease"
    headers = {"product-secret-key": product_secret_key}
    try:
        response = requests.put(PAYHIP_RESET_USAGE_URL, headers=headers, data={"license_key": license_key.strip()}, timeout=10)
        response.raise_for_status()

        if response.status_code == 200:
            await inter.response.send_message(f"✅ License key for '{product_name}' has been reset successfully.", ephemeral=True)
        else:
            await inter.response.send_message("❌ Failed to reset the license key.", ephemeral=True)
    except requests.exceptions.RequestException as e:
        logging.error(f"Error contacting Payhip API: {e}")
        await inter.response.send_message("❌ Unable to contact the reset server.", ephemeral=True)

class VerificationButton(disnake.ui.View):
    def __init__(self, products):
        super().__init__(timeout=None)  # Timeout disabled for persistent button
        self.products = products

        # Button with unique custom_id
        button = disnake.ui.Button(label="Verify", style=disnake.ButtonStyle.primary, custom_id="verify_button")
        button.callback = self.verify_callback
        self.add_item(button)

    async def verify_callback(self, interaction: disnake.MessageInteraction):
        options = [disnake.SelectOption(label=name, description=f"Verify {name}") for name in self.products.keys()]
        select = ProductDropdown(options, self.products)
        await interaction.response.send_message(
            "Select a product to verify:",
            view=select,
            ephemeral=True
        )
@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}!")

    # Fetch all verification messages from the database
    cursor.execute("SELECT guild_id, message_id, channel_id FROM verification_message")
    rows = cursor.fetchall()

    for row in rows:
        guild_id, message_id, channel_id = row["guild_id"], row["message_id"], row["channel_id"]
        try:
            guild = bot.get_guild(int(guild_id))
            if not guild:
                print(f"Guild {guild_id} not found. Skipping...")
                continue

            channel = guild.get_channel(int(channel_id))
            if not channel:
                print(f"Channel {channel_id} not found in guild {guild_id}. Removing entry from database...")
                # Remove entry if the channel is missing
                cursor.execute("DELETE FROM verification_message WHERE guild_id = ?", (guild_id,))
                conn.commit()
                continue

            # Fetch the products for this guild
            products = fetch_products(guild_id)
            if not products:
                print(f"No products found for guild {guild_id}. Skipping...")
                continue

            # Create the view and pre-register it
            view = VerificationButton(products)
            bot.add_view(view, message_id=int(message_id))

            try:
                # Fetch and update the existing message
                message = await channel.fetch_message(int(message_id))
                embed = disnake.Embed(
                    title="Verify your purchase",
                    description="Click the button below to begin verifying your purchase.",
                    color=disnake.Color.blurple()
                )
                embed.set_footer(text="Powered by GumCord")
                await message.edit(embed=embed, view=view)
                print(f"Verification message updated for guild {guild_id} in channel {channel.name}.")
            except disnake.NotFound:
                print(f"Message {message_id} not found in channel {channel_id}. Removing entry from database...")
                # Remove entry if the message is missing
                cursor.execute("DELETE FROM verification_message WHERE guild_id = ?", (guild_id,))
                conn.commit()

        except Exception as e:
            logging.error(f"Error processing verification message for guild {guild_id}: {e}")
            
@bot.slash_command(
    guild_ids=[503325217133690895],
    description="Start the product verification process (visible to all).",
    default_member_permissions=disnake.Permissions(manage_guild=True),
)
async def start_verification(inter: disnake.ApplicationCommandInteraction):
    if inter.author.id != inter.guild.owner_id:
        await inter.response.send_message("❌ Only the server owner can use this command.", ephemeral=True)
        return

    products = fetch_products(str(inter.guild.id))
    if not products:
        await inter.response.send_message("❌ No products are registered for this server.", ephemeral=True)
        return

    # Create the embed
    embed = disnake.Embed(
        title="Verify your purchase",
        description="Click the button below to begin verifying your purchase.",
        color=disnake.Color.blurple()
    )
    embed.set_footer(text="Powered by KeyVerify")

    # Create the persistent button view
    view = VerificationButton(products)

    # Send or update the verification message
    cursor.execute("SELECT message_id, channel_id FROM verification_message WHERE guild_id = ?", (str(inter.guild.id),))
    result = cursor.fetchone()

    if result:
        # Try to fetch and edit the existing message
        try:
            message_id = int(result["message_id"])
            channel_id = int(result["channel_id"])
            channel = inter.guild.get_channel(channel_id)
            if not channel:
                raise disnake.NotFound  # Channel no longer exists

            existing_message = await channel.fetch_message(message_id)
            await existing_message.edit(embed=embed, view=view)
            bot.add_view(view, message_id=existing_message.id)  # Re-register the view
            await inter.response.send_message("✅ Verification message updated successfully.", ephemeral=True)
        except (disnake.NotFound, AttributeError):
            # If message or channel is not found, create a new one
            print(f"Message or channel missing for guild {inter.guild.id}. Creating a new message...")
            new_message = await inter.channel.send(embed=embed, view=view)
            cursor.execute(
                "REPLACE INTO verification_message (guild_id, message_id, channel_id) VALUES (?, ?, ?)",
                (str(inter.guild.id), str(new_message.id), str(inter.channel.id))
            )
            conn.commit()
            bot.add_view(view, message_id=new_message.id)  # Register the view
            await inter.response.send_message("✅ New verification message created successfully.", ephemeral=True)
    else:
        # No existing message, send a new one
        new_message = await inter.channel.send(embed=embed, view=view)
        cursor.execute(
            "INSERT INTO verification_message (guild_id, message_id, channel_id) VALUES (?, ?, ?)",
            (str(inter.guild.id), str(new_message.id), str(inter.channel.id))
        )
        conn.commit()
        bot.add_view(view, message_id=new_message.id)  # Register the view
        await inter.response.send_message("✅ Verification message created successfully.", ephemeral=True)


class ProductDropdown(disnake.ui.View):
    def __init__(self, options, products):
        super().__init__()
        self.products = products
        dropdown = disnake.ui.StringSelect(placeholder="Choose a product", options=options)
        dropdown.callback = self.select_callback
        self.add_item(dropdown)

    async def select_callback(self, interaction: disnake.MessageInteraction):
        product_name = interaction.data["values"][0]
        product_secret_key = self.products[product_name]
        await interaction.response.send_modal(VerifyLicenseModal(product_name, product_secret_key))


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

    async def callback(self, interaction: disnake.ModalInteraction):
        license_key = interaction.text_values["license_key"].strip()
        PAYHIP_VERIFY_URL = f"https://payhip.com/api/v2/license/verify?license_key={license_key}"
        PAYHIP_INCREMENT_USAGE_URL = "https://payhip.com/api/v2/license/usage"

        headers = {"product-secret-key": self.product_secret_key}

        try:
            # Verify license key
            response = requests.get(PAYHIP_VERIFY_URL, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json().get("data")

            if not data or not data.get("enabled"):
                await interaction.response.send_message(
                    "❌ This license is not valid or has been disabled.",
                    ephemeral=True
                )
                return

            # Check if the license key is already used
            if data.get("uses", 0) > 0:
                await interaction.response.send_message(
                    f"❌ This license has already been used {data['uses']} times.",
                    ephemeral=True
                )
                return

            # Increment usage count to mark key as used
            increment_response = requests.put(
                PAYHIP_INCREMENT_USAGE_URL,
                headers=headers,
                data={"license_key": license_key},
                timeout=10
            )

            if increment_response.status_code != 200:
                await interaction.response.send_message(
                    "❌ Failed to mark the license as used. Please contact support.",
                    ephemeral=True
                )
                return

            # Assign the role to the user based on database data
            user = interaction.author
            guild = interaction.guild

            # Retrieve role_id for the product from the database
            cursor.execute(
                "SELECT role_id FROM products WHERE guild_id = ? AND product_name = ?",
                (str(guild.id), self.product_name)
            )
            result = cursor.fetchone()

            if not result:
                await interaction.response.send_message(
                    f"❌ Role information for '{self.product_name}' could not be found. Please contact support.",
                    ephemeral=True
                )
                return

            role_id = result["role_id"]
            role = disnake.utils.get(guild.roles, id=int(role_id))

            if not role:
                await interaction.response.send_message(
                    f"❌ The role associated with this product is missing or was deleted. Please contact support.",
                    ephemeral=True
                )
                return

            # Assign the role to the user
            await user.add_roles(role)
            await interaction.response.send_message(
                f"🎉 {user.mention}, your license for '{self.product_name}' is verified! Role '{role.name}' has been assigned.",
                ephemeral=True
            )

        except requests.exceptions.RequestException as e:
            logging.error(f"Error contacting Payhip API: {e}")
            await interaction.response.send_message(
                "❌ Unable to contact the verification server. Please try again later.",
                ephemeral=True
            )

def run():
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=8080, debug=False), daemon=True).start()
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    run()
