from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


# ─── Checkout / Create Order ───
class CheckoutRequest(BaseModel):
    listing_id: UUID
    quantity: int = 1
    shipping_method: str | None = None  # pwe, bubble_mailer, box (auto if None)
    ship_to_name: str
    ship_to_address1: str
    ship_to_address2: str | None = None
    ship_to_city: str
    ship_to_state: str
    ship_to_zip: str
    ship_to_country: str = "US"
    buyer_note: str | None = None


class CheckoutResponse(BaseModel):
    order_id: UUID
    client_secret: str  # Stripe PaymentIntent client_secret for frontend
    subtotal_cents: int
    shipping_cents: int
    platform_fee_cents: int
    order_fee_cents: int
    stripe_fee_cents: int
    total_cents: int
    seller_payout_cents: int
    shipping_method: str
    requires_insurance: bool
    requires_signature: bool = False
    tracking_required: bool = False


# ─── Order Response ───
class OrderListingInfo(BaseModel):
    id: UUID
    title: str
    condition: str
    price_cents: int
    card: "OrderCardInfo | None" = None

    model_config = {"from_attributes": True}


class OrderCardInfo(BaseModel):
    id: UUID
    name: str
    set_name: str | None = None
    card_number: str | None = None
    parallel: str | None = None
    weapon: str | None = None
    image_url: str | None = None

    model_config = {"from_attributes": True}


class OrderUserInfo(BaseModel):
    id: UUID
    username: str
    display_name: str | None = None

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: UUID
    buyer_id: UUID
    seller_id: UUID
    listing_id: UUID
    quantity: int
    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    platform_fee_cents: int
    stripe_fee_cents: int
    seller_payout_cents: int
    stripe_payment_intent_id: str | None
    status: str
    tracking_number: str | None
    tracking_carrier: str | None
    shipping_method: str | None
    requires_insurance: bool
    ship_to_name: str | None
    ship_to_city: str | None
    ship_to_state: str | None
    ship_to_zip: str | None
    payout_released: bool
    paid_at: datetime | None
    shipped_at: datetime | None
    ship_by: datetime | None
    delivered_at: datetime | None
    completed_at: datetime | None
    seller_note: str | None
    buyer_note: str | None
    created_at: datetime

    listing: OrderListingInfo | None = None
    buyer: OrderUserInfo | None = None
    seller: OrderUserInfo | None = None

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    limit: int
    total_pages: int


# ─── Shipping ───
class OrderShipRequest(BaseModel):
    tracking_number: str | None = None  # Optional for PWE orders
    carrier: str | None = "usps"  # usps, ups, fedex
    seller_note: str | None = None


# ─── Dispute ───
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


# ─── Review ───
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
