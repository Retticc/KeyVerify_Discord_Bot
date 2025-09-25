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
        raise ValueError("DATABASE_URL environment variable is not set!")
    
    print(f"Database URL configured: {DATABASE_URL[:20]}...")  # Log partial URL for debugging
    
    max_retries = 3  # Reduced from 5
    retry_delay = 2  # Reduced from 5
    
    for attempt in range(max_retries):
        try:
            print(f"Attempting database connection {attempt + 1}/{max_retries}...")
            
            # Shorter timeout and more aggressive connection settings
            database_pool = await asyncio.wait_for(
                asyncpg.create_pool(
                    DATABASE_URL,
                    min_size=1,
                    max_size=5,  # Reduced pool size
                    command_timeout=30,  # Reduced from 60
                    server_settings={
                        'jit': 'off',
                        'statement_timeout': '30000',  # 30 seconds
                    }
                ),
                timeout=15  # Reduced timeout
            )
            
            # Test the connection immediately
            async with database_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            
            print("✅ Database connection successful!")
            await create_tables()
            return
            
        except asyncio.TimeoutError:
            print(f"❌ Database connection timeout on attempt {attempt + 1}")
        except Exception as e:
            print(f"❌ Database error on attempt {attempt + 1}: {str(e)}")
        
        if attempt < max_retries - 1:
            print(f"Retrying in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
    
    raise Exception("Failed to connect to database after all attempts")

async def create_tables():
    """Separate function for table creation to avoid timeout issues"""
    print("Creating database tables...")
    
    async with database_pool.acquire() as conn:
        # Create tables one by one with error handling
        tables = [
            ("products", """
                CREATE TABLE IF NOT EXISTS products (
                    guild_id TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    product_secret TEXT NOT NULL,
                    role_id TEXT,
                    stock INTEGER DEFAULT -1,
                    PRIMARY KEY (guild_id, product_name)
                )
            """),
            ("verification_message", """
                CREATE TABLE IF NOT EXISTS verification_message (
                    guild_id TEXT NOT NULL PRIMARY KEY,
                    message_id TEXT,
                    channel_id TEXT
                )
            """),
            ("verified_licenses", """
                CREATE TABLE IF NOT EXISTS verified_licenses (
                    user_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    license_key TEXT NOT NULL,
                    PRIMARY KEY (user_id, guild_id, product_name)
                )
            """),
            # Add other essential tables here...
        ]
        
        for table_name, sql in tables:
            try:
                await conn.execute(sql)
                print(f"✅ Created/verified table: {table_name}")
            except Exception as e:
                print(f"❌ Error creating table {table_name}: {e}")
                # Continue with other tables instead of failing completely

async def get_database_pool():
    if database_pool is None:
        raise ValueError("Database not initialized. Call initialize_database() first.")
    return database_pool

# Rest of your functions remain the same...
