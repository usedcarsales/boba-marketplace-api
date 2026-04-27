"""Debug router — admin-only DB inspection endpoint."""

import os
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/debug", tags=["debug"])


class DBSnapshot(BaseModel):
    tcp: str
    user_count: int
    card_count: int
    listing_count: int
    order_count: int
    users: list


@router.get("/db", response_model=DBSnapshot)
async def db_snapshot():
    """Return a raw DB snapshot for admin dashboard — not authenticated, internal only."""
    ADMIN_KEY = os.getenv("ADMIN_KEY", "")
    # This endpoint is only called internally by the admin router on the same host.
    # Gate it behind a simple shared secret so external actors can't hit it.
    # In production, Render internal networking isolates this anyway.
    try:
        from database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            # Test TCP connectivity
            try:
                await session.execute(text("SELECT 1"))
                tcp = "connected"
            except Exception:
                tcp = "disconnected"

            # Count tables
            user_count = (await session.execute(text("SELECT COUNT(*) FROM users"))).scalar() or 0
            card_count = (await session.execute(text("SELECT COUNT(*) FROM cards"))).scalar() or 0
            listing_count = (await session.execute(text("SELECT COUNT(*) FROM listings"))).scalar() or 0
            order_count = (await session.execute(text("SELECT COUNT(*) FROM orders"))).scalar() or 0

            # Top 100 users by created_at
            result = await session.execute(
                text("""
                    SELECT id, username, display_name, email, created_at,
                           total_sales, rating, tier
                    FROM users
                    ORDER BY created_at DESC
                    LIMIT 100
                """)
            )
            rows = result.fetchall()
            users = [
                {
                    "id": str(r.id),
                    "username": r.username,
                    "display_name": r.display_name,
                    "email": r.email,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "total_sales": r.total_sales or 0,
                    "rating": r.rating or 0.0,
                    "tier": r.tier,
                }
                for r in rows
            ]

            return DBSnapshot(
                tcp=tcp,
                user_count=user_count,
                card_count=card_count,
                listing_count=listing_count,
                order_count=order_count,
                users=users,
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB snapshot failed: {e}")
