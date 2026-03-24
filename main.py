from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from config import get_settings
from database import init_db
from routers import auth, cards, listings, orders, sealed, seller, seller_tier, users, webhooks, feedback

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables
    await init_db()
    yield
    # Shutdown: cleanup if needed


app = FastAPI(
    title=settings.app_name,
    description="The marketplace for Bo Jackson Battle Arena cards and collectibles",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(cards.router)
app.include_router(listings.router)
app.include_router(orders.router)
app.include_router(users.router)
app.include_router(seller.router)
app.include_router(webhooks.router)
app.include_router(seller_tier.router)
app.include_router(feedback.router)
app.include_router(sealed.router)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/debug/db")
async def debug_db():
    """Debug database connection."""
    import socket
    import os
    results = {}
    
    # Check env var
    db_url = os.environ.get("DATABASE_URL", "NOT SET")
    results["db_url_set"] = db_url[:30] + "..." if len(db_url) > 30 else db_url
    
    # DNS resolve
    host = "ep-shiny-hall-antdzo3i-pooler.c-6.us-east-1.aws.neon.tech"
    try:
        ip = socket.getaddrinfo(host, 5432)
        results["dns"] = str(ip[0][4])
    except Exception as e:
        results["dns_error"] = str(e)
    
    # TCP connect
    try:
        s = socket.create_connection((host, 5432), timeout=10)
        results["tcp"] = "connected"
        s.close()
    except Exception as e:
        results["tcp_error"] = str(e)
    
    # SQLAlchemy connect
    from database import engine
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT current_database(), current_user"))
            row = result.fetchone()
            results["db"] = {"database": row[0], "user": row[1]}
            
            count_result = await conn.execute(text("SELECT COUNT(*) FROM cards"))
            results["card_count"] = count_result.scalar()
            
            user_result = await conn.execute(text("SELECT COUNT(*) FROM users"))
            results["user_count"] = user_result.scalar()
            
            # List users (just username + email, no passwords)
            users_result = await conn.execute(text("SELECT username, email, display_name, created_at FROM users ORDER BY created_at"))
            results["users"] = [{"username": r[0], "email": r[1], "display_name": r[2], "created_at": str(r[3])} for r in users_result.fetchall()]
    except Exception as e:
        results["db_error"] = str(e)
        results["db_error_type"] = type(e).__name__
    
    return results


@app.post("/debug/migrate-orders")
async def migrate_orders():
    """Add new columns to orders table for v2 transaction engine."""
    from database import engine
    migrations = [
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_fee_cents INTEGER DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS shipping_cents INTEGER DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS total_cents INTEGER DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS stripe_client_secret VARCHAR(500)",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS tracking_carrier VARCHAR(50)",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS shipping_method VARCHAR(50)",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS requires_insurance BOOLEAN DEFAULT FALSE",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS ship_to_name VARCHAR(255)",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS ship_to_address1 VARCHAR(255)",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS ship_to_address2 VARCHAR(255)",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS ship_to_city VARCHAR(100)",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS ship_to_state VARCHAR(50)",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS ship_to_zip VARCHAR(20)",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS ship_to_country VARCHAR(50) DEFAULT 'US'",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payout_released BOOLEAN DEFAULT FALSE",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payout_released_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS ship_by TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS seller_note TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS buyer_note TEXT",
        # Backfill total_cents for any existing orders
        "UPDATE orders SET total_cents = subtotal_cents + COALESCE(shipping_cents, 0) WHERE total_cents = 0 OR total_cents IS NULL",
    ]
    results = []
    try:
        async with engine.begin() as conn:
            for sql in migrations:
                try:
                    await conn.execute(text(sql))
                    results.append({"sql": sql[:60] + "...", "status": "ok"})
                except Exception as e:
                    results.append({"sql": sql[:60] + "...", "status": f"error: {e}"})
        return {"status": "migrated", "results": results}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/debug/migrate-v3")
async def migrate_v3():
    """Create seller_profiles, feedback tables and add source column to listings."""
    from database import engine
    migrations = [
        # Seller profiles table
        """CREATE TABLE IF NOT EXISTS seller_profiles (
            id UUID PRIMARY KEY,
            user_id UUID UNIQUE NOT NULL REFERENCES users(id),
            tier VARCHAR(20) NOT NULL DEFAULT 'recruit',
            rolling_30d_volume_cents INTEGER DEFAULT 0,
            total_sales_count INTEGER DEFAULT 0,
            total_sales_volume_cents INTEGER DEFAULT 0,
            active_listing_count INTEGER DEFAULT 0,
            avg_rating FLOAT,
            total_ratings INTEGER DEFAULT 0,
            avg_shipping_stars FLOAT,
            avg_condition_stars FLOAT,
            avg_comms_stars FLOAT,
            avg_accuracy_stars FLOAT,
            bio TEXT,
            banner_url VARCHAR(500),
            stripe_account_id VARCHAR(255),
            stripe_onboarded BOOLEAN DEFAULT FALSE,
            tier_upgraded_at TIMESTAMP,
            tier_grace_deadline TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        # Feedback table
        """CREATE TABLE IF NOT EXISTS feedback (
            id UUID PRIMARY KEY,
            order_id UUID UNIQUE NOT NULL REFERENCES orders(id),
            buyer_id UUID NOT NULL REFERENCES users(id),
            seller_id UUID NOT NULL REFERENCES users(id),
            overall_stars INTEGER NOT NULL CHECK (overall_stars >= 1 AND overall_stars <= 5),
            shipping_stars INTEGER CHECK (shipping_stars IS NULL OR (shipping_stars >= 1 AND shipping_stars <= 5)),
            condition_stars INTEGER CHECK (condition_stars IS NULL OR (condition_stars >= 1 AND condition_stars <= 5)),
            comms_stars INTEGER CHECK (comms_stars IS NULL OR (comms_stars >= 1 AND comms_stars <= 5)),
            accuracy_stars INTEGER CHECK (accuracy_stars IS NULL OR (accuracy_stars >= 1 AND accuracy_stars <= 5)),
            comment TEXT,
            seller_response TEXT,
            response_at TIMESTAMP,
            is_visible BOOLEAN DEFAULT TRUE,
            moderation_flag BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        # Add source column to listings
        "ALTER TABLE listings ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'manual'",
        # Indexes
        "CREATE INDEX IF NOT EXISTS idx_feedback_seller_id ON feedback(seller_id)",
        "CREATE INDEX IF NOT EXISTS idx_feedback_buyer_id ON feedback(buyer_id)",
        "CREATE INDEX IF NOT EXISTS idx_seller_profiles_user_id ON seller_profiles(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_listings_source ON listings(source)",
    ]
    results = []
    try:
        async with engine.begin() as conn:
            for sql in migrations:
                try:
                    await conn.execute(text(sql))
                    results.append({"sql": sql[:80] + "...", "status": "ok"})
                except Exception as e:
                    results.append({"sql": sql[:80] + "...", "status": f"error: {e}"})
        return {"status": "migrated", "count": len(results), "results": results}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/debug/migrate-v4")
async def migrate_v4():
    """Add discord_id and google_id columns to users table for OAuth."""
    try:
        from database import engine
        from sqlalchemy import text
        statements = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS discord_id VARCHAR(50) UNIQUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(100) UNIQUE",
            "CREATE INDEX IF NOT EXISTS ix_users_discord_id ON users (discord_id)",
            "CREATE INDEX IF NOT EXISTS ix_users_google_id ON users (google_id)",
        ]
        results = []
        async with engine.begin() as conn:
            for sql in statements:
                try:
                    await conn.execute(text(sql))
                    results.append({"sql": sql, "status": "ok"})
                except Exception as e:
                    results.append({"sql": sql, "status": f"error: {e}"})
        return {"status": "migrated", "count": len(results), "results": results}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/debug/migrate-v5-sealed")
async def migrate_v5_sealed():
    """Create sealed_products table and seed data."""
    try:
        from database import engine
        from sqlalchemy import text
        
        # Create table
        create_sql = """
        CREATE TABLE IF NOT EXISTS sealed_products (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            set_name VARCHAR(100) NOT NULL,
            product_type VARCHAR(50) NOT NULL,
            year INTEGER,
            msrp_cents INTEGER,
            description TEXT,
            image_url TEXT,
            cards_per_pack INTEGER,
            packs_per_box INTEGER,
            last_sale_price NUMERIC(10,2),
            avg_price_30d NUMERIC(10,2),
            total_sales INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
        
        seed_sql = """
        INSERT INTO sealed_products (name, set_name, product_type, year, msrp_cents, description, cards_per_pack, packs_per_box, last_sale_price, avg_price_30d, total_sales)
        VALUES
        -- Alpha Edition
        ('Alpha Edition Hobby Box', 'Alpha Edition', 'hobby_box', 2024, 14999, '24 packs per box. The original BoBA set featuring 200+ base cards, Battlefoils, and Superfoils. Chase the 1/1 Superfoils!', 10, 24, 189.99, 175.00, 85),
        ('Alpha Edition Booster Pack', 'Alpha Edition', 'booster_pack', 2024, 699, '10 cards per pack. Pull Heroes, Plays, and chase rare Battlefoil parallels from the original Alpha Edition set.', 10, NULL, 8.99, 7.50, 320),
        ('Alpha Edition Booster Box', 'Alpha Edition', 'booster_box', 2024, 12999, '24 packs of Alpha Edition. Guaranteed hits in every box.', 10, 24, 159.99, 150.00, 45),
        
        -- Griffey Edition
        ('Griffey Edition Hobby Box', 'Griffey Edition', 'hobby_box', 2024, 17999, 'The massive 10,000+ card Griffey Edition set. Hobby boxes include exclusive Battlefoil parallels and guaranteed Superfoil hits.', 10, 24, 249.99, 220.00, 62),
        ('Griffey Edition Booster Pack', 'Griffey Edition', 'booster_pack', 2024, 699, '10 cards per pack from the Griffey Edition. Features Ken Griffey Jr. themed Heroes and exclusive parallels.', 10, NULL, 9.99, 8.00, 280),
        ('Griffey Edition Booster Box', 'Griffey Edition', 'booster_box', 2024, 14999, '24 packs of Griffey Edition boosters. The largest BoBA set with 10,000+ cards to collect.', 10, 24, 199.99, 185.00, 38),
        ('Griffey Edition Jumbo Pack', 'Griffey Edition', 'jumbo_pack', 2024, 1999, 'Oversized pack with 30 cards including guaranteed Battlefoil parallel. Griffey Edition exclusive.', 30, NULL, 24.99, 22.00, 95),
        
        -- Alpha Update
        ('Alpha Update Hobby Box', 'Alpha Update', 'hobby_box', 2025, 14999, 'The latest expansion with new Heroes, Plays, and updated game mechanics. 24 packs per hobby box.', 10, 24, 169.99, 160.00, 40),
        ('Alpha Update Booster Pack', 'Alpha Update', 'booster_pack', 2025, 699, '10 cards per pack from Alpha Update. New weapons, new abilities, new chase cards.', 10, NULL, 7.99, 7.00, 200),
        ('Alpha Update Booster Box', 'Alpha Update', 'booster_box', 2025, 12999, '24 packs of Alpha Update. Continues the Alpha Edition story with new content.', 10, 24, 149.99, 140.00, 30),
        
        -- Special Products
        ('Blast Box', 'Alpha Blast', 'blast_box', 2024, 4999, 'Exclusive Blast Box containing HTD (Blast Play) cards. Limited availability — the only way to pull Alpha Blast HTD cards.', 15, NULL, 79.99, 65.00, 55),
        ('Battle Trainer Kit', 'Battle Trainer Kit', 'starter_kit', 2024, 2499, 'Two ready-to-play 60-card decks with learn-to-play guide. Perfect for new players. Includes exclusive Trainer Kit cards.', 60, 2, 29.99, 28.00, 120),
        ('National 2024 Starter Set', 'National 24 Starter Set', 'starter_kit', 2024, 1999, 'Exclusive starter set from the 2024 National Sports Card Convention. Limited edition with convention-exclusive cards.', 30, NULL, 39.99, 35.00, 25),
        ('Big League Chew Promo Box', 'Big League Chew', 'promo_box', 2024, 999, 'Special collaboration with Big League Chew. Includes exclusive gum-themed BoBA cards and actual Big League Chew gum!', 5, NULL, 14.99, 12.00, 150),
        
        -- Cases
        ('Alpha Edition Hobby Case', 'Alpha Edition', 'hobby_case', 2024, 84999, '6 Hobby Boxes per case (144 packs total). Best value for ripping Alpha Edition. Case hits guaranteed.', 10, 144, 999.99, 950.00, 12),
        ('Griffey Edition Hobby Case', 'Griffey Edition', 'hobby_case', 2024, 99999, '6 Hobby Boxes per case (144 packs total). The ultimate Griffey Edition experience.', 10, 144, 1299.99, 1200.00, 8)
        ON CONFLICT DO NOTHING
        """
        
        results = []
        async with engine.begin() as conn:
            await conn.execute(text(create_sql))
            results.append({"step": "create_table", "status": "ok"})
            
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sealed_name ON sealed_products (name)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sealed_set ON sealed_products (set_name)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sealed_type ON sealed_products (product_type)"))
            results.append({"step": "indexes", "status": "ok"})
            
            await conn.execute(text(seed_sql))
            
            count = (await conn.execute(text("SELECT COUNT(*) FROM sealed_products"))).scalar()
            results.append({"step": "seed", "status": "ok", "count": count})
        
        return {"status": "ok", "results": results}
    except Exception as e:
        return {"status": "error", "error": str(e)}
