import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifiers
    card_number: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # e.g. "PL-13", "GLBF-151"
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # e.g. "Play Booster", "Showtime"
    radish_id: Mapped[int | None] = mapped_column(Integer, unique=True)  # ID from Radish API

    # Classification
    card_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # Hero, Play, Bonus Play, Hot Dog
    set_name: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # Alpha Edition, Griffey Edition, etc.
    year: Mapped[str | None] = mapped_column(String(4), index=True)  # 2024, 2025, 2026

    # Treatment / Parallel
    parallel: Mapped[str | None] = mapped_column(String(100), index=True)  # Paper, Play, Battlefoil, etc.
    treatment: Mapped[str | None] = mapped_column(String(100))  # Headlines Battlefoil, Grandma's Linoleum, etc.
    variation: Mapped[str | None] = mapped_column(String(100))  # First Edition, Founding Hero, Debut, etc.
    notation: Mapped[str | None] = mapped_column(String(50))  # SSP, SP, Secret SSP (rarity)

    # Hero-specific
    weapon: Mapped[str | None] = mapped_column(String(50), index=True)  # Fire, Ice, Steel, Glow, Hex, Gum, Super, etc.
    power: Mapped[int | None] = mapped_column(Integer)  # Hero power rating (55-250)
    athlete: Mapped[str | None] = mapped_column(String(100))  # Real athlete name

    # Play-specific
    play_cost: Mapped[int | None] = mapped_column(Integer)  # Hot Dog cost
    play_ability: Mapped[str | None] = mapped_column(Text)  # Full ability text

    # Pricing (from Radish)
    last_sale_price: Mapped[float | None] = mapped_column()
    last_sale_date: Mapped[str | None] = mapped_column(String(30))
    avg_price_30d: Mapped[float | None] = mapped_column()
    total_sales: Mapped[int | None] = mapped_column(Integer, default=0)
    sales_last_30d: Mapped[int | None] = mapped_column(Integer, default=0)

    # Images
    image_url: Mapped[str | None] = mapped_column(Text)  # Official card image
    last_sale_image: Mapped[str | None] = mapped_column(Text)  # eBay listing photo

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    listings = relationship("Listing", back_populates="card")
    price_history = relationship("PriceHistory", back_populates="card")
    watchlist_entries = relationship("Watchlist", back_populates="card")
