import json
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from models.listing import Listing
from models.order import Order
from models.user import User

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
settings = get_settings()
stripe.api_key = settings.stripe_secret_key


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe webhook events for payments and Connect onboarding."""
    payload = await request.body()

    # Verify webhook signature if secret is configured
    if settings.stripe_webhook_secret and settings.stripe_webhook_secret != "whsec_placeholder":
        try:
            event = stripe.Webhook.construct_event(
                payload, stripe_signature, settings.stripe_webhook_secret
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        event = json.loads(payload)

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    # ─── Payment succeeded → mark order as PAID, set ship_by deadline ───
    if event_type == "payment_intent.succeeded":
        order_id = data.get("metadata", {}).get("order_id")
        if order_id:
            result = await db.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()
            if order and order.status == "pending":
                now = datetime.now(timezone.utc)
                order.status = "paid"
                order.paid_at = now
                order.ship_by = now + timedelta(hours=48)  # 48hr shipping deadline
                order.stripe_payment_intent_id = data.get("id")

                # Deduct listing inventory (in case it wasn't done at checkout)
                listing_result = await db.execute(select(Listing).where(Listing.id == order.listing_id))
                listing = listing_result.scalar_one_or_none()
                if listing:
                    listing.quantity_available = max(0, listing.quantity_available - order.quantity)
                    if listing.quantity_available <= 0:
                        listing.status = "sold"

    # ─── Payment failed ───
    elif event_type == "payment_intent.payment_failed":
        order_id = data.get("metadata", {}).get("order_id")
        if order_id:
            result = await db.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()
            if order:
                order.status = "payment_failed"
                # Restore listing inventory
                listing_result = await db.execute(select(Listing).where(Listing.id == order.listing_id))
                listing = listing_result.scalar_one_or_none()
                if listing:
                    listing.quantity_available += order.quantity
                    if listing.status == "sold":
                        listing.status = "active"

    # ─── Stripe Connect account updated → check seller onboarding ───
    elif event_type == "account.updated":
        account_id = data.get("id")
        if account_id:
            result = await db.execute(select(User).where(User.stripe_account_id == account_id))
            user = result.scalar_one_or_none()
            if user:
                charges_enabled = data.get("charges_enabled", False)
                payouts_enabled = data.get("payouts_enabled", False)
                if charges_enabled and payouts_enabled:
                    user.stripe_onboarding_complete = True
                    user.role = "seller"

    # ─── Charge refunded ───
    elif event_type == "charge.refunded":
        payment_intent_id = data.get("payment_intent")
        if payment_intent_id:
            result = await db.execute(
                select(Order).where(Order.stripe_payment_intent_id == payment_intent_id)
            )
            order = result.scalar_one_or_none()
            if order:
                order.status = "refunded"

    # ─── Transfer completed (seller payout) ───
    elif event_type == "transfer.created":
        transfer_id = data.get("id")
        order_id = data.get("metadata", {}).get("order_id")
        if order_id and transfer_id:
            result = await db.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()
            if order:
                order.stripe_transfer_id = transfer_id

    return {"status": "ok"}
