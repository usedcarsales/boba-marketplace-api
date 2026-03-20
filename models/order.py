import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buyer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    seller_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listings.id"), nullable=False)

    quantity: Mapped[int] = mapped_column(Integer, default=1)
    subtotal_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    platform_fee_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    order_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    stripe_fee_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    shipping_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # subtotal + shipping
    seller_payout_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    # Stripe
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255))
    stripe_transfer_id: Mapped[str | None] = mapped_column(String(255))
    stripe_client_secret: Mapped[str | None] = mapped_column(String(500))

    # Status tracking
    # pending → paid → shipped → delivered → completed
    # pending → cancelled
    # paid → shipped → disputed → refunded
    # paid → ship_deadline_missed → auto_cancelled
    status: Mapped[str] = mapped_column(
        String(30), default="pending", index=True
    )

    # Shipping
    tracking_number: Mapped[str | None] = mapped_column(String(255))
    tracking_carrier: Mapped[str | None] = mapped_column(String(50))  # usps, ups, fedex
    shipping_method: Mapped[str | None] = mapped_column(String(50))  # pwe, bubble_mailer, box
    requires_insurance: Mapped[bool] = mapped_column(Boolean, default=False)

    # Buyer info for seller
    ship_to_name: Mapped[str | None] = mapped_column(String(255))
    ship_to_address1: Mapped[str | None] = mapped_column(String(255))
    ship_to_address2: Mapped[str | None] = mapped_column(String(255))
    ship_to_city: Mapped[str | None] = mapped_column(String(100))
    ship_to_state: Mapped[str | None] = mapped_column(String(50))
    ship_to_zip: Mapped[str | None] = mapped_column(String(20))
    ship_to_country: Mapped[str | None] = mapped_column(String(50), default="US")

    # Payout tracking
    payout_released: Mapped[bool] = mapped_column(Boolean, default=False)
    payout_released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ship_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 48hr deadline
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Notes
    seller_note: Mapped[str | None] = mapped_column(Text)
    buyer_note: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    buyer = relationship("User", back_populates="purchases", foreign_keys=[buyer_id])
    seller = relationship("User", back_populates="sales", foreign_keys=[seller_id])
    listing = relationship("Listing", back_populates="orders")
    review = relationship("Review", back_populates="order", uselist=False)
    dispute = relationship("Dispute", back_populates="order", uselist=False)
