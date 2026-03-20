import stripe
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from models.listing import Listing
from models.order import Order
from models.user import User
from routers.auth import get_current_user

router = APIRouter(prefix="/api/seller", tags=["seller"])
settings = get_settings()
stripe.api_key = settings.stripe_secret_key


@router.post("/onboard")
async def start_onboarding(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start Stripe Connect Express onboarding for seller."""
    if current_user.stripe_onboarding_complete:
        return {"message": "Already onboarded", "status": "complete"}

    # Create or reuse Stripe Connect account
    if not current_user.stripe_account_id:
        account = stripe.Account.create(
            type="express",
            email=current_user.email,
            metadata={"boba_user_id": str(current_user.id)},
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
        )
        current_user.stripe_account_id = account.id
        await db.flush()
    
    # Create onboarding link
    frontend_url = settings.cors_origins.split(",")[0]  # Use first CORS origin as frontend
    link = stripe.AccountLink.create(
        account=current_user.stripe_account_id,
        refresh_url=f"{frontend_url}/dashboard/sell/onboard",
        return_url=f"{frontend_url}/dashboard/sell?onboarded=true",
        type="account_onboarding",
    )

    return {"url": link.url, "status": "onboarding"}


@router.get("/onboard/status")
async def onboarding_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check Stripe Connect onboarding status."""
    if not current_user.stripe_account_id:
        return {
            "stripe_account_id": None,
            "onboarding_complete": False,
            "charges_enabled": False,
            "payouts_enabled": False,
        }

    # Check actual status from Stripe
    try:
        account = stripe.Account.retrieve(current_user.stripe_account_id)
        is_complete = account.charges_enabled and account.payouts_enabled

        # Update our DB if status changed
        if is_complete and not current_user.stripe_onboarding_complete:
            current_user.stripe_onboarding_complete = True
            current_user.role = "seller"
            await db.flush()

        return {
            "stripe_account_id": current_user.stripe_account_id,
            "onboarding_complete": is_complete,
            "charges_enabled": account.charges_enabled,
            "payouts_enabled": account.payouts_enabled,
        }
    except stripe.StripeError as e:
        return {
            "stripe_account_id": current_user.stripe_account_id,
            "onboarding_complete": current_user.stripe_onboarding_complete,
            "error": str(e),
        }


@router.get("/orders")
async def seller_orders(
    status: str | None = None,
    page: int = 1,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Seller's orders/sales list with card + buyer info for fulfillment."""
    from sqlalchemy.orm import selectinload
    from models.listing import Listing
    from models.card import Card

    query = (
        select(Order)
        .where(Order.seller_id == current_user.id)
        .options(
            selectinload(Order.listing).selectinload(Listing.card),
            selectinload(Order.buyer),
        )
    )
    if status:
        query = query.where(Order.status == status)

    query = query.order_by(Order.created_at.desc()).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    orders = result.scalars().all()

    return [
        {
            "id": str(o.id),
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            "ship_by": o.ship_by.isoformat() if o.ship_by else None,
            "shipped_at": o.shipped_at.isoformat() if o.shipped_at else None,
            "tracking_number": o.tracking_number,
            "tracking_carrier": o.tracking_carrier,
            "shipping_method": o.shipping_method,
            "requires_insurance": o.requires_insurance,
            "quantity": o.quantity,
            "subtotal_cents": o.subtotal_cents,
            "shipping_cents": o.shipping_cents,
            "total_cents": o.total_cents,
            "seller_payout_cents": o.seller_payout_cents,
            "payout_released": o.payout_released,
            "buyer_note": o.buyer_note,
            # Shipping address for packing slip
            "ship_to": {
                "name": o.ship_to_name,
                "address1": o.ship_to_address1,
                "address2": o.ship_to_address2,
                "city": o.ship_to_city,
                "state": o.ship_to_state,
                "zip": o.ship_to_zip,
                "country": o.ship_to_country,
            },
            # Card info
            "card": {
                "name": o.listing.card.name if o.listing and o.listing.card else None,
                "set_name": o.listing.card.set_name if o.listing and o.listing.card else None,
                "card_number": o.listing.card.card_number if o.listing and o.listing.card else None,
                "parallel": o.listing.card.parallel if o.listing and o.listing.card else None,
                "weapon": o.listing.card.weapon if o.listing and o.listing.card else None,
                "image_url": o.listing.card.image_url if o.listing and o.listing.card else None,
            } if o.listing else None,
            "listing_title": o.listing.title if o.listing else None,
            "listing_condition": o.listing.condition if o.listing else None,
            # Buyer info
            "buyer": {
                "username": o.buyer.username if o.buyer else None,
                "display_name": o.buyer.display_name if o.buyer else None,
            } if o.buyer else None,
        }
        for o in orders
    ]


@router.get("/orders/{order_id}/packing-slip")
async def get_packing_slip(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate packing slip data for a specific order."""
    from sqlalchemy.orm import selectinload
    from models.listing import Listing

    result = await db.execute(
        select(Order)
        .where(Order.id == order_id, Order.seller_id == current_user.id)
        .options(selectinload(Order.listing).selectinload(Listing.card), selectinload(Order.buyer))
    )
    order = result.scalar_one_or_none()
    if not order:
        return {"error": "Order not found"}

    return {
        "order_id": str(order.id),
        "order_date": order.paid_at.isoformat() if order.paid_at else order.created_at.isoformat(),
        "ship_by": order.ship_by.isoformat() if order.ship_by else None,
        "shipping_method": order.shipping_method,
        "requires_insurance": order.requires_insurance,
        "ship_to": {
            "name": order.ship_to_name,
            "address1": order.ship_to_address1,
            "address2": order.ship_to_address2,
            "city": order.ship_to_city,
            "state": order.ship_to_state,
            "zip": order.ship_to_zip,
            "country": order.ship_to_country,
        },
        "seller": {
            "username": current_user.username,
            "display_name": current_user.display_name,
        },
        "item": {
            "title": order.listing.title if order.listing else "Unknown",
            "condition": order.listing.condition if order.listing else None,
            "card_name": order.listing.card.name if order.listing and order.listing.card else None,
            "set_name": order.listing.card.set_name if order.listing and order.listing.card else None,
            "card_number": order.listing.card.card_number if order.listing and order.listing.card else None,
            "image_url": order.listing.card.image_url if order.listing and order.listing.card else None,
        },
        "quantity": order.quantity,
        "subtotal_cents": order.subtotal_cents,
        "shipping_cents": order.shipping_cents,
        "buyer_note": order.buyer_note,
    }


@router.get("/dashboard")
async def seller_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Seller dashboard stats: active listings, total sales, revenue."""
    active_count = (
        await db.execute(select(func.count()).where(Listing.seller_id == current_user.id, Listing.status == "active"))
    ).scalar() or 0

    total_sales = (
        await db.execute(
            select(func.count()).where(
                Order.seller_id == current_user.id, Order.status.in_(["paid", "shipped", "delivered"])
            )
        )
    ).scalar() or 0

    total_revenue = (
        await db.execute(
            select(func.sum(Order.seller_payout_cents)).where(
                Order.seller_id == current_user.id, Order.status.in_(["paid", "shipped", "delivered"])
            )
        )
    ).scalar() or 0

    pending_shipments = (
        await db.execute(select(func.count()).where(Order.seller_id == current_user.id, Order.status == "paid"))
    ).scalar() or 0

    return {
        "active_listings": active_count,
        "total_sales": total_sales,
        "total_revenue_cents": total_revenue,
        "pending_shipments": pending_shipments,
        "stripe_onboarded": current_user.stripe_onboarding_complete,
    }
