"""Seller tier model — BoBA weapon-themed 6-tier progression system."""

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class SellerTier(str, enum.Enum):
    STEEL = "steel"
    FIRE = "fire"
    ICE = "ice"
    GLOW = "glow"
    HEX = "hex"
    SUPER = "super"


# Tier configuration — thresholds, fees, perks
TIER_CONFIG = {
    SellerTier.STEEL: {
        "display_name": "Steel",
        "emoji": "🔩",
        "fee_percent": 8.0,
        "min_volume_cents": 0,
        "max_volume_cents": 9999,       # $0–$99.99
        "min_rating": None,
        "min_ratings_count": 0,
        "max_listing_slots": 10,
        "color": "#71717A",             # zinc-500
        "bulk_listing": False,
        "perks": ["10 listing slots", "Basic profile"],
    },
    SellerTier.FIRE: {
        "display_name": "Fire",
        "emoji": "🔥",
        "fee_percent": 8.0,
        "min_volume_cents": 10000,      # $100
        "max_volume_cents": 49999,      # $499.99
        "min_rating": 4.0,
        "min_ratings_count": 10,
        "max_listing_slots": 25,
        "color": "#EF4444",             # red-500
        "bulk_listing": True,
        "perks": ["25 listing slots", "Verified badge", "Bulk listing tool"],
    },
    SellerTier.ICE: {
        "display_name": "Ice",
        "emoji": "🧊",
        "fee_percent": 8.0,
        "min_volume_cents": 50000,      # $500
        "max_volume_cents": 199999,     # $1,999.99
        "min_rating": 4.2,
        "min_ratings_count": 10,
        "max_listing_slots": 75,
        "color": "#38BDF8",             # sky-400
        "bulk_listing": True,
        "perks": ["75 listing slots", "Bulk listing tool", "Priority search", "Custom bio"],
    },
    SellerTier.GLOW: {
        "display_name": "Glow",
        "emoji": "✨",
        "fee_percent": 7.0,
        "min_volume_cents": 200000,     # $2,000
        "max_volume_cents": 499999,     # $4,999.99
        "min_rating": 4.5,
        "min_ratings_count": 10,
        "max_listing_slots": 150,
        "color": "#79F528",             # boba glow green
        "bulk_listing": True,
        "perks": ["150 listing slots", "7% fee (reduced!)", "Flash Sale access", "Glow badge on listings"],
    },
    SellerTier.HEX: {
        "display_name": "Hex",
        "emoji": "🔮",
        "fee_percent": 6.0,
        "min_volume_cents": 500000,     # $5,000
        "max_volume_cents": 999999,     # $9,999.99
        "min_rating": 4.5,
        "min_ratings_count": 10,
        "max_listing_slots": 300,
        "color": "#A855F7",             # purple-500
        "bulk_listing": True,
        "perks": ["300 listing slots", "6% fee", "Custom storefront + banner", "Early feature access"],
    },
    SellerTier.SUPER: {
        "display_name": "Super",
        "emoji": "⚡",
        "fee_percent": 5.0,
        "min_volume_cents": 1000000,    # $10,000
        "max_volume_cents": None,
        "min_rating": 4.7,
        "min_ratings_count": 10,
        "max_listing_slots": None,      # Unlimited
        "color": "#FBBF24",             # amber-400 / gold
        "bulk_listing": True,
        "perks": ["Unlimited listing slots", "5% fee", "Homepage spotlight", "Newsletter/socials feature", "Priority support", "BoBA Official Partner eligible"],
    },
}


class SellerProfile(Base):
    __tablename__ = "seller_profiles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), unique=True, nullable=False)

    # Current tier
    tier: Mapped[str] = mapped_column(String(20), default=SellerTier.STEEL.value, nullable=False)

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
    bio: Mapped[str] = mapped_column(Text, nullable=True)       # 160 chars, Ice+
    banner_url: Mapped[str] = mapped_column(String(500), nullable=True)  # Hex+

    # Stripe Connect
    stripe_account_id: Mapped[str] = mapped_column(String(255), nullable=True)
    stripe_onboarded: Mapped[bool] = mapped_column(Boolean, default=False)

    # Tier tracking
    tier_upgraded_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    tier_grace_deadline: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def evaluate_tier(volume_cents: int, avg_rating: float | None, ratings_count: int) -> SellerTier:
    """Evaluate what tier a seller qualifies for based on 30-day volume and rating."""
    for tier in reversed(list(SellerTier)):
        config = TIER_CONFIG[tier]
        if volume_cents < config["min_volume_cents"]:
            continue
        if config["min_rating"] is not None:
            if ratings_count < config["min_ratings_count"]:
                continue
            if avg_rating is None or avg_rating < config["min_rating"]:
                continue
        return tier
    return SellerTier.STEEL


def get_fee_for_tier(tier: SellerTier) -> float:
    """Get the platform fee percentage for a given tier."""
    return TIER_CONFIG[tier]["fee_percent"]


def has_bulk_listing(tier: SellerTier) -> bool:
    """Check if a tier has access to the bulk listing tool."""
    return TIER_CONFIG[tier]["bulk_listing"]
