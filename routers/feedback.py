"""Feedback endpoints — buyer reviews + seller responses."""

from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.feedback import (
    Feedback, FEEDBACK_COOLDOWN_HOURS, FEEDBACK_WINDOW_DAYS,
    MIN_ACCOUNT_AGE_DAYS, VELOCITY_LIMIT, SELLER_RESPONSE_WINDOW_DAYS,
    SELLER_RESPONSE_MAX_CHARS, BUYER_COMMENT_MAX_CHARS,
)
from models.order import Order
from models.user import User
from models.seller_tier import SellerProfile
from routers.auth import get_current_user

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


# --- Schemas ---

class FeedbackCreate(BaseModel):
    order_id: str
    overall_stars: int = Field(ge=1, le=5)
    shipping_stars: int | None = Field(None, ge=1, le=5)
    condition_stars: int | None = Field(None, ge=1, le=5)
    comms_stars: int | None = Field(None, ge=1, le=5)
    accuracy_stars: int | None = Field(None, ge=1, le=5)
    comment: str | None = Field(None, max_length=BUYER_COMMENT_MAX_CHARS)


class SellerResponseCreate(BaseModel):
    response: str = Field(max_length=SELLER_RESPONSE_MAX_CHARS)


class FeedbackOut(BaseModel):
    id: str
    order_id: str
    buyer_username: str | None = None
    overall_stars: int
    shipping_stars: int | None = None
    condition_stars: int | None = None
    comms_stars: int | None = None
    accuracy_stars: int | None = None
    comment: str | None = None
    seller_response: str | None = None
    response_at: datetime | None = None
    created_at: datetime


class SellerRatingSummary(BaseModel):
    avg_overall: float | None = None
    avg_shipping: float | None = None
    avg_condition: float | None = None
    avg_comms: float | None = None
    avg_accuracy: float | None = None
    total_ratings: int = 0
    positive_count: int = 0  # 4-5 stars
    neutral_count: int = 0   # 3 stars
    negative_count: int = 0  # 1-2 stars


# --- Endpoints ---

@router.post("", response_model=FeedbackOut)
async def submit_feedback(
    data: FeedbackCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit feedback for a completed order. Anti-gaming checks enforced."""
    now = datetime.utcnow()

    # Check account age
    buyer = await db.get(User, user.id)
    if not buyer:
        raise HTTPException(404, "User not found")
    if (now - buyer.created_at).days < MIN_ACCOUNT_AGE_DAYS:
        raise HTTPException(403, f"Account must be at least {MIN_ACCOUNT_AGE_DAYS} days old to leave feedback")

    # Get order
    order = await db.get(Order, data.order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if str(order.buyer_id) != str(user.id):
        raise HTTPException(403, "Only the buyer can leave feedback")
    if order.status not in ("delivered", "completed"):
        raise HTTPException(400, "Order must be delivered before leaving feedback")

    # Check cooldown (48hrs after delivery)
    if order.delivered_at:
        cooldown_end = order.delivered_at + timedelta(hours=FEEDBACK_COOLDOWN_HOURS)
        if now < cooldown_end:
            hours_left = (cooldown_end - now).total_seconds() / 3600
            raise HTTPException(400, f"Feedback opens in {hours_left:.0f} hours (48hr cooldown after delivery)")

    # Check window (60 days)
    if order.delivered_at:
        window_end = order.delivered_at + timedelta(days=FEEDBACK_WINDOW_DAYS)
        if now > window_end:
            raise HTTPException(400, "Feedback window has closed (60 days after delivery)")

    # Check duplicate
    existing = await db.execute(
        select(Feedback).where(Feedback.order_id == data.order_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Feedback already submitted for this order")

    # Velocity check — 10+ in 24hrs triggers hold
    day_ago = now - timedelta(hours=24)
    velocity = await db.execute(
        select(func.count(Feedback.id)).where(
            and_(Feedback.buyer_id == str(user.id), Feedback.created_at >= day_ago)
        )
    )
    if velocity.scalar() >= VELOCITY_LIMIT:
        raise HTTPException(429, "Too many feedback submissions. Please try again later.")

    # Create feedback
    feedback = Feedback(
        order_id=data.order_id,
        buyer_id=str(user.id),
        seller_id=str(order.seller_id),
        overall_stars=data.overall_stars,
        shipping_stars=data.shipping_stars,
        condition_stars=data.condition_stars,
        comms_stars=data.comms_stars,
        accuracy_stars=data.accuracy_stars,
        comment=data.comment,
    )
    db.add(feedback)

    # Update seller profile rating aggregates
    await _update_seller_ratings(db, str(order.seller_id))

    await db.commit()
    await db.refresh(feedback)

    return FeedbackOut(
        id=feedback.id,
        order_id=feedback.order_id,
        buyer_username=buyer.username,
        overall_stars=feedback.overall_stars,
        shipping_stars=feedback.shipping_stars,
        condition_stars=feedback.condition_stars,
        comms_stars=feedback.comms_stars,
        accuracy_stars=feedback.accuracy_stars,
        comment=feedback.comment,
        created_at=feedback.created_at,
    )


@router.post("/{feedback_id}/respond")
async def seller_respond(
    feedback_id: str,
    data: SellerResponseCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Seller responds to feedback (300 chars, 30-day window)."""
    feedback = await db.get(Feedback, feedback_id)
    if not feedback:
        raise HTTPException(404, "Feedback not found")
    if str(feedback.seller_id) != str(user.id):
        raise HTTPException(403, "Only the seller can respond")
    if feedback.seller_response:
        raise HTTPException(409, "Already responded to this feedback")

    # Check 30-day response window
    window_end = feedback.created_at + timedelta(days=SELLER_RESPONSE_WINDOW_DAYS)
    if datetime.utcnow() > window_end:
        raise HTTPException(400, "Response window has closed (30 days)")

    feedback.seller_response = data.response
    feedback.response_at = datetime.utcnow()
    await db.commit()

    return {"status": "ok", "message": "Response submitted"}


@router.get("/seller/{seller_id}", response_model=list[FeedbackOut])
async def get_seller_feedback(
    seller_id: str,
    filter: str = "all",  # all, positive, neutral, negative
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Get feedback for a seller with optional filter."""
    query = select(Feedback).where(
        and_(Feedback.seller_id == seller_id, Feedback.is_visible == True)
    )

    if filter == "positive":
        query = query.where(Feedback.overall_stars >= 4)
    elif filter == "neutral":
        query = query.where(Feedback.overall_stars == 3)
    elif filter == "negative":
        query = query.where(Feedback.overall_stars <= 2)

    query = query.order_by(Feedback.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    feedbacks = result.scalars().all()

    # Get buyer usernames
    out = []
    for fb in feedbacks:
        buyer = await db.get(User, fb.buyer_id)
        out.append(FeedbackOut(
            id=fb.id,
            order_id=fb.order_id,
            buyer_username=buyer.username if buyer else "Anonymous",
            overall_stars=fb.overall_stars,
            shipping_stars=fb.shipping_stars,
            condition_stars=fb.condition_stars,
            comms_stars=fb.comms_stars,
            accuracy_stars=fb.accuracy_stars,
            comment=fb.comment,
            seller_response=fb.seller_response,
            response_at=fb.response_at,
            created_at=fb.created_at,
        ))
    return out


@router.get("/seller/{seller_id}/summary", response_model=SellerRatingSummary)
async def get_seller_rating_summary(
    seller_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated rating summary for a seller."""
    result = await db.execute(
        select(
            func.avg(Feedback.overall_stars),
            func.avg(Feedback.shipping_stars),
            func.avg(Feedback.condition_stars),
            func.avg(Feedback.comms_stars),
            func.avg(Feedback.accuracy_stars),
            func.count(Feedback.id),
            func.count(Feedback.id).filter(Feedback.overall_stars >= 4),
            func.count(Feedback.id).filter(Feedback.overall_stars == 3),
            func.count(Feedback.id).filter(Feedback.overall_stars <= 2),
        ).where(
            and_(Feedback.seller_id == seller_id, Feedback.is_visible == True)
        )
    )
    row = result.one()
    return SellerRatingSummary(
        avg_overall=round(row[0], 1) if row[0] else None,
        avg_shipping=round(row[1], 1) if row[1] else None,
        avg_condition=round(row[2], 1) if row[2] else None,
        avg_comms=round(row[3], 1) if row[3] else None,
        avg_accuracy=round(row[4], 1) if row[4] else None,
        total_ratings=row[5] or 0,
        positive_count=row[6] or 0,
        neutral_count=row[7] or 0,
        negative_count=row[8] or 0,
    )


async def _update_seller_ratings(db: AsyncSession, seller_id: str):
    """Recalculate and update seller profile rating aggregates."""
    result = await db.execute(
        select(
            func.avg(Feedback.overall_stars),
            func.avg(Feedback.shipping_stars),
            func.avg(Feedback.condition_stars),
            func.avg(Feedback.comms_stars),
            func.avg(Feedback.accuracy_stars),
            func.count(Feedback.id),
        ).where(
            and_(Feedback.seller_id == seller_id, Feedback.is_visible == True)
        )
    )
    row = result.one()

    profile = await db.execute(
        select(SellerProfile).where(SellerProfile.user_id == seller_id)
    )
    profile = profile.scalar_one_or_none()
    if profile:
        profile.avg_rating = round(row[0], 2) if row[0] else None
        profile.avg_shipping_stars = round(row[1], 2) if row[1] else None
        profile.avg_condition_stars = round(row[2], 2) if row[2] else None
        profile.avg_comms_stars = round(row[3], 2) if row[3] else None
        profile.avg_accuracy_stars = round(row[4], 2) if row[4] else None
        profile.total_ratings = row[5] or 0
