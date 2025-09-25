# Replace your utils/database.py initialize_database function with this:

import asyncpg
import asyncio
import os
from dotenv import load_dotenv
from utils.encryption import decrypt_data, encrypt_data

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
database_pool = None

async def initialize_database():
    global database_pool
    
    if not DATABASE_URL:
        print("❌ DATABASE_URL environment variable is not set!")
        raise ValueError("DATABASE_URL is required")
    
    # Fix Railway PostgreSQL URL format
    db_url = DATABASE_URL
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
        print("🔧 Fixed postgres:// URL to postgresql://")
    
    print(f"🔌 Connecting to database: {db_url[:30]}...")
    
    # Test basic connection first
    print("🧪 Testing database connection...")
    try:
        test_conn = await asyncio.wait_for(
            asyncpg.connect(db_url),
            timeout=15
        )
        result = await test_conn.fetchval("SELECT 1")
        await test_conn.close()
        print(f"✅ Database connection test successful: {result}")
    except asyncio.TimeoutError:
        print("❌ Database connection timeout (15s)")
        print("Check if your DATABASE_URL is correct in Railway dashboard")
        raise
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("This usually means:")
        print("  • DATABASE_URL is wrong")
        print("  • Database server is not running")
        print("  • Network connectivity issues")
        raise
    
    # Create connection pool
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"🔄 Creating connection pool (attempt {attempt + 1}/{max_retries})...")
            
            database_pool = await asyncio.wait_for(
                asyncpg.create_pool(
                    db_url,
                    min_size=1,
                    max_size=3,  # Reduced for Railway
                    command_timeout=30,
                    server_settings={
                        'jit': 'off',
                        'statement_timeout': '30000'
                    }
                ),
                timeout=20
            )
            
            # Test the pool
            async with database_pool.acquire() as conn:
                await conn.fetchval("SELECT version()")
            
            print("✅ Database pool created successfully!")
            break
            
        except Exception as e:
            print(f"❌ Pool creation failed (attempt {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2)
    
    # Create tables
    await create_essential_tables()

async def create_essential_tables():
    """Create only essential tables first"""
    print("📋 Creating essential database tables...")
    
    essential_tables = {
        "products": """
            CREATE TABLE IF NOT EXISTS products (
                guild_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                product_secret TEXT NOT NULL,
                role_id TEXT,
                stock INTEGER DEFAULT -1,
                PRIMARY KEY (guild_id, product_name)
            )
        """,
        "verification_message": """
            CREATE TABLE IF NOT EXISTS verification_message (
                guild_id TEXT NOT NULL PRIMARY KEY,
                message_id TEXT,
                channel_id TEXT
            )
        """,
        "verified_licenses": """
            CREATE TABLE IF NOT EXISTS verified_licenses (
                user_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                license_key TEXT NOT NULL,
                PRIMARY KEY (user_id, guild_id, product_name)
            )
        """
    }
    
    async with database_pool.acquire() as conn:
        for table_name, sql in essential_tables.items():
            try:
                await conn.execute(sql)
                print(f"✅ Created table: {table_name}")
            except Exception as e:
                print(f"❌ Failed to create {table_name}: {e}")
                raise

async def get_database_pool():
    if database_pool is None:
        raise ValueError("Database not initialized. Call initialize_database() first.")
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
