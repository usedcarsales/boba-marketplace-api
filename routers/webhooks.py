from fastapi import APIRouter, Header, HTTPException, Request

from config import get_settings

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
settings = get_settings()


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None),
):
    """Handle Stripe webhook events for payments and payouts."""
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    _payload = await request.body()

    # TODO: Verify webhook signature
    # try:
    #     event = stripe.Webhook.construct_event(
    #         payload, stripe_signature, settings.stripe_webhook_secret
    #     )
    # except ValueError:
    #     raise HTTPException(status_code=400, detail="Invalid payload")
    # except stripe.error.SignatureVerificationError:
    #     raise HTTPException(status_code=400, detail="Invalid signature")

    # TODO: Handle events
    # event_type = event["type"]
    #
    # if event_type == "payment_intent.succeeded":
    #     # Mark order as paid
    #     pass
    # elif event_type == "payment_intent.payment_failed":
    #     # Mark order as failed
    #     pass
    # elif event_type == "account.updated":
    #     # Update seller's Stripe onboarding status
    #     pass
    # elif event_type == "transfer.created":
    #     # Log payout to seller
    #     pass

    return {"status": "ok"}
