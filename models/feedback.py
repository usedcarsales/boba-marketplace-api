"""Seller feedback/rating model — buyer reviews with anti-gaming protections."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("overall_stars >= 1 AND overall_stars <= 5", name="ck_overall_stars_range"),
        CheckConstraint("shipping_stars IS NULL OR (shipping_stars >= 1 AND shipping_stars <= 5)", name="ck_shipping_stars_range"),
        CheckConstraint("condition_stars IS NULL OR (condition_stars >= 1 AND condition_stars <= 5)", name="ck_condition_stars_range"),
        CheckConstraint("comms_stars IS NULL OR (comms_stars >= 1 AND comms_stars <= 5)", name="ck_comms_stars_range"),
        CheckConstraint("accuracy_stars IS NULL OR (accuracy_stars >= 1 AND accuracy_stars <= 5)", name="ck_accuracy_stars_range"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    order_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("orders.id"), unique=True, nullable=False)
    buyer_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    seller_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)

    # Required overall rating
    overall_stars: Mapped[int] = mapped_column(Integer, nullable=False)

    # Optional sub-ratings
    shipping_stars: Mapped[int] = mapped_column(Integer, nullable=True)
    condition_stars: Mapped[int] = mapped_column(Integer, nullable=True)
    comms_stars: Mapped[int] = mapped_column(Integer, nullable=True)
    accuracy_stars: Mapped[int] = mapped_column(Integer, nullable=True)

    # Buyer comment (500 chars max)
    comment: Mapped[str] = mapped_column(Text, nullable=True)

    # Seller response (300 chars max, 30-day window)
    seller_response: Mapped[str] = mapped_column(Text, nullable=True)
    response_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Moderation
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    moderation_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# Anti-gaming constants
FEEDBACK_COOLDOWN_HOURS = 48      # Opens 48hrs after delivery
FEEDBACK_WINDOW_DAYS = 60         # Closes 60 days post-delivery
MIN_ACCOUNT_AGE_DAYS = 7          # Accounts under 7 days can't leave feedback
VELOCITY_LIMIT = 10               # 10+ feedbacks in 24hrs triggers review hold
SELLER_RESPONSE_WINDOW_DAYS = 30  # Seller has 30 days to respond
SELLER_RESPONSE_MAX_CHARS = 300
BUYER_COMMENT_MAX_CHARS = 500
