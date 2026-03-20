from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from schemas.card import CardResponse
from schemas.user import UserPublicResponse


class ListingCreate(BaseModel):
    card_id: UUID
    title: str | None = None
    description: str | None = None
    condition: str = "NM"  # NM, LP, MP, HP, DMG
    price_cents: int
    quantity: int = 1
    source: str = "manual"  # manual, discord_pipeline, bulk_import


class ListingUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    condition: str | None = None
    price_cents: int | None = None
    quantity: int | None = None
    status: str | None = None


class ListingImageResponse(BaseModel):
    id: UUID
    image_url: str
    display_order: int

    model_config = {"from_attributes": True}


class ListingResponse(BaseModel):
    id: UUID
    seller_id: UUID
    card_id: UUID
    title: str
    description: str | None
    condition: str
    price_cents: int
    quantity: int
    quantity_available: int
    is_featured: bool
    status: str
    views: int
    source: str = "manual"
    created_at: datetime
    updated_at: datetime

    seller: UserPublicResponse | None = None
    card: CardResponse | None = None
    images: list[ListingImageResponse] = []

    model_config = {"from_attributes": True}


class ListingListResponse(BaseModel):
    listings: list[ListingResponse]
    total: int
    page: int
    limit: int
    total_pages: int
