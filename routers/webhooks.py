import stripe
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from config import get_settings
from database import get_db
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
        import json
        event = json.loads(payload)

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    if event_type == "payment_intent.succeeded":
        # Mark order as paid
        order_id = data.get("metadata", {}).get("order_id")
        if order_id:
            result = await db.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()
            if order:
                order.status = "paid"
                order.stripe_payment_intent_id = data.get("id")

    elif event_type == "payment_intent.payment_failed":
        order_id = data.get("metadata", {}).get("order_id")
        if order_id:
            result = await db.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()
            if order:
                order.status = "payment_failed"

    elif event_type == "account.updated":
        # Update seller's Stripe onboarding status
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

    return {"status": "ok"}
