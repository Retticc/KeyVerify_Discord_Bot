# Create this file as: migration.py - Run this once to update your database

import asyncio
import os
from dotenv import load_dotenv
import asyncpg

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

async def migrate_database():
    """Migrate existing database to support Roblox products"""
    
    if not DATABASE_URL:
        print("❌ DATABASE_URL environment variable is not set!")
        return
        
    if DATABASE_URL.startswith('postgres://'):
        db_url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    else:
        db_url = DATABASE_URL
    
    print("🔄 Starting database migration...")
    
    conn = await asyncpg.connect(db_url)
    
    try:
        # Add new columns to products table
        print("📊 Adding new columns to products table...")
        
        await conn.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS product_type TEXT DEFAULT 'payhip'")
        await conn.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS gamepass_id TEXT")
        await conn.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS price TEXT")
        await conn.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT")
        
        print("✅ Added product_type, gamepass_id, price, description columns")
        
        # Create roblox_verified_users table
        print("🎮 Creating roblox_verified_users table...")
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS roblox_verified_users (
                guild_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                discord_user_id TEXT NOT NULL,
                roblox_username TEXT NOT NULL,
                roblox_user_id TEXT NOT NULL,
                verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, product_name, discord_user_id)
            )
        """)
        
        print("✅ Created roblox_verified_users table")
        
        # Update any existing products to have payhip type
        result = await conn.execute("UPDATE products SET product_type = 'payhip' WHERE product_type IS NULL")
        print(f"✅ Updated existing products to payhip type")
        
        print("🎉 Migration completed successfully!")
        
        # Show current products
        products = await conn.fetch("SELECT guild_id, product_name, product_type, price FROM products LIMIT 10")
        if products:
            print("\n📋 Sample products after migration:")
            for product in products:
                guild_name = f"Guild {product['guild_id'][:8]}..."
                price_display = product['price'] or 'No price set'
                print(f"  • {product['product_name']} ({product['product_type']}) - {price_display} [{guild_name}]")
        
        print("\n💡 Next steps:")
        print("  1. Replace your bot files with the updated versions")
        print("  2. Restart your bot")
        print("  3. Try adding a Roblox product with /add_product")
        print("  4. Test verification with both license keys and Roblox usernames")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate_database())
