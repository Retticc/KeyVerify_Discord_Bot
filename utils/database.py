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
            PRIMARY KEY (guild_id, product_name)
        )
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
        
    print("Database initialized.")
    
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
