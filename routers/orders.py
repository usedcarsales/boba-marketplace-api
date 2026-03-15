from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from models.listing import Listing
from models.order import Order
from models.user import User
from routers.auth import get_current_user
from schemas.order import DisputeCreate, OrderCreate, OrderResponse, OrderShipRequest, ReviewCreate

router = APIRouter(prefix="/api/orders", tags=["orders"])
settings = get_settings()


def calculate_fees(subtotal_cents: int) -> dict:
    """Calculate platform fee, Stripe fee, and seller payout."""
    platform_fee = int(subtotal_cents * settings.platform_fee_percent / 100)
    stripe_fee = int(subtotal_cents * 0.029 + 30)  # 2.9% + 30¢
    seller_payout = subtotal_cents - platform_fee - stripe_fee
    return {
        "platform_fee_cents": platform_fee,
        "stripe_fee_cents": stripe_fee,
        "seller_payout_cents": seller_payout,
    }


@router.post("", response_model=OrderResponse, status_code=201)
async def create_order(
    data: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get listing
    result = await db.execute(select(Listing).where(Listing.id == data.listing_id))
    listing = result.scalar_one_or_none()
    if not listing or listing.status != "active":
        raise HTTPException(status_code=404, detail="Listing not found or unavailable")
    if listing.quantity_available < data.quantity:
        raise HTTPException(status_code=400, detail="Insufficient quantity available")
    if listing.seller_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot buy your own listing")

    subtotal = listing.price_cents * data.quantity
    fees = calculate_fees(subtotal)

    order = Order(
        buyer_id=current_user.id,
        seller_id=listing.seller_id,
        listing_id=listing.id,
        quantity=data.quantity,
        subtotal_cents=subtotal,
        **fees,
    )
    db.add(order)

    # Update listing quantity
    listing.quantity_available -= data.quantity
    if listing.quantity_available <= 0:
        listing.status = "sold"

    await db.flush()

    # TODO: Create Stripe PaymentIntent here
    # stripe_service.create_payment_intent(order)

    return OrderResponse.model_validate(order)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.buyer_id != current_user.id and order.seller_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return OrderResponse.model_validate(order)


@router.put("/{order_id}/ship", response_model=OrderResponse)
async def ship_order(
    order_id: UUID,
    data: OrderShipRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.seller_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only seller can mark as shipped")
    if order.status != "paid":
        raise HTTPException(status_code=400, detail="Order must be paid before shipping")

    from datetime import datetime, timezone

    order.tracking_number = data.tracking_number
    order.status = "shipped"
    order.shipped_at = datetime.now(timezone.utc)
    await db.flush()
    return OrderResponse.model_validate(order)


@router.put("/{order_id}/deliver", response_model=OrderResponse)
async def confirm_delivery(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.buyer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only buyer can confirm delivery")

    from datetime import datetime, timezone

    order.status = "delivered"
    order.delivered_at = datetime.now(timezone.utc)
    await db.flush()

    # TODO: Trigger Stripe payout to seller
    return OrderResponse.model_validate(order)


@router.post("/{order_id}/dispute")
async def open_dispute(
    order_id: UUID,
    data: DisputeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.dispute import Dispute

    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.buyer_id != current_user.id and order.seller_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    dispute = Dispute(
        order_id=order.id,
        opened_by=current_user.id,
        reason=data.reason,
    )
    db.add(dispute)
    order.status = "disputed"
    await db.flush()

    return {"id": str(dispute.id), "status": "open", "message": "Dispute opened successfully"}


@router.post("/{order_id}/review")
async def leave_review(
    order_id: UUID,
    data: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.review import Review

    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.buyer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only buyer can leave a review")
    if order.status not in ("delivered", "shipped"):
        raise HTTPException(status_code=400, detail="Order must be delivered to review")

    # Check for existing review
    existing = await db.execute(select(Review).where(Review.order_id == order_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Review already exists for this order")

    review = Review(
        order_id=order.id,
        reviewer_id=current_user.id,
        reviewed_id=order.seller_id,
        rating=data.rating,
        comment=data.comment,
    )
    db.add(review)
    await db.flush()

    return {"id": str(review.id), "rating": review.rating, "message": "Review submitted"}
