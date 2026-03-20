"""Seller tier model — weapon-themed progression system."""

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class SellerTier(str, enum.Enum):
    RECRUIT = "recruit"
    BLADESMAN = "bladesman"
    LANCER = "lancer"
    WARLORD = "warlord"
    ARENA_LEGEND = "arena_legend"


# Tier configuration — thresholds, fees, perks
TIER_CONFIG = {
    SellerTier.RECRUIT: {
        "display_name": "Recruit",
        "emoji": "⚔️",
        "fee_percent": 8.0,
        "min_volume_cents": 0,
        "max_volume_cents": 9999,  # $0-$99.99
        "min_rating": None,
        "min_ratings_count": 0,
        "max_listing_slots": 10,
        "color": "#9CA3AF",  # Gray
        "perks": ["Standard listing slots", "Basic profile"],
    },
    SellerTier.BLADESMAN: {
        "display_name": "Bladesman",
        "emoji": "🗡️",
        "fee_percent": 7.0,
        "min_volume_cents": 10000,  # $100
        "max_volume_cents": 49999,  # $499.99
        "min_rating": 4.0,
        "min_ratings_count": 10,
        "max_listing_slots": 25,
        "color": "#22C55E",  # Green
        "perks": ["Verified checkmark", "Above Recruits in search", "Reduced fee"],
    },
    SellerTier.LANCER: {
        "display_name": "Lancer",
        "emoji": "🪃",
        "fee_percent": 6.0,
        "min_volume_cents": 50000,  # $500
        "max_volume_cents": 199999,  # $1,999.99
        "min_rating": 4.2,
        "min_ratings_count": 10,
        "max_listing_slots": 75,
        "color": "#3B82F6",  # Blue
        "perks": ["Priority search", "Flash Sale access", "Lancer badge", "Custom bio"],
    },
    SellerTier.WARLORD: {
        "display_name": "Warlord",
        "emoji": "🪓",
        "fee_percent": 5.0,
        "min_volume_cents": 200000,  # $2,000
        "max_volume_cents": 999999,  # $9,999.99
        "min_rating": 4.5,
        "min_ratings_count": 10,
        "max_listing_slots": 200,
        "color": "#A855F7",  # Purple
        "perks": ["Top search placement", "Warlord Pick weekly feature", "Custom storefront + banner", "Early feature access"],
    },
    SellerTier.ARENA_LEGEND: {
        "display_name": "Arena Legend",
        "emoji": "🏆",
        "fee_percent": 4.0,
        "min_volume_cents": 1000000,  # $10,000
        "max_volume_cents": None,
        "min_rating": 4.7,
        "min_ratings_count": 10,
        "max_listing_slots": None,  # Unlimited
        "color": "#FBBF24",  # Gold
        "perks": ["Pinned top of categories", "Homepage spotlight", "Newsletter/socials feature", "Priority support", "Animated fire badge", "BoBA Official Partner eligible"],
    },
}


class SellerProfile(Base):
    __tablename__ = "seller_profiles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), unique=True, nullable=False)
    
    # Current tier
    tier: Mapped[str] = mapped_column(String(20), default=SellerTier.RECRUIT.value, nullable=False)
    
    # Computed stats (updated on each sale / tier evaluation)
    rolling_30d_volume_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_sales_count: Mapped[int] = mapped_column(Integer, default=0)
    total_sales_volume_cents: Mapped[int] = mapped_column(Integer, default=0)
    active_listing_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Rating aggregates
    avg_rating: Mapped[float] = mapped_column(Float, nullable=True)
    total_ratings: Mapped[int] = mapped_column(Integer, default=0)
    avg_shipping_stars: Mapped[float] = mapped_column(Float, nullable=True)
    avg_condition_stars: Mapped[float] = mapped_column(Float, nullable=True)
    avg_comms_stars: Mapped[float] = mapped_column(Float, nullable=True)
    avg_accuracy_stars: Mapped[float] = mapped_column(Float, nullable=True)
    
    # Profile customization
    bio: Mapped[str] = mapped_column(Text, nullable=True)  # 160 chars, Lancer+
    banner_url: Mapped[str] = mapped_column(String(500), nullable=True)  # Warlord+
    
    # Stripe Connect
    stripe_account_id: Mapped[str] = mapped_column(String(255), nullable=True)
    stripe_onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Tier tracking
    tier_upgraded_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    tier_grace_deadline: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # 7-day grace before downgrade
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def evaluate_tier(volume_cents: int, avg_rating: float | None, ratings_count: int) -> SellerTier:
    """Evaluate what tier a seller qualifies for based on 30-day volume and rating."""
    # Work from highest to lowest
    for tier in reversed(list(SellerTier)):
        config = TIER_CONFIG[tier]
        # Check volume threshold
        if volume_cents < config["min_volume_cents"]:
            continue
        # Check rating requirement (skip if not enough ratings yet — grace period)
        if config["min_rating"] is not None:
            if ratings_count < config["min_ratings_count"]:
                continue
            if avg_rating is None or avg_rating < config["min_rating"]:
                continue
        return tier
    return SellerTier.RECRUIT


def get_fee_for_tier(tier: SellerTier) -> float:
    """Get the platform fee percentage for a given tier."""
    return TIER_CONFIG[tier]["fee_percent"]
