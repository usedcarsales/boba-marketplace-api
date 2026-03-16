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
