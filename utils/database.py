import asyncpg
from utils.encryption import decrypt_data
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

database_pool = None

async def initialize_database():
    """Initialize the database and create required tables."""
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
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS verification_message (
            guild_id TEXT NOT NULL PRIMARY KEY,
            message_id TEXT,
            channel_id TEXT
        )
        """)
    print("Database initialized.")

async def get_database_pool():
    if database_pool is None:
        raise ValueError("Database not initialized. Call `initialize_database` first.")
    return database_pool

async def fetch_products(guild_id):
    """Fetch products for a specific guild."""
    async with (await get_database_pool()).acquire() as conn:
        rows = await conn.fetch(
            "SELECT product_name, product_secret FROM products WHERE guild_id = $1", guild_id
        )
        return {row["product_name"]: decrypt_data(row["product_secret"]) for row in rows}
