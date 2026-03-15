from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class OrderCreate(BaseModel):
    listing_id: UUID
    quantity: int = 1


class OrderResponse(BaseModel):
    id: UUID
    buyer_id: UUID
    seller_id: UUID
    listing_id: UUID
    quantity: int
    subtotal_cents: int
    platform_fee_cents: int
    stripe_fee_cents: int
    seller_payout_cents: int
    stripe_payment_intent_id: str | None
    status: str
    tracking_number: str | None
    shipped_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderShipRequest(BaseModel):
    tracking_number: str


class DisputeCreate(BaseModel):
    reason: str


class DisputeResponse(BaseModel):
    id: UUID
    order_id: UUID
    opened_by: UUID
    reason: str
    status: str
    resolution: str | None
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


class ReviewCreate(BaseModel):
    rating: int  # 1-5
    comment: str | None = None


class ReviewResponse(BaseModel):
    id: UUID
    order_id: UUID
    reviewer_id: UUID
    reviewed_id: UUID
    rating: int
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
