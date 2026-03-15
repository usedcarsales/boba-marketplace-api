import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.card import Card
from schemas.card import CardFilterOptions, CardListResponse, CardResponse

router = APIRouter(prefix="/api/cards", tags=["cards"])


@router.get("", response_model=CardListResponse)
async def list_cards(
    q: str | None = None,
    set_name: str | None = None,
    card_type: str | None = None,
    weapon: str | None = None,
    parallel: str | None = None,
    year: str | None = None,
    notation: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    sort: str = Query("name", regex="^(name|last_sale_price|power|created_at|total_sales)$"),
    order: str = Query("asc", regex="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(Card)

    # Multi-word search: each word must match at least one field
    if q:
        words = q.strip().split()
        for word in words:
            pattern = f"%{word}%"
            query = query.where(
                or_(
                    Card.name.ilike(pattern),
                    Card.parallel.ilike(pattern),
                    Card.weapon.ilike(pattern),
                    Card.set_name.ilike(pattern),
                    Card.card_number.ilike(pattern),
                    Card.card_type.ilike(pattern),
                    Card.athlete.ilike(pattern),
                    Card.treatment.ilike(pattern),
                )
            )
    if set_name:
        query = query.where(Card.set_name == set_name)
    if card_type:
        query = query.where(Card.card_type == card_type)
    if weapon:
        query = query.where(Card.weapon == weapon)
    if parallel:
        query = query.where(Card.parallel == parallel)
    if year:
        query = query.where(Card.year == year)
    if notation:
        query = query.where(Card.notation == notation)
    if min_price is not None:
        query = query.where(Card.last_sale_price >= min_price)
    if max_price is not None:
        query = query.where(Card.last_sale_price <= max_price)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Sort
    sort_column = getattr(Card, sort, Card.name)
    if order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Pagination
    query = query.offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    cards = result.scalars().all()

    return CardListResponse(
        cards=[CardResponse.model_validate(c) for c in cards],
        total=total,
        page=page,
        limit=limit,
        total_pages=math.ceil(total / limit) if total > 0 else 0,
    )


@router.get("/sets", response_model=list[str])
async def list_sets(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Card.set_name).distinct().order_by(Card.set_name))
    return result.scalars().all()


@router.get("/filters", response_model=CardFilterOptions)
async def get_filter_options(db: AsyncSession = Depends(get_db)):
    sets = (await db.execute(select(Card.set_name).distinct().order_by(Card.set_name))).scalars().all()
    weapons = (
        (await db.execute(select(Card.weapon).where(Card.weapon.isnot(None)).distinct().order_by(Card.weapon)))
        .scalars()
        .all()
    )
    parallels = (
        (await db.execute(select(Card.parallel).where(Card.parallel.isnot(None)).distinct().order_by(Card.parallel)))
        .scalars()
        .all()
    )
    card_types = (await db.execute(select(Card.card_type).distinct().order_by(Card.card_type))).scalars().all()
    years = (
        (await db.execute(select(Card.year).where(Card.year.isnot(None)).distinct().order_by(Card.year)))
        .scalars()
        .all()
    )
    notations = (
        (await db.execute(select(Card.notation).where(Card.notation.isnot(None)).distinct().order_by(Card.notation)))
        .scalars()
        .all()
    )

    return CardFilterOptions(
        sets=sets,
        weapons=weapons,
        parallels=parallels,
        card_types=card_types,
        years=years,
        notations=notations,
    )


@router.get("/autocomplete")
async def autocomplete(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    # Multi-word autocomplete: each word narrows results across all searchable fields
    base_query = select(Card.id, Card.name, Card.set_name, Card.card_number, Card.parallel, Card.weapon)
    words = q.strip().split()
    for word in words:
        pattern = f"%{word}%"
        base_query = base_query.where(
            or_(
                Card.name.ilike(pattern),
                Card.parallel.ilike(pattern),
                Card.weapon.ilike(pattern),
                Card.set_name.ilike(pattern),
                Card.card_number.ilike(pattern),
                Card.athlete.ilike(pattern),
            )
        )
    base_query = base_query.limit(limit)
    result = await db.execute(base_query)
    rows = result.all()
    return [
        {"id": str(r.id), "name": r.name, "set": r.set_name, "number": r.card_number, "parallel": r.parallel, "weapon": r.weapon}
        for r in rows
    ]


@router.get("/{card_id}", response_model=CardResponse)
async def get_card(card_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Card).where(Card.id == card_id))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    return CardResponse.model_validate(card)
