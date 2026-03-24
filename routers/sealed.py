from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.sealed_product import SealedProduct

router = APIRouter(prefix="/api/sealed", tags=["sealed"])


@router.get("")
async def list_sealed(
    product_type: str | None = Query(None),
    set_name: str | None = Query(None),
    q: str | None = Query(None),
    sort: str = Query("name"),
    page: int = Query(1, ge=1),
    limit: int = Query(48, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List sealed products with optional filters."""
    query = select(SealedProduct)

    if product_type:
        query = query.where(SealedProduct.product_type == product_type)
    if set_name:
        query = query.where(SealedProduct.set_name == set_name)
    if q:
        search = f"%{q}%"
        query = query.where(SealedProduct.name.ilike(search))

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sort
    sort_map = {
        "name": SealedProduct.name,
        "price_asc": SealedProduct.last_sale_price.asc().nulls_last(),
        "price_desc": SealedProduct.last_sale_price.desc().nulls_last(),
        "set": SealedProduct.set_name,
        "newest": SealedProduct.created_at.desc(),
    }
    order = sort_map.get(sort, SealedProduct.name)
    if sort not in ("price_asc", "price_desc", "newest"):
        query = query.order_by(order)
    else:
        query = query.order_by(order)

    query = query.offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    products = result.scalars().all()

    return {
        "sealed_products": [
            {
                "id": str(p.id),
                "name": p.name,
                "set_name": p.set_name,
                "product_type": p.product_type,
                "year": p.year,
                "msrp_cents": p.msrp_cents,
                "description": p.description,
                "image_url": p.image_url,
                "cards_per_pack": p.cards_per_pack,
                "packs_per_box": p.packs_per_box,
                "last_sale_price": float(p.last_sale_price) if p.last_sale_price else None,
                "avg_price_30d": float(p.avg_price_30d) if p.avg_price_30d else None,
                "total_sales": p.total_sales,
            }
            for p in products
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/types")
async def sealed_types(db: AsyncSession = Depends(get_db)):
    """Get available sealed product types."""
    result = await db.execute(
        select(SealedProduct.product_type, func.count(SealedProduct.id))
        .group_by(SealedProduct.product_type)
        .order_by(func.count(SealedProduct.id).desc())
    )
    return [{"type": row[0], "count": row[1]} for row in result.all()]


@router.get("/{product_id}")
async def get_sealed_product(product_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get a single sealed product by ID."""
    result = await db.execute(select(SealedProduct).where(SealedProduct.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Sealed product not found")

    return {
        "id": str(product.id),
        "name": product.name,
        "set_name": product.set_name,
        "product_type": product.product_type,
        "year": product.year,
        "msrp_cents": product.msrp_cents,
        "description": product.description,
        "image_url": product.image_url,
        "cards_per_pack": product.cards_per_pack,
        "packs_per_box": product.packs_per_box,
        "last_sale_price": float(product.last_sale_price) if product.last_sale_price else None,
        "avg_price_30d": float(product.avg_price_30d) if product.avg_price_30d else None,
        "total_sales": product.total_sales,
    }
