import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models.listing import Listing
from models.user import User
from models.seller_tier import SellerProfile, SellerTier, TIER_CONFIG, evaluate_tier, has_bulk_listing
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

        # Check listing slot limit based on seller tier
        profile_result = await db.execute(
            select(SellerProfile).where(SellerProfile.user_id == current_user.id)
        )
        profile = profile_result.scalar_one_or_none()
        if profile:
            tier = SellerTier(profile.tier)
            max_slots = TIER_CONFIG[tier]["max_listing_slots"]
            if max_slots is not None:
                active_count_result = await db.execute(
                    select(func.count(Listing.id)).where(
                        and_(Listing.seller_id == current_user.id, Listing.status == "active")
                    )
                )
                active_count = active_count_result.scalar() or 0
                if active_count >= max_slots:
                    raise HTTPException(
                        400,
                        f"Listing limit reached ({max_slots} for {TIER_CONFIG[tier]['display_name']} tier). "
                        f"Upgrade your seller tier for more slots!"
                    )

        listing = Listing(
            seller_id=current_user.id,
            card_id=data.card_id,
            title=title,
            description=data.description,
            condition=data.condition,
            price_cents=data.price_cents,
            quantity=data.quantity,
            quantity_available=data.quantity,
            source=getattr(data, "source", "manual"),
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


# --- Inventory Management Endpoints ---

class BulkPriceUpdate(BaseModel):
    listing_ids: list[str]
    adjustment_type: str = Field(description="'set', 'increase_percent', 'decrease_percent', 'increase_cents', 'decrease_cents'")
    value: int  # cents for set/increase_cents/decrease_cents, basis points for percent (e.g., 1000 = 10%)


class BulkStatusUpdate(BaseModel):
    listing_ids: list[str]
    status: str = Field(description="'active', 'paused', 'removed'")


class InventoryStats(BaseModel):
    active_listings: int
    paused_listings: int
    sold_listings: int
    total_inventory_value_cents: int
    total_views: int
    listing_slot_limit: int | None
    listing_slots_used: int
    seller_tier: str
    seller_tier_emoji: str


@router.get("/inventory/stats", response_model=InventoryStats)
async def get_inventory_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get seller's inventory overview stats."""
    uid = current_user.id

    # Counts by status
    active = (await db.execute(
        select(func.count(Listing.id)).where(and_(Listing.seller_id == uid, Listing.status == "active"))
    )).scalar() or 0
    paused = (await db.execute(
        select(func.count(Listing.id)).where(and_(Listing.seller_id == uid, Listing.status == "paused"))
    )).scalar() or 0
    sold = (await db.execute(
        select(func.count(Listing.id)).where(and_(Listing.seller_id == uid, Listing.status == "sold"))
    )).scalar() or 0

    # Total value of active inventory
    value = (await db.execute(
        select(func.sum(Listing.price_cents * Listing.quantity_available)).where(
            and_(Listing.seller_id == uid, Listing.status == "active")
        )
    )).scalar() or 0

    # Total views
    views = (await db.execute(
        select(func.sum(Listing.views)).where(Listing.seller_id == uid)
    )).scalar() or 0

    # Tier info
    profile = (await db.execute(
        select(SellerProfile).where(SellerProfile.user_id == uid)
    )).scalar_one_or_none()

    tier = SellerTier(profile.tier) if profile else SellerTier.STEEL
    config = TIER_CONFIG[tier]

    return InventoryStats(
        active_listings=active,
        paused_listings=paused,
        sold_listings=sold,
        total_inventory_value_cents=value,
        total_views=views,
        listing_slot_limit=config["max_listing_slots"],
        listing_slots_used=active,
        seller_tier=config["display_name"],
        seller_tier_emoji=config["emoji"],
    )


@router.post("/inventory/bulk-price")
async def bulk_update_prices(
    data: BulkPriceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk update prices for multiple listings."""
    updated = 0
    errors = []

    for lid in data.listing_ids:
        result = await db.execute(select(Listing).where(Listing.id == lid))
        listing = result.scalar_one_or_none()
        if not listing:
            errors.append(f"{lid}: not found")
            continue
        if str(listing.seller_id) != current_user.id:
            errors.append(f"{lid}: not your listing")
            continue

        if data.adjustment_type == "set":
            listing.price_cents = max(1, data.value)
        elif data.adjustment_type == "increase_percent":
            listing.price_cents = int(listing.price_cents * (1 + data.value / 10000))
        elif data.adjustment_type == "decrease_percent":
            listing.price_cents = max(1, int(listing.price_cents * (1 - data.value / 10000)))
        elif data.adjustment_type == "increase_cents":
            listing.price_cents += data.value
        elif data.adjustment_type == "decrease_cents":
            listing.price_cents = max(1, listing.price_cents - data.value)
        else:
            errors.append(f"{lid}: invalid adjustment type")
            continue
        updated += 1

    await db.flush()
    return {"updated": updated, "errors": errors}


@router.post("/inventory/bulk-status")
async def bulk_update_status(
    data: BulkStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk update status for multiple listings (pause, reactivate, remove)."""
    if data.status not in ("active", "paused", "removed"):
        raise HTTPException(400, "Status must be 'active', 'paused', or 'removed'")

    updated = 0
    errors = []

    for lid in data.listing_ids:
        result = await db.execute(select(Listing).where(Listing.id == lid))
        listing = result.scalar_one_or_none()
        if not listing:
            errors.append(f"{lid}: not found")
            continue
        if str(listing.seller_id) != current_user.id:
            errors.append(f"{lid}: not your listing")
            continue
        listing.status = data.status
        updated += 1

    await db.flush()
    return {"updated": updated, "errors": errors}


# --- Bulk Listing Tool (Fire+ tier) ---

class BulkListingItem(BaseModel):
    card_id: str
    condition: str = "NM"
    price_cents: int
    quantity: int = 1
    description: str | None = None


class BulkListingRequest(BaseModel):
    listings: list[BulkListingItem] = Field(max_length=50, description="Up to 50 listings per batch")
    source: str = "manual"


@router.post("/bulk-create")
async def bulk_create_listings(
    data: BulkListingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple listings in one batch. Requires Fire tier or higher."""
    from models.card import Card

    # Check tier access
    profile_result = await db.execute(
        select(SellerProfile).where(SellerProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()
    tier = SellerTier(profile.tier) if profile else SellerTier.STEEL
    
    if not has_bulk_listing(tier):
        raise HTTPException(
            403,
            f"Bulk listing requires Fire tier or higher. You are currently {TIER_CONFIG[tier]['display_name']}. "
            f"Reach $100 in 30-day sales volume to unlock!"
        )

    # Check slot limits
    max_slots = TIER_CONFIG[tier]["max_listing_slots"]
    if max_slots is not None:
        active_count = (await db.execute(
            select(func.count(Listing.id)).where(
                and_(Listing.seller_id == current_user.id, Listing.status == "active")
            )
        )).scalar() or 0
        remaining = max_slots - active_count
        if len(data.listings) > remaining:
            raise HTTPException(
                400,
                f"Not enough listing slots. You have {remaining} remaining "
                f"({active_count}/{max_slots} used). Upgrade your tier for more!"
            )

    created = []
    errors = []

    for i, item in enumerate(data.listings):
        try:
            # Verify card exists
            card_result = await db.execute(select(Card).where(Card.id == item.card_id))
            card = card_result.scalar_one_or_none()
            if not card:
                errors.append({"index": i, "card_id": item.card_id, "error": "Card not found"})
                continue

            title = f"{card.name} — {card.parallel or card.card_type} [{item.condition}]"
            listing = Listing(
                seller_id=current_user.id,
                card_id=item.card_id,
                title=title,
                description=item.description,
                condition=item.condition,
                price_cents=item.price_cents,
                quantity=item.quantity,
                quantity_available=item.quantity,
                source=data.source,
            )
            db.add(listing)
            await db.flush()
            created.append({
                "index": i,
                "listing_id": str(listing.id),
                "title": title,
                "price_cents": item.price_cents,
            })
        except Exception as e:
            errors.append({"index": i, "card_id": item.card_id, "error": str(e)})

    await db.commit()
    return {
        "created": len(created),
        "errors": len(errors),
        "listings": created,
        "error_details": errors,
    }
