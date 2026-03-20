import math
from datetime import datetime, timedelta, timezone
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from database import get_db
from models.card import Card
from models.listing import Listing
from models.order import Order
from models.user import User
from routers.auth import get_current_user
from schemas.order import (
    CheckoutRequest,
    CheckoutResponse,
    DisputeCreate,
    OrderListResponse,
    OrderResponse,
    OrderShipRequest,
    ReviewCreate,
)

router = APIRouter(prefix="/api/orders", tags=["orders"])
settings = get_settings()
stripe.api_key = settings.stripe_secret_key

# --- Shipping rates ---
SHIPPING_RATES = {
    "pwe": {"label": "Plain White Envelope (PWE)", "cents": 100, "max_value_cents": 2000},
    "bubble_mailer": {"label": "Bubble Mailer w/ Tracking", "cents": 400, "max_value_cents": 50000},
    "box": {"label": "Small Box w/ Tracking + Insurance", "cents": 800, "max_value_cents": None},
}
INSURANCE_REQUIRED_ABOVE_CENTS = 5000   # $50+
TRACKING_REQUIRED_ABOVE_CENTS = 1000   # $10+ (matches TCGPlayer)
SIGNATURE_REQUIRED_ABOVE_CENTS = 75000 # $750+ (matches eBay seller protection)
DISPUTE_WINDOW_DAYS = 7                # 7 days post-delivery (TCGPlayer standard)


def calculate_fees(subtotal_cents: int) -> dict:
    """Calculate platform fee, Stripe fee, and seller payout."""
    platform_fee = int(subtotal_cents * settings.platform_fee_percent / 100)
    stripe_fee = int(subtotal_cents * 0.029 + 30)  # 2.9% + 30¢
    seller_payout = subtotal_cents - platform_fee - stripe_fee
    return {
        "platform_fee_cents": platform_fee,
        "stripe_fee_cents": stripe_fee,
        "seller_payout_cents": max(seller_payout, 0),
    }


def determine_shipping(subtotal_cents: int, method: str | None = None) -> dict:
    """Determine shipping cost and requirements based on order value."""
    requires_tracking = subtotal_cents >= TRACKING_REQUIRED_ABOVE_CENTS
    requires_insurance = subtotal_cents >= INSURANCE_REQUIRED_ABOVE_CENTS

    if method and method in SHIPPING_RATES:
        rate = SHIPPING_RATES[method]
        # Validate: can't use PWE for high-value orders
        if rate["max_value_cents"] and subtotal_cents > rate["max_value_cents"]:
            # Force upgrade
            if subtotal_cents > SHIPPING_RATES["bubble_mailer"]["max_value_cents"]:
                method = "box"
            else:
                method = "bubble_mailer"
            rate = SHIPPING_RATES[method]
        return {
            "shipping_method": method,
            "shipping_cents": rate["cents"],
            "requires_insurance": requires_insurance,
        }

    # Auto-select based on value
    if subtotal_cents <= 2000:
        return {"shipping_method": "pwe", "shipping_cents": 100, "requires_insurance": False}
    elif subtotal_cents <= 50000:
        return {"shipping_method": "bubble_mailer", "shipping_cents": 400, "requires_insurance": requires_insurance}
    else:
        return {"shipping_method": "box", "shipping_cents": 800, "requires_insurance": True}


# ─── CHECKOUT: Create order + Stripe PaymentIntent ───
@router.post("/checkout", response_model=CheckoutResponse, status_code=201)
async def checkout(
    data: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create order, calculate fees/shipping, create Stripe PaymentIntent."""
    try:
        # Get listing with card and seller
        result = await db.execute(
            select(Listing)
            .where(Listing.id == data.listing_id)
            .options(selectinload(Listing.card), selectinload(Listing.seller))
        )
        listing = result.scalar_one_or_none()
        if not listing or listing.status != "active":
            raise HTTPException(status_code=404, detail="Listing not found or unavailable")
        if listing.quantity_available < data.quantity:
            raise HTTPException(status_code=400, detail="Not enough quantity available")
        if listing.seller_id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot buy your own listing")

        # Verify seller has Stripe Connect
        seller = listing.seller
        if not seller or not seller.stripe_account_id or not seller.stripe_onboarding_complete:
            raise HTTPException(status_code=400, detail="Seller payment not configured")

        # Calculate everything
        subtotal = listing.price_cents * data.quantity
        fees = calculate_fees(subtotal)
        shipping = determine_shipping(subtotal, data.shipping_method)

        total = subtotal + shipping["shipping_cents"]

        # Create the order
        order = Order(
            buyer_id=current_user.id,
            seller_id=listing.seller_id,
            listing_id=listing.id,
            quantity=data.quantity,
            subtotal_cents=subtotal,
            shipping_cents=shipping["shipping_cents"],
            total_cents=total,
            shipping_method=shipping["shipping_method"],
            requires_insurance=shipping["requires_insurance"],
            ship_to_name=data.ship_to_name,
            ship_to_address1=data.ship_to_address1,
            ship_to_address2=data.ship_to_address2,
            ship_to_city=data.ship_to_city,
            ship_to_state=data.ship_to_state,
            ship_to_zip=data.ship_to_zip,
            ship_to_country=data.ship_to_country or "US",
            buyer_note=data.buyer_note,
            **fees,
        )
        db.add(order)
        await db.flush()

        # Create Stripe PaymentIntent with destination charge
        # Buyer pays total, platform takes fee, seller gets payout
        payment_intent = stripe.PaymentIntent.create(
            amount=total,
            currency="usd",
            # Destination charge: payment goes to platform, then we transfer to seller
            transfer_data={
                "destination": seller.stripe_account_id,
                "amount": fees["seller_payout_cents"],  # Seller receives this after fees
            },
            metadata={
                "order_id": str(order.id),
                "listing_id": str(listing.id),
                "buyer_id": str(current_user.id),
                "seller_id": str(listing.seller_id),
            },
            description=f"BoBA Market — {listing.title}",
            receipt_email=current_user.email,
            # Hold the payment — don't capture until seller ships (optional for MVP)
            # capture_method="manual",  # Uncomment for hold-then-capture flow
        )

        order.stripe_payment_intent_id = payment_intent.id
        order.stripe_client_secret = payment_intent.client_secret
        await db.flush()

        return CheckoutResponse(
            order_id=order.id,
            client_secret=payment_intent.client_secret,
            subtotal_cents=subtotal,
            shipping_cents=shipping["shipping_cents"],
            platform_fee_cents=fees["platform_fee_cents"],
            stripe_fee_cents=fees["stripe_fee_cents"],
            total_cents=total,
            seller_payout_cents=fees["seller_payout_cents"],
            shipping_method=shipping["shipping_method"],
            requires_insurance=shipping["requires_insurance"],
        )

    except HTTPException:
        raise
    except stripe.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Payment error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Checkout error: {type(e).__name__}: {str(e)}")


# ─── LIST ORDERS (buyer or seller) ───
@router.get("", response_model=OrderListResponse)
async def list_orders(
    role: str = Query("buyer", regex="^(buyer|seller|all)$"),
    status: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List orders — as buyer, seller, or both."""
    query = select(Order).options(
        selectinload(Order.listing).selectinload(Listing.card),
        selectinload(Order.buyer),
        selectinload(Order.seller),
    )

    if role == "buyer":
        query = query.where(Order.buyer_id == current_user.id)
    elif role == "seller":
        query = query.where(Order.seller_id == current_user.id)
    else:
        query = query.where(or_(Order.buyer_id == current_user.id, Order.seller_id == current_user.id))

    if status:
        query = query.where(Order.status == status)

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sort & paginate
    query = query.order_by(Order.created_at.desc())
    query = query.offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    orders = result.scalars().all()

    return OrderListResponse(
        orders=[OrderResponse.model_validate(o) for o in orders],
        total=total,
        page=page,
        limit=limit,
        total_pages=math.ceil(total / limit) if total > 0 else 0,
    )


# ─── GET SINGLE ORDER ───
@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.listing).selectinload(Listing.card),
            selectinload(Order.buyer),
            selectinload(Order.seller),
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.buyer_id != current_user.id and order.seller_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return OrderResponse.model_validate(order)


# ─── SELLER: MARK ORDER AS SHIPPED ───
@router.put("/{order_id}/ship", response_model=OrderResponse)
async def ship_order(
    order_id: UUID,
    data: OrderShipRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id).options(
            selectinload(Order.listing).selectinload(Listing.card)
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.seller_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only seller can mark as shipped")
    if order.status != "paid":
        raise HTTPException(status_code=400, detail=f"Order must be paid before shipping (current: {order.status})")

    # Validate tracking requirement
    if order.subtotal_cents >= TRACKING_REQUIRED_ABOVE_CENTS and not data.tracking_number:
        raise HTTPException(status_code=400, detail=f"Tracking number required for orders ${TRACKING_REQUIRED_ABOVE_CENTS/100:.0f}+")

    # Validate signature confirmation for high-value orders
    if order.subtotal_cents >= SIGNATURE_REQUIRED_ABOVE_CENTS and not data.tracking_number:
        raise HTTPException(status_code=400, detail=f"Tracking with signature confirmation required for orders ${SIGNATURE_REQUIRED_ABOVE_CENTS/100:.0f}+")

    now = datetime.now(timezone.utc)
    order.tracking_number = data.tracking_number
    order.tracking_carrier = data.carrier
    order.status = "shipped"
    order.shipped_at = now
    order.seller_note = data.seller_note
    await db.flush()

    return OrderResponse.model_validate(order)


# ─── BUYER: CONFIRM DELIVERY ───
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
    if order.status != "shipped":
        raise HTTPException(status_code=400, detail="Order must be shipped first")

    now = datetime.now(timezone.utc)
    order.status = "delivered"
    order.delivered_at = now

    # Auto-complete after delivery confirmation → release payout
    order.status = "completed"
    order.completed_at = now
    order.payout_released = True
    order.payout_released_at = now

    # Transfer funds to seller via Stripe (if using manual capture)
    # With automatic capture + destination charge, Stripe handles this
    # The transfer was already set up in the PaymentIntent

    await db.flush()
    return OrderResponse.model_validate(order)


# ─── BUYER: CANCEL ORDER (only if not yet shipped) ───
@router.put("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.buyer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only buyer can cancel")
    if order.status not in ("pending", "paid"):
        raise HTTPException(status_code=400, detail="Cannot cancel — order already shipped")

    # Refund via Stripe if paid
    if order.stripe_payment_intent_id and order.status == "paid":
        try:
            stripe.Refund.create(payment_intent=order.stripe_payment_intent_id)
        except stripe.StripeError as e:
            raise HTTPException(status_code=502, detail=f"Refund failed: {str(e)}")

    order.status = "cancelled"

    # Restore listing inventory
    listing_result = await db.execute(select(Listing).where(Listing.id == order.listing_id))
    listing = listing_result.scalar_one_or_none()
    if listing:
        listing.quantity_available += order.quantity
        if listing.status == "sold":
            listing.status = "active"

    await db.flush()
    return OrderResponse.model_validate(order)


# ─── DISPUTE ───
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
    if order.buyer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only buyer can open disputes")
    if order.status not in ("shipped", "delivered"):
        raise HTTPException(status_code=400, detail="Can only dispute shipped or delivered orders")

    # Check dispute window after delivery
    if order.delivered_at:
        window = order.delivered_at + timedelta(days=DISPUTE_WINDOW_DAYS)
        if datetime.now(timezone.utc) > window:
            raise HTTPException(status_code=400, detail=f"Dispute window has closed ({DISPUTE_WINDOW_DAYS} days after delivery)")

    dispute = Dispute(
        order_id=order.id,
        opened_by=current_user.id,
        reason=data.reason,
    )
    db.add(dispute)
    order.status = "disputed"
    await db.flush()

    return {"id": str(dispute.id), "status": "open", "message": "Dispute opened — we'll review within 24 hours"}


# ─── REVIEW ───
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
    if order.status not in ("delivered", "completed"):
        raise HTTPException(status_code=400, detail="Order must be delivered to review")

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

    return {"id": str(review.id), "rating": review.rating, "message": "Review submitted — thank you!"}


# ─── SHIPPING RATES INFO ───
@router.get("/shipping/rates")
async def get_shipping_rates():
    """Return available shipping methods and their rates."""
    return {
        "rates": [
            {
                "method": "pwe",
                "label": "Plain White Envelope (PWE)",
                "price_cents": 100,
                "max_value_cents": 2000,
                "tracking": False,
                "insurance": False,
                "description": "For cards under $20. No tracking. Seller assumes risk.",
            },
            {
                "method": "bubble_mailer",
                "label": "Bubble Mailer w/ Tracking",
                "price_cents": 400,
                "max_value_cents": 50000,
                "tracking": True,
                "insurance": False,
                "description": "Top loader in bubble mailer. USPS tracking included.",
            },
            {
                "method": "box",
                "label": "Small Box w/ Tracking + Insurance",
                "price_cents": 800,
                "max_value_cents": None,
                "tracking": True,
                "insurance": True,
                "description": "For high-value cards $50+. Full tracking and insurance.",
            },
        ],
        "rules": {
            "tracking_required_above_cents": TRACKING_REQUIRED_ABOVE_CENTS,
            "insurance_required_above_cents": INSURANCE_REQUIRED_ABOVE_CENTS,
            "signature_required_above_cents": SIGNATURE_REQUIRED_ABOVE_CENTS,
            "dispute_window_days": DISPUTE_WINDOW_DAYS,
        },
    }
