from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/boba_marketplace"

    # Auth
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Stripe
    stripe_publishable_key: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "boba-marketplace"
    r2_public_url: str = ""

    # Email
    resend_api_key: str = ""
    from_email: str = "hello@bobamarket.gg"

    # App
    app_name: str = "BoBA Marketplace"
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # Platform
    platform_fee_percent: float = 6.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
