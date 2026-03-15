"""Email notifications via Resend.

Templates:
- Welcome email (new registration)
- Order confirmation (buyer)
- New sale notification (seller)
- Shipping confirmation (buyer)
- Price alert (watchlist)
"""

# import resend
# from config import get_settings
# settings = get_settings()
# resend.api_key = settings.resend_api_key


async def send_welcome_email(to_email: str, username: str) -> None:
    """Send welcome email to new user."""
    # resend.Emails.send({
    #     "from": settings.from_email,
    #     "to": to_email,
    #     "subject": f"Welcome to BoBA Marketplace, {username}!",
    #     "html": f"<h1>Welcome, {username}!</h1><p>Start buying and selling BoBA cards today.</p>",
    # })
    pass


async def send_order_confirmation(to_email: str, order_id: str, card_name: str, total_cents: int) -> None:
    """Send order confirmation to buyer."""
    pass


async def send_sale_notification(to_email: str, card_name: str, price_cents: int) -> None:
    """Notify seller of a new sale."""
    pass


async def send_shipping_notification(to_email: str, tracking_number: str) -> None:
    """Notify buyer that their order shipped."""
    pass


async def send_price_alert(to_email: str, card_name: str, current_price: float, alert_price: float) -> None:
    """Notify user that a watched card dropped below their alert price."""
    pass
