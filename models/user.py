import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)  # null for OAuth users
    display_name: Mapped[str | None] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    bio: Mapped[str | None] = mapped_column(Text)

    # Stripe Connect
    stripe_account_id: Mapped[str | None] = mapped_column(String(255))
    stripe_onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)

    # Role & Stats
    role: Mapped[str] = mapped_column(String(20), default="user")  # user, seller, admin
    rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0.00)
    total_sales: Mapped[int] = mapped_column(Integer, default=0)
    total_purchases: Mapped[int] = mapped_column(Integer, default=0)

    # OAuth
    oauth_provider: Mapped[str | None] = mapped_column(String(50))  # google, discord, twitter
    oauth_id: Mapped[str | None] = mapped_column(String(255))
    discord_id: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)
    google_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    listings = relationship("Listing", back_populates="seller", foreign_keys="Listing.seller_id")
    purchases = relationship("Order", back_populates="buyer", foreign_keys="Order.buyer_id")
    sales = relationship("Order", back_populates="seller", foreign_keys="Order.seller_id")
    watchlist_items = relationship("Watchlist", back_populates="user")
    reviews_given = relationship("Review", back_populates="reviewer", foreign_keys="Review.reviewer_id")
    reviews_received = relationship("Review", back_populates="reviewed", foreign_keys="Review.reviewed_id")
