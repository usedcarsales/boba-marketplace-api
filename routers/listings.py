import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models.listing import Listing
from models.user import User
from routers.auth import get_current_user
from schemas.listing import ListingCreate, ListingListResponse, ListingResponse, ListingUpdate

router = APIRouter(prefix="/api/listings", tags=["listings"])


@router.get("", response_model=ListingListResponse)
async def list_listings(
    card_id: UUID | None = None,
    set_name: str | None = None,
    condition: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    seller_id: UUID | None = None,
    sort: str = Query("created_at", regex="^(created_at|price_cents|views)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Listing)
        .where(Listing.status == "active")
        .options(
            selectinload(Listing.seller),
            selectinload(Listing.card),
            selectinload(Listing.images),
        )
    )

    if card_id:
        query = query.where(Listing.card_id == card_id)
    if condition:
        query = query.where(Listing.condition == condition)
    if min_price is not None:
        query = query.where(Listing.price_cents >= min_price)
    if max_price is not None:
        query = query.where(Listing.price_cents <= max_price)
    if seller_id:
        query = query.where(Listing.seller_id == seller_id)

    # Join card for set filter
    if set_name:
        from models.card import Card

        query = query.join(Listing.card).where(Card.set_name == set_name)

    # Count
    count_q = select(func.count()).select_from(select(Listing.id).where(Listing.status == "active").subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sort & paginate
    sort_col = getattr(Listing, sort, Listing.created_at)
    query = query.order_by(sort_col.desc() if order == "desc" else sort_col.asc())
    query = query.offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    listings = result.scalars().all()

    return ListingListResponse(
        listings=[ListingResponse.model_validate(item) for item in listings],
        total=total,
        page=page,
        limit=limit,
        total_pages=math.ceil(total / limit) if total > 0 else 0,
    )


@router.get("/featured", response_model=list[ListingResponse])
async def featured_listings(db: AsyncSession = Depends(get_db)):
    query = (
        select(Listing)
        .where(Listing.status == "active", Listing.is_featured.is_(True))
        .options(selectinload(Listing.seller), selectinload(Listing.card), selectinload(Listing.images))
        .limit(12)
    )
    result = await db.execute(query)
    return [ListingResponse.model_validate(item) for item in result.scalars().all()]


@router.get("/recent", response_model=list[ListingResponse])
async def recent_listings(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Listing)
        .where(Listing.status == "active")
        .options(selectinload(Listing.seller), selectinload(Listing.card), selectinload(Listing.images))
        .order_by(Listing.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    return [ListingResponse.model_validate(item) for item in result.scalars().all()]


@router.get("/{listing_id}", response_model=ListingResponse)
async def get_listing(listing_id: UUID, db: AsyncSession = Depends(get_db)):
    query = (
        select(Listing)
        .where(Listing.id == listing_id)
        .options(selectinload(Listing.seller), selectinload(Listing.card), selectinload(Listing.images))
    )
    result = await db.execute(query)
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    # Increment views
    listing.views += 1
    await db.flush()

    return ListingResponse.model_validate(listing)


@router.post("", response_model=ListingResponse, status_code=201)
async def create_listing(
    data: ListingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        # Verify card exists
        from models.card import Card
        card_result = await db.execute(select(Card).where(Card.id == data.card_id))
        card = card_result.scalar_one_or_none()
        if not card:
            raise HTTPException(status_code=404, detail="Card not found")

        # Auto-generate title from card if not provided
        title = data.title or f"{card.name} — {card.parallel or card.card_type} [{data.condition}]"

        listing = Listing(
            seller_id=current_user.id,
            card_id=data.card_id,
            title=title,
            description=data.description,
            condition=data.condition,
            price_cents=data.price_cents,
            quantity=data.quantity,
            quantity_available=data.quantity,
        )
        db.add(listing)
        await db.flush()

        # Reload with relationships
        query = (
            select(Listing)
            .where(Listing.id == listing.id)
            .options(selectinload(Listing.seller), selectinload(Listing.card), selectinload(Listing.images))
        )
        result = await db.execute(query)
        listing = result.scalar_one()
        return ListingResponse.model_validate(listing)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create listing: {type(e).__name__}: {str(e)}")


@router.put("/{listing_id}", response_model=ListingResponse)
async def update_listing(
    listing_id: UUID,
    data: ListingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.seller_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your listing")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(listing, field, value)
    await db.flush()

    return ListingResponse.model_validate(listing)


@router.delete("/{listing_id}", status_code=204)
async def delete_listing(
    listing_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.seller_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    listing.status = "removed"
    await db.flush()
