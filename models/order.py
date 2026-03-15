import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
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
    stripe_fee_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    seller_payout_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    # Stripe
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255))
    stripe_transfer_id: Mapped[str | None] = mapped_column(String(255))

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(30), default="pending"
    )  # pending, paid, shipped, delivered, disputed, refunded
    tracking_number: Mapped[str | None] = mapped_column(String(255))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
