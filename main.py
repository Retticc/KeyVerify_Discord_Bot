import disnake
from disnake.ext import commands
import requests
import sqlite3
from dotenv import load_dotenv
import os
from flask import Flask
import asyncio
from uvicorn import Config, Server

# Flask app for health check
app = Flask(__name__)

# Health check route
@app.route('/')
def health_check():
    return "OK", 200

# Load environment variables from the .env file
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # Default to INFO if not specified

# Database setup
def get_database_connection(database_url):
    if database_url.startswith("sqlite"):
        # SQLite database
        conn = sqlite3.connect(database_url.split("sqlite:///")[1])
        conn.row_factory = sqlite3.Row  # Enable column access by name
    elif database_url.startswith("postgresql"):
        # PostgreSQL database
        import psycopg2
        from psycopg2.extras import DictCursor
        conn = psycopg2.connect(database_url, cursor_factory=DictCursor)
    else:
        raise ValueError(f"Unsupported database type: {database_url}")
    return conn

try:
    conn = get_database_connection(DATABASE_URL)
    cursor = conn.cursor()

    # Ensure the table exists
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        guild_id TEXT NOT NULL,
        product_name TEXT NOT NULL,
        product_secret TEXT NOT NULL,
        PRIMARY KEY (guild_id, product_name)
    )
    """)
    conn.commit()
    print("Database connected and ready.")
except Exception as e:
    print(f"Error initializing the database: {e}")
    exit(1)

intents = disnake.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
bot = commands.InteractionBot(intents=intents)

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}!")
    try:
        await bot.tree.sync()  # Sync commands with Discord
        print("Commands have been synchronized.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


# Helper function to fetch products for a guild
def fetch_products(guild_id):
    cursor.execute("SELECT product_name, product_secret FROM products WHERE guild_id = ?", (guild_id,))
    return {row[0]: row[1] for row in cursor.fetchall()}


class ProductSelectionView(disnake.ui.View):
    def __init__(self, products, license_key):
        super().__init__(timeout=60)  # Timeout after 60 seconds
        self.products = products
        self.license_key = license_key

        # Add dropdown to the view
        self.dropdown = disnake.ui.StringSelect(
            placeholder="Select a product",
            options=[
                disnake.SelectOption(label=name, description=f"Verify license for {name}")
                for name in products.keys()
            ]
        )
        self.dropdown.callback = self.select_callback  # Bind the callback to the dropdown
        self.add_item(self.dropdown)

    async def select_callback(self, interaction: disnake.MessageInteraction):
        # Get selected product
        product_name = interaction.data["values"][0]
        product_secret_key = self.products[product_name]
        license_key = self.license_key

        # Verify the license key
        PAYHIP_VERIFY_URL = f"https://payhip.com/api/v2/license/verify?license_key={license_key}"
        headers = {"product-secret-key": product_secret_key}
        response = requests.get(PAYHIP_VERIFY_URL, headers=headers)

        if response.status_code == 200 and (data := response.json().get("data")):
            if not data["enabled"]:
                await interaction.response.send_message(
                    "❌ This license is not enabled. Please contact support.",
                    ephemeral=True
                )
                return

            # Check license usage
            if data["uses"] > 0:
                await interaction.response.send_message(
                    f"❌ This license has already been used {data['uses']} times.",
                    ephemeral=True
                )
                return

            # Assign role for verified license
            user = interaction.author
            role_name = f"Verified-{product_name}"
            guild = interaction.guild
            role = disnake.utils.get(guild.roles, name=role_name)

            if not role:
                role = await guild.create_role(name=role_name)

            await user.add_roles(role)
            await interaction.response.send_message(
                f"🎉 {user.mention}, your license for '{product_name}' is verified! Role '{role_name}' has been assigned.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Invalid license key or product secret.",
                ephemeral=True
            )


# Verify a license for a product
@bot.slash_command(description="Verify your product license key.")
async def verify(
    inter: disnake.ApplicationCommandInteraction,
    license_key: str = commands.Param(description="Enter your license key")
):
    # Fetch products for the current guild
    products = fetch_products(str(inter.guild.id))

    # No products in the guild
    if not products:
        await inter.response.send_message("❌ No products are registered for this server.", ephemeral=True)
        return

    # Show dropdown menu to select product
    view = ProductSelectionView(products, license_key)
    await inter.response.send_message("Select a product to verify:", view=view, ephemeral=True)


async def start_flask():
    """Start Flask server using Uvicorn."""
    config = Config(app, host="0.0.0.0", port=8080, log_level="info")
    server = Server(config)
    await server.serve()

async def start_discord_bot():
    """Start the Discord bot."""
    await bot.start(DISCORD_TOKEN)

async def main():
    """Run Flask server and Discord bot concurrently."""
    await asyncio.gather(
        start_flask(),
        start_discord_bot()
    )

if __name__ == "__main__":
    asyncio.run(main())
