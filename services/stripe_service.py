"""Stripe Connect integration for marketplace payments.

Handles:
- Seller onboarding (Connect Express accounts)
- Payment intent creation (buyer pays)
- Automatic fee splitting (platform 4% + Stripe fees)
- Payouts to sellers
- Refund processing
"""

# import stripe
# from config import get_settings
# settings = get_settings()
# stripe.api_key = settings.stripe_secret_key


async def create_connect_account(email: str) -> dict:
    """Create a Stripe Connect Express account for a seller."""
    # account = stripe.Account.create(
    #     type="express",
    #     email=email,
    #     capabilities={"card_payments": {"requested": True}, "transfers": {"requested": True}},
    # )
    # return {"account_id": account.id}
    return {"account_id": "placeholder", "status": "not_configured"}


async def create_onboarding_link(account_id: str, return_url: str, refresh_url: str) -> str:
    """Generate Stripe onboarding URL for seller."""
    # link = stripe.AccountLink.create(
    #     account=account_id,
    #     refresh_url=refresh_url,
    #     return_url=return_url,
    #     type="account_onboarding",
    # )
    # return link.url
    return f"{return_url}?onboarding=pending"


async def create_payment_intent(amount_cents: int, seller_account_id: str, platform_fee_cents: int) -> dict:
    """Create a PaymentIntent with automatic platform fee."""
    # intent = stripe.PaymentIntent.create(
    #     amount=amount_cents,
    #     currency="usd",
    #     application_fee_amount=platform_fee_cents,
    #     transfer_data={"destination": seller_account_id},
    # )
    # return {"client_secret": intent.client_secret, "payment_intent_id": intent.id}
    return {"client_secret": "placeholder", "payment_intent_id": "placeholder"}


async def process_refund(payment_intent_id: str, amount_cents: int | None = None) -> dict:
    """Process a refund (full or partial)."""
    # refund = stripe.Refund.create(
    #     payment_intent=payment_intent_id,
    #     amount=amount_cents,  # None = full refund
    # )
    # return {"refund_id": refund.id, "status": refund.status}
    return {"refund_id": "placeholder", "status": "not_configured"}
