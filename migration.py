# migration.py - Complete migration for dual payment system

import asyncio
import os
from dotenv import load_dotenv
import asyncpg

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

async def migrate_database():
    """Migrate existing database to support dual payment methods"""
    
    if not DATABASE_URL:
        print("❌ DATABASE_URL environment variable is not set!")
        return
        
    if DATABASE_URL.startswith('postgres://'):
        db_url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    else:
        db_url = DATABASE_URL
    
    print("🔄 Starting dual payment system migration...")
    
    conn = await asyncpg.connect(db_url)
    
    try:
        # Step 1: Add new columns for dual payment support
        print("💳 Adding dual payment columns to products table...")
        
        await conn.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS payment_methods TEXT")
        await conn.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS payhip_secret TEXT") 
        await conn.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS gamepass_id TEXT")
        await conn.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS roblox_cookie TEXT")
        await conn.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT")
        
        print("✅ Added payment_methods, payhip_secret, gamepass_id, roblox_cookie, description columns")
        
        # Step 2: Migrate existing single-payment products
        print("🔄 Migrating existing products to dual payment format...")
        
        existing_products = await conn.fetch("SELECT * FROM products")
        
        for product in existing_products:
            # Check if this product already has payment_methods configured
            if product.get('payment_methods'):
                continue  # Skip already migrated products
                
            # Determine what kind of product this was
            has_product_secret = bool(product.get('product_secret'))
            product_type = product.get('product_type', 'payhip')
            
            payment_methods = ""
            payhip_secret = None
            gamepass_id = None
            roblox_cookie = None
            
            if product_type == 'roblox' and has_product_secret:
                # This was a Roblox-only product
                payment_methods = "robux:Robux Price"  # Default price text
                roblox_cookie = product['product_secret']  # Cookie was stored as secret
                gamepass_id = product.get('gamepass_id')
            elif has_product_secret:
                # This was a PayHip-only product
                payment_methods = "usd:USD Price"  # Default price text
                payhip_secret = product['product_secret']  # PayHip secret
            
            # Update the product with new format
            if payment_methods:
                await conn.execute("""
                    UPDATE products SET 
                        payment_methods = $1,
                        payhip_secret = $2,
                        gamepass_id = $3,
                        roblox_cookie = $4
                    WHERE guild_id = $5 AND product_name = $6
                """, payment_methods, payhip_secret, gamepass_id, roblox_cookie, 
                    product['guild_id'], product['product_name'])
        
        print("✅ Migrated existing products to dual payment format")
        
        # Step 3: Create roblox_verified_users table if it doesn't exist
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
        
        # Step 4: Clean up old columns (optional - you can keep them for backup)
        print("🧹 Cleaning up old single-payment columns...")
        
        try:
            # Only drop if they exist and we've successfully migrated
            await conn.execute("ALTER TABLE products DROP COLUMN IF EXISTS product_type")
            await conn.execute("ALTER TABLE products DROP COLUMN IF EXISTS product_secret")
            print("✅ Removed old single-payment columns")
        except Exception as e:
            print(f"⚠️ Note: {e} (This is usually fine)")
        
        print("🎉 Migration completed successfully!")
        
        # Show sample products after migration
        sample_products = await conn.fetch("""
            SELECT guild_id, product_name, payment_methods, 
                   CASE WHEN payhip_secret IS NOT NULL THEN 'Yes' ELSE 'No' END as has_payhip,
                   CASE WHEN roblox_cookie IS NOT NULL THEN 'Yes' ELSE 'No' END as has_roblox,
                   gamepass_id
            FROM products LIMIT 5
        """)
        
        if sample_products:
            print("\n📋 Sample products after migration:")
            for product in sample_products:
                guild_name = f"Guild {product['guild_id'][:8]}..."
                payment_info = product['payment_methods'] or 'No payments configured'
                payhip_status = "💳" if product['has_payhip'] == 'Yes' else "❌"
                roblox_status = "🎮" if product['has_roblox'] == 'Yes' else "❌"
                
                print(f"  • {product['product_name']} [{guild_name}]")
                print(f"    Payment methods: {payment_info}")
                print(f"    PayHip: {payhip_status} | Roblox: {roblox_status}")
                if product['gamepass_id']:
                    print(f"    Gamepass ID: {product['gamepass_id']}")
                print()
        
        print("💡 Next steps:")
        print("  1. Replace your bot files with the dual payment versions")
        print("  2. Restart your bot")
        print("  3. Test adding a product with /add_product:")
        print("     - Enter both USD Price ($9.99) and Robux Price (350 Robux)")
        print("     - Configure both PayHip secret AND Roblox gamepass")
        print("  4. Users will now see both payment options when verifying!")
        print("  5. Existing products should still work with their original payment method")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate_database())
