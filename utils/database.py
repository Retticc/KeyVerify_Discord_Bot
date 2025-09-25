import asyncpg
from utils.encryption import decrypt_data, encrypt_data
from dotenv import load_dotenv
import os

load_dotenv() # Load environment variables from .env file

DATABASE_URL = os.getenv("DATABASE_URL") # Get the database URL from environment

database_pool = None  # Global variable to hold the asyncpg connection pool

# Initializes the PostgreSQL database and required tables
async def initialize_database():
    global database_pool
    database_pool = await asyncpg.create_pool(DATABASE_URL)
    async with database_pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            guild_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            product_secret TEXT NOT NULL,
            role_id TEXT,
            stock INTEGER DEFAULT -1,
            PRIMARY KEY (guild_id, product_name)
        )
        """)
        
        # Add stock column to existing products table if it doesn't exist
        await conn.execute("""
            ALTER TABLE products 
            ADD COLUMN IF NOT EXISTS stock INTEGER DEFAULT -1
        """)
        
        # Table for tracking the verification message position per guild
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS verification_message (
            guild_id TEXT NOT NULL PRIMARY KEY,
            message_id TEXT,
            channel_id TEXT
        )
        """)
        # Stores verified licenses to avoid re-verification
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS verified_licenses (
            user_id TEXT NOT NULL,
            guild_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            license_key TEXT NOT NULL,
            PRIMARY KEY (user_id, guild_id, product_name)
        )
        """)
        
        # Table for tracking ticket boxes
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_boxes (
                guild_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                PRIMARY KEY (guild_id, message_id)
            );
        """)
        
        # Table for tracking active tickets
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS active_tickets (
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                product_name TEXT,
                ticket_number INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, channel_id)
            );
        """)
        
        # Table for ticket counter per guild
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_counters (
                guild_id TEXT PRIMARY KEY,
                counter INTEGER DEFAULT 0
            );
        """)
        
        # Table for stock display channels
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_channels (
                guild_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                category_id TEXT,
                PRIMARY KEY (guild_id, product_name)
            );
        """)

        # Table for ticket customization
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_customization (
                guild_id TEXT PRIMARY KEY,
                title TEXT DEFAULT 'Support Tickets',
                description TEXT DEFAULT 'Need help with one of our products? Click the button below to create a support ticket!

**What happens next?**
• Select the product you need help with
• A private channel will be created for you
• Provide your license key for verification
• Get personalized support from our team',
                button_text TEXT DEFAULT 'Create Ticket',
                button_emoji TEXT DEFAULT '🎫',
                show_stock_info BOOLEAN DEFAULT TRUE
            );
        """)

        # Table for custom messages
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

        # Table for ticket categories
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_categories (
                guild_id TEXT NOT NULL,
                category_name TEXT NOT NULL,
                category_description TEXT NOT NULL,
                display_order INTEGER NOT NULL DEFAULT 0,
                emoji TEXT DEFAULT '🎫',
                PRIMARY KEY (guild_id, category_name)
            );
        """)

        # Table for role permissions - FIXED
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS role_permissions (
                guild_id TEXT NOT NULL,
                role_id TEXT NOT NULL,
                permission_type TEXT NOT NULL,
                PRIMARY KEY (guild_id, role_id, permission_type)
            );
        """)
        
        # Table for auto-roles - FIXED
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_roles (
                guild_id TEXT NOT NULL,
                role_type TEXT NOT NULL,
                role_id TEXT NOT NULL,
                product_name TEXT,
                PRIMARY KEY (guild_id, role_type, role_id, COALESCE(product_name, ''))
            );
        """)

        # Table for bot settings
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                guild_id TEXT NOT NULL,
                setting_name TEXT NOT NULL,
                setting_value TEXT NOT NULL,
                PRIMARY KEY (guild_id, setting_name)
            );
        """)

        # Table for server log channels
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS server_log_channels (
                guild_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL
            );
        """)

        # Table for ticket category assignments
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_category_assignments (
                guild_id TEXT NOT NULL,
                ticket_type TEXT NOT NULL,
                category_id TEXT NOT NULL,
                product_name TEXT,
                PRIMARY KEY (guild_id, ticket_type, COALESCE(product_name, ''))
            );
        """)

        # Table for ticket category to Discord category mapping
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_category_channels (
                guild_id TEXT NOT NULL,
                category_name TEXT NOT NULL,
                discord_category_id TEXT NOT NULL,
                PRIMARY KEY (guild_id, category_name)
            );
        """)
         await conn.execute("""
            CREATE TABLE IF NOT EXISTS product_sales (
                guild_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                total_sold INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, product_name)
            );
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS review_settings (
                guild_id TEXT PRIMARY KEY,
                review_channel_id TEXT NOT NULL
            );
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_reviews (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id, product_name)
            );
        """)
        
    print("Database initialized with sales tracking and review system.")
    
# Provides access to the shared asyncpg connection pool
async def get_database_pool():
    if database_pool is None:
        raise ValueError("Database not initialized. Call `initialize_database` first.")
    return database_pool

# Retrieves all product names and decrypted secrets for a given guild
async def fetch_products(guild_id):
    async with (await get_database_pool()).acquire() as conn:
        rows = await conn.fetch(
            "SELECT product_name, product_secret FROM products WHERE guild_id = $1", guild_id
        )
        return {row["product_name"]: decrypt_data(row["product_secret"]) for row in rows}

# Retrieves all products with stock information for a given guild
async def fetch_products_with_stock(guild_id):
    async with (await get_database_pool()).acquire() as conn:
        rows = await conn.fetch(
            "SELECT product_name, product_secret, stock FROM products WHERE guild_id = $1", guild_id
        )
        return {
            row["product_name"]: {
                "secret": decrypt_data(row["product_secret"]),
                "stock": row["stock"] if row["stock"] is not None else -1
            } 
            for row in rows
        }
    
# Saves a verified license to the database (avoids duplicate entries)
async def save_verified_license(user_id, guild_id, product_name, license_key):
    encrypted_key = encrypt_data(license_key)
    async with (await get_database_pool()).acquire() as conn:
        await conn.execute(
            """
            INSERT INTO verified_licenses (user_id, guild_id, product_name, license_key)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id, guild_id, product_name)
            DO NOTHING
            """,
            str(user_id), str(guild_id), product_name, encrypted_key
        )
        
# Fetches a previously saved license key for a user if it exists
async def get_verified_license(user_id, guild_id, product_name):
    """Retrieve the verified license for a user, guild, and product."""
    async with (await get_database_pool()).acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT license_key FROM verified_licenses
            WHERE user_id = $1 AND guild_id = $2 AND product_name = $3
            """,
            str(user_id), str(guild_id), product_name
        )
        return decrypt_data(row["license_key"]) if row else None
