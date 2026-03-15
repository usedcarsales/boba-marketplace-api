from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from config import get_settings
from database import init_db
from routers import auth, cards, listings, orders, seller, users, webhooks

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
    from database import engine
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT current_database(), current_user, version()"))
            row = result.fetchone()
            
            # Check tables
            tables_result = await conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
            ))
            tables = [r[0] for r in tables_result.fetchall()]
            
            # Count cards
            if 'cards' in tables:
                count_result = await conn.execute(text("SELECT COUNT(*) FROM cards"))
                card_count = count_result.scalar()
            else:
                card_count = "table not found"
            
            return {
                "database": row[0],
                "user": row[1],
                "version": row[2][:50],
                "tables": tables,
                "card_count": card_count,
            }
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}
