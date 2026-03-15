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


@router.post("/onboard")
async def start_onboarding(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start Stripe Connect onboarding for seller."""
    if current_user.stripe_onboarding_complete:
        return {"message": "Already onboarded", "status": "complete"}

    # TODO: Create Stripe Connect account and return onboarding URL
    # account = stripe.Account.create(type="express", email=current_user.email)
    # current_user.stripe_account_id = account.id
    # link = stripe.AccountLink.create(
    #     account=account.id,
    #     refresh_url=f"{settings.frontend_url}/dashboard/sell/onboard",
    #     return_url=f"{settings.frontend_url}/dashboard/sell",
    #     type="account_onboarding",
    # )
    # return {"url": link.url}

    return {"message": "Stripe not configured yet", "status": "pending"}


@router.get("/onboard/status")
async def onboarding_status(current_user: User = Depends(get_current_user)):
    return {
        "stripe_account_id": current_user.stripe_account_id,
        "onboarding_complete": current_user.stripe_onboarding_complete,
    }


@router.get("/dashboard")
async def seller_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Seller dashboard stats: active listings, total sales, revenue."""
    # Active listings count
    active_count = (
        await db.execute(select(func.count()).where(Listing.seller_id == current_user.id, Listing.status == "active"))
    ).scalar() or 0

    # Total sales
    total_sales = (
        await db.execute(
            select(func.count()).where(
                Order.seller_id == current_user.id, Order.status.in_(["paid", "shipped", "delivered"])
            )
        )
    ).scalar() or 0

    # Total revenue (cents)
    total_revenue = (
        await db.execute(
            select(func.sum(Order.seller_payout_cents)).where(
                Order.seller_id == current_user.id, Order.status.in_(["paid", "shipped", "delivered"])
            )
        )
    ).scalar() or 0

    # Pending shipments
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
