from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.listing import Listing
from models.order import Order
from models.review import Review
from models.user import User
from models.watchlist import Watchlist
from routers.auth import get_current_user
from schemas.listing import ListingResponse
from schemas.order import OrderResponse, ReviewResponse
from schemas.user import UserPublicResponse, UserResponse, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])


# ── Current User ──────────────────────────────────────────────────────────────


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.put("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await db.flush()
    return UserResponse.model_validate(current_user)


@router.get("/me/listings", response_model=list[ListingResponse])
async def my_listings(
    status: str = Query("active", regex="^(active|sold|expired|removed)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Listing)
        .where(Listing.seller_id == current_user.id, Listing.status == status)
        .order_by(Listing.created_at.desc())
    )
    result = await db.execute(query)
    return [ListingResponse.model_validate(item) for item in result.scalars().all()]


@router.get("/me/orders", response_model=list[OrderResponse])
async def my_purchases(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Order).where(Order.buyer_id == current_user.id).order_by(Order.created_at.desc())
    result = await db.execute(query)
    return [OrderResponse.model_validate(o) for o in result.scalars().all()]


@router.get("/me/sales", response_model=list[OrderResponse])
async def my_sales(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Order).where(Order.seller_id == current_user.id).order_by(Order.created_at.desc())
    result = await db.execute(query)
    return [OrderResponse.model_validate(o) for o in result.scalars().all()]


# ── Watchlist ─────────────────────────────────────────────────────────────────


@router.get("/me/watchlist")
async def my_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload

    query = select(Watchlist).where(Watchlist.user_id == current_user.id).options(selectinload(Watchlist.card))
    result = await db.execute(query)
    items = result.scalars().all()
    return [
        {
            "id": str(w.id),
            "card_id": str(w.card_id),
            "card_name": w.card.name if w.card else None,
            "card_set": w.card.set_name if w.card else None,
            "price_alert_cents": w.price_alert_cents,
            "created_at": w.created_at.isoformat(),
        }
        for w in items
    ]


@router.post("/me/watchlist", status_code=201)
async def add_to_watchlist(
    card_id: UUID,
    price_alert_cents: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check if already watching
    existing = await db.execute(
        select(Watchlist).where(Watchlist.user_id == current_user.id, Watchlist.card_id == card_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already in watchlist")

    item = Watchlist(user_id=current_user.id, card_id=card_id, price_alert_cents=price_alert_cents)
    db.add(item)
    await db.flush()
    return {"id": str(item.id), "message": "Added to watchlist"}


@router.delete("/me/watchlist/{card_id}", status_code=204)
async def remove_from_watchlist(
    card_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Watchlist).where(Watchlist.user_id == current_user.id, Watchlist.card_id == card_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Not in watchlist")
    await db.delete(item)


# ── Public User Profile ───────────────────────────────────────────────────────


@router.get("/{user_id}", response_model=UserPublicResponse)
async def get_user_profile(user_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserPublicResponse.model_validate(user)


@router.get("/{user_id}/reviews", response_model=list[ReviewResponse])
async def get_user_reviews(user_id: UUID, db: AsyncSession = Depends(get_db)):
    query = select(Review).where(Review.reviewed_id == user_id).order_by(Review.created_at.desc())
    result = await db.execute(query)
    return [ReviewResponse.model_validate(r) for r in result.scalars().all()]
