"""Seller tier endpoints — profile, tier evaluation, fee lookup."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.order import Order
from models.seller_tier import (
    SellerProfile, SellerTier, TIER_CONFIG, evaluate_tier, get_fee_for_tier,
)
from models.user import User
from routers.auth import get_current_user, get_current_user_optional

router = APIRouter(prefix="/api/seller", tags=["seller-tier"])


# --- Schemas ---

class SellerProfileOut(BaseModel):
    user_id: str
    username: str | None = None
    tier: str
    tier_display: str
    tier_emoji: str
    tier_color: str
    fee_percent: float
    rolling_30d_volume_cents: int
    total_sales_count: int
    total_sales_volume_cents: int
    active_listing_count: int
    avg_rating: float | None = None
    total_ratings: int = 0
    avg_shipping_stars: float | None = None
    avg_condition_stars: float | None = None
    avg_comms_stars: float | None = None
    avg_accuracy_stars: float | None = None
    bio: str | None = None
    banner_url: str | None = None
    stripe_onboarded: bool = False
    member_since: datetime | None = None
    perks: list[str] = []
    max_listing_slots: int | None = None
    next_tier: str | None = None
    next_tier_volume_needed_cents: int | None = None


class TierConfigOut(BaseModel):
    tiers: list[dict]


# --- Endpoints ---

@router.get("/profile/me", response_model=SellerProfileOut)
async def get_my_seller_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's seller profile, creating one if needed."""
    profile = await _get_or_create_profile(db, str(user.id))
    await _evaluate_and_update_tier(db, profile)
    await db.commit()
    await db.refresh(profile)

    u = await db.get(User, user.id)
    return _profile_to_response(profile, u)


@router.get("/profile/{user_id}", response_model=SellerProfileOut)
async def get_seller_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get any seller's public profile."""
    result = await db.execute(
        select(SellerProfile).where(SellerProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Seller profile not found")

    u = await db.get(User, user_id)
    return _profile_to_response(profile, u)


@router.post("/profile/bio")
async def update_bio(
    bio: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update seller bio (Lancer+ only, 160 chars max)."""
    profile = await _get_or_create_profile(db, str(user.id))
    tier = SellerTier(profile.tier)

    # Lancer+ only
    tier_order = list(SellerTier)
    if tier_order.index(tier) < tier_order.index(SellerTier.ICE):
        raise HTTPException(403, "Custom bio requires Lancer tier or higher")

    if len(bio) > 160:
        raise HTTPException(400, "Bio must be 160 characters or less")

    profile.bio = bio
    await db.commit()
    return {"status": "ok"}


@router.get("/tiers", response_model=TierConfigOut)
async def get_tier_config():
    """Get all tier configurations (public)."""
    tiers = []
    for tier in SellerTier:
        config = TIER_CONFIG[tier]
        tiers.append({
            "id": tier.value,
            "display_name": config["display_name"],
            "emoji": config["emoji"],
            "fee_percent": config["fee_percent"],
            "min_volume_cents": config["min_volume_cents"],
            "min_rating": config["min_rating"],
            "max_listing_slots": config["max_listing_slots"],
            "color": config["color"],
            "perks": config["perks"],
        })
    return TierConfigOut(tiers=tiers)


@router.get("/fee")
async def get_my_fee(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's effective platform fee based on tier."""
    profile = await _get_or_create_profile(db, str(user.id))
    tier = SellerTier(profile.tier)
    fee = get_fee_for_tier(tier)
    config = TIER_CONFIG[tier]
    return {
        "tier": tier.value,
        "tier_display": config["display_name"],
        "fee_percent": fee,
        "per_order_fee_cents": 25,
    }


# --- Helpers ---

async def _get_or_create_profile(db: AsyncSession, user_id: str) -> SellerProfile:
    """Get or create a seller profile for a user."""
    result = await db.execute(
        select(SellerProfile).where(SellerProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        profile = SellerProfile(user_id=user_id)
        db.add(profile)
        await db.flush()
    return profile


async def _evaluate_and_update_tier(db: AsyncSession, profile: SellerProfile):
    """Recalculate 30-day volume and evaluate tier."""
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)

    # Calculate rolling 30-day volume from completed orders
    volume_result = await db.execute(
        select(func.coalesce(func.sum(Order.subtotal_cents), 0)).where(
            and_(
                Order.seller_id == profile.user_id,
                Order.status.in_(["delivered", "completed"]),
                Order.created_at >= thirty_days_ago,
            )
        )
    )
    volume_30d = volume_result.scalar() or 0

    # Total all-time sales
    totals = await db.execute(
        select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.subtotal_cents), 0),
        ).where(
            and_(
                Order.seller_id == profile.user_id,
                Order.status.in_(["delivered", "completed"]),
            )
        )
    )
    total_count, total_volume = totals.one()

    profile.rolling_30d_volume_cents = volume_30d
    profile.total_sales_count = total_count or 0
    profile.total_sales_volume_cents = total_volume or 0

    # Evaluate new tier
    new_tier = evaluate_tier(volume_30d, profile.avg_rating, profile.total_ratings)
    old_tier = SellerTier(profile.tier)

    if new_tier != old_tier:
        tier_order = list(SellerTier)
        if tier_order.index(new_tier) > tier_order.index(old_tier):
            # Upgrade — immediate
            profile.tier = new_tier.value
            profile.tier_upgraded_at = now
            profile.tier_grace_deadline = None
        else:
            # Downgrade — 7-day grace period
            if profile.tier_grace_deadline is None:
                profile.tier_grace_deadline = now + timedelta(days=7)
            elif now > profile.tier_grace_deadline:
                profile.tier = new_tier.value
                profile.tier_grace_deadline = None
    else:
        # Still qualified — clear any grace deadline
        profile.tier_grace_deadline = None


def _profile_to_response(profile: SellerProfile, user: User | None) -> SellerProfileOut:
    tier = SellerTier(profile.tier)
    config = TIER_CONFIG[tier]

    # Calculate next tier
    tier_list = list(SellerTier)
    current_idx = tier_list.index(tier)
    next_tier = None
    next_volume = None
    if current_idx < len(tier_list) - 1:
        next_t = tier_list[current_idx + 1]
        next_config = TIER_CONFIG[next_t]
        next_tier = next_config["display_name"]
        next_volume = max(0, next_config["min_volume_cents"] - profile.rolling_30d_volume_cents)

    return SellerProfileOut(
        user_id=profile.user_id,
        username=user.username if user else None,
        tier=tier.value,
        tier_display=config["display_name"],
        tier_emoji=config["emoji"],
        tier_color=config["color"],
        fee_percent=config["fee_percent"],
        rolling_30d_volume_cents=profile.rolling_30d_volume_cents,
        total_sales_count=profile.total_sales_count,
        total_sales_volume_cents=profile.total_sales_volume_cents,
        active_listing_count=profile.active_listing_count,
        avg_rating=profile.avg_rating,
        total_ratings=profile.total_ratings,
        avg_shipping_stars=profile.avg_shipping_stars,
        avg_condition_stars=profile.avg_condition_stars,
        avg_comms_stars=profile.avg_comms_stars,
        avg_accuracy_stars=profile.avg_accuracy_stars,
        bio=profile.bio,
        banner_url=profile.banner_url,
        stripe_onboarded=profile.stripe_onboarded,
        member_since=user.created_at if user else None,
        perks=config["perks"],
        max_listing_slots=config["max_listing_slots"],
        next_tier=next_tier,
        next_tier_volume_needed_cents=next_volume,
    )
