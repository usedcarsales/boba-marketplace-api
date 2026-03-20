from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from config import get_settings
from database import init_db
from routers import auth, cards, listings, orders, seller, seller_tier, users, webhooks, feedback

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
