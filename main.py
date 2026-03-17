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
