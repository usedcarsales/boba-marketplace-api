import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class SealedProduct(Base):
    __tablename__ = "sealed_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    set_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    product_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # hobby_box, booster_pack, booster_box, jumbo_pack, blaster_box, blast_box, starter_kit, trainer_kit, promo_box
    year: Mapped[int | None] = mapped_column(Integer)
    msrp_cents: Mapped[int | None] = mapped_column(Integer)  # MSRP in cents
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    cards_per_pack: Mapped[int | None] = mapped_column(Integer)
    packs_per_box: Mapped[int | None] = mapped_column(Integer)

    # Market data
    last_sale_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    avg_price_30d: Mapped[float | None] = mapped_column(Numeric(10, 2))
    total_sales: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
