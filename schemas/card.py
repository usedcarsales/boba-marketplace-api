from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CardBase(BaseModel):
    card_number: str
    name: str
    card_type: str
    set_name: str
    year: str | None = None
    parallel: str | None = None
    treatment: str | None = None
    variation: str | None = None
    notation: str | None = None
    weapon: str | None = None
    power: int | None = None
    athlete: str | None = None
    play_cost: int | None = None
    play_ability: str | None = None


class CardResponse(CardBase):
    id: UUID
    radish_id: int | None
    last_sale_price: float | None
    last_sale_date: str | None
    avg_price_30d: float | None
    total_sales: int | None
    sales_last_30d: int | None
    image_url: str | None
    last_sale_image: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CardListResponse(BaseModel):
    cards: list[CardResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class CardSearchParams(BaseModel):
    q: str | None = None
    set_name: str | None = None
    card_type: str | None = None
    weapon: str | None = None
    parallel: str | None = None
    year: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    sort: str = "name"  # name, price, power, recent
    order: str = "asc"
    page: int = 1
    limit: int = 50


class CardFilterOptions(BaseModel):
    sets: list[str]
    weapons: list[str]
    parallels: list[str]
    card_types: list[str]
    years: list[str]
    notations: list[str]
