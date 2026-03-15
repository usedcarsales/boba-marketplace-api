#!/usr/bin/env python3
"""
BoBA Card Seeder — Fetches all cards from Radish Price Guide API.

Usage:
    python seed_cards.py                    # Fetch + save JSON cache
    python seed_cards.py --dry-run          # Fetch + save JSON only (no DB)
    python seed_cards.py --from-cache       # Load from existing JSON cache
    python seed_cards.py --db               # Save to database (requires DATABASE_URL)

API: GET https://radishpriceguide.com/api/boba/getFilteredCards
Response: {cards: [...], total, page, limit, totalPages}
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_FILE = DATA_DIR / "radish_cards.json"

# API
BASE_URL = "https://radishpriceguide.com/api/boba/getFilteredCards"
PAGE_SIZE = 100
DELAY_SECONDS = 1.0  # Be polite


def classify_card_type(card: dict) -> str:
    """Determine card type from Radish data."""
    parallel = (card.get("parallel") or "").lower()
    card_num = (card.get("card_number") or "").upper()

    if card_num.startswith("HD-"):
        return "Hot Dog"
    elif card_num.startswith("BPL-"):
        return "Bonus Play"
    elif card_num.startswith("PL-"):
        return "Play"
    elif card.get("power") and card["power"] > 0:
        return "Hero"
    elif "play" in parallel:
        return "Play"
    elif "hot dog" in parallel:
        return "Hot Dog"
    else:
        return "Hero"


async def fetch_all_cards() -> list[dict]:
    """Fetch all cards from Radish API, paginating through all pages."""
    all_cards = []
    page = 1

    async with httpx.AsyncClient(timeout=30.0) as client:
        # First request to get total
        print("[*] Fetching page 1 from Radish API...")
        resp = await client.get(BASE_URL, params={"limit": PAGE_SIZE, "page": 1, "sort": "name", "order": "asc"})
        resp.raise_for_status()
        data = resp.json()

        total = data["total"]
        total_pages = data["totalPages"]
        all_cards.extend(data["cards"])
        print(f"[*] Total cards: {total} across {total_pages} pages")

        # Fetch remaining pages
        for page in range(2, total_pages + 1):
            time.sleep(DELAY_SECONDS)  # Be polite
            print(f"[*] Fetching page {page}/{total_pages}... ({len(all_cards)}/{total} cards)")

            try:
                resp = await client.get(
                    BASE_URL, params={"limit": PAGE_SIZE, "page": page, "sort": "name", "order": "asc"}
                )
                resp.raise_for_status()
                data = resp.json()
                all_cards.extend(data["cards"])
            except Exception as e:
                print(f"[!] Error on page {page}: {e}")
                print("[!] Retrying in 5 seconds...")
                time.sleep(5)
                try:
                    resp = await client.get(
                        BASE_URL, params={"limit": PAGE_SIZE, "page": page, "sort": "name", "order": "asc"}
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    all_cards.extend(data["cards"])
                except Exception as e2:
                    print(f"[!] Failed again on page {page}: {e2}. Skipping.")

    print(f"[✓] Fetched {len(all_cards)} cards total")
    return all_cards


def save_to_cache(cards: list[dict]) -> None:
    """Save raw card data to JSON cache file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump({"total": len(cards), "cards": cards}, f, indent=2)
    size_mb = CACHE_FILE.stat().st_size / (1024 * 1024)
    print(f"[✓] Saved {len(cards)} cards to {CACHE_FILE} ({size_mb:.1f} MB)")


def load_from_cache() -> list[dict]:
    """Load cards from JSON cache."""
    if not CACHE_FILE.exists():
        print(f"[!] Cache file not found: {CACHE_FILE}")
        print("[!] Run without --from-cache first to fetch data")
        sys.exit(1)
    with open(CACHE_FILE) as f:
        data = json.load(f)
    print(f"[✓] Loaded {data['total']} cards from cache")
    return data["cards"]


def transform_card(raw: dict) -> dict:
    """Transform Radish API card into our database schema format."""
    return {
        "radish_id": raw.get("id"),
        "card_number": raw.get("card_number", ""),
        "name": raw.get("name", "Unknown"),
        "card_type": classify_card_type(raw),
        "set_name": raw.get("set", "Unknown"),
        "year": raw.get("year"),
        "parallel": raw.get("parallel"),
        "treatment": raw.get("parallel"),  # Radish uses "parallel" for treatment info
        "variation": None,  # Will be enriched from official checklists later
        "notation": None,  # Will be enriched from official checklists later
        "weapon": raw.get("weapon") or None,
        "power": raw.get("power") if raw.get("power") else None,
        "athlete": None,  # Will be enriched from official checklists later
        "play_cost": None,  # Will be enriched from official checklists later
        "play_ability": None,  # Will be enriched from official checklists later
        "last_sale_price": raw.get("lastSalePrice"),
        "last_sale_date": raw.get("lastSaleDate"),
        "avg_price_30d": raw.get("avgPriceLast30Days"),
        "total_sales": raw.get("totalSales", 0),
        "sales_last_30d": raw.get("salesLast30Days", 0),
        "image_url": raw.get("image"),
        "last_sale_image": raw.get("lastSaleImage"),
    }


def print_stats(cards: list[dict]) -> None:
    """Print summary statistics of the card data."""
    sets = {}
    types = {}
    weapons = {}
    with_price = 0
    with_image = 0

    for c in cards:
        t = transform_card(c)
        sets[t["set_name"]] = sets.get(t["set_name"], 0) + 1
        types[t["card_type"]] = types.get(t["card_type"], 0) + 1
        if t["weapon"]:
            weapons[t["weapon"]] = weapons.get(t["weapon"], 0) + 1
        if t["last_sale_price"]:
            with_price += 1
        if t["image_url"]:
            with_image += 1

    print(f"\n{'=' * 60}")
    print("  BoBA Card Catalog Stats")
    print(f"{'=' * 60}")
    print(f"  Total cards: {len(cards)}")
    print(f"  With price data: {with_price}")
    print(f"  With images: {with_image}")
    print("\n  Sets:")
    for s in sorted(sets.keys()):
        print(f"    {s}: {sets[s]}")
    print("\n  Card Types:")
    for t in sorted(types.keys()):
        print(f"    {t}: {types[t]}")
    print("\n  Weapons:")
    for w in sorted(weapons.keys()):
        print(f"    {w}: {weapons[w]}")
    print(f"{'=' * 60}\n")


async def insert_to_db(cards: list[dict]) -> None:
    """Insert cards into the database."""
    # Add backend to path for imports
    backend_dir = str(SCRIPT_DIR.parent)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    from sqlalchemy import select

    from database import async_session, init_db
    from models.card import Card

    await init_db()

    async with async_session() as session:
        inserted = 0
        updated = 0
        errors = 0

        for raw in cards:
            t = transform_card(raw)
            try:
                # Check if card already exists by radish_id
                if t["radish_id"]:
                    result = await session.execute(select(Card).where(Card.radish_id == t["radish_id"]))
                    existing = result.scalar_one_or_none()
                    if existing:
                        # Update pricing data
                        existing.last_sale_price = t["last_sale_price"]
                        existing.last_sale_date = t["last_sale_date"]
                        existing.avg_price_30d = t["avg_price_30d"]
                        existing.total_sales = t["total_sales"]
                        existing.sales_last_30d = t["sales_last_30d"]
                        if t["image_url"] and not existing.image_url:
                            existing.image_url = t["image_url"]
                        updated += 1
                        continue

                card = Card(**t)
                session.add(card)
                inserted += 1

                # Batch commit every 500
                if inserted % 500 == 0:
                    await session.commit()
                    print(f"  [*] Inserted {inserted} cards...")

            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"  [!] Error inserting card {t['name']}: {e}")

        await session.commit()
        print("\n[✓] Database seeding complete:")
        print(f"    Inserted: {inserted}")
        print(f"    Updated: {updated}")
        print(f"    Errors: {errors}")


async def main():
    parser = argparse.ArgumentParser(description="BoBA Card Seeder")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and save JSON only, no DB insert")
    parser.add_argument("--from-cache", action="store_true", help="Use existing JSON cache instead of fetching")
    parser.add_argument("--db", action="store_true", help="Insert cards into database")
    parser.add_argument("--stats", action="store_true", help="Print stats only")
    args = parser.parse_args()

    # Load or fetch cards
    if args.from_cache:
        cards = load_from_cache()
    else:
        cards = await fetch_all_cards()
        save_to_cache(cards)

    # Stats
    print_stats(cards)

    # Database insert
    if args.db and not args.dry_run:
        print("[*] Inserting cards into database...")
        await insert_to_db(cards)
    elif not args.dry_run and not args.stats:
        print("[*] Cards saved to cache. Use --db to insert into database.")
        print("    python seed_cards.py --from-cache --db")


if __name__ == "__main__":
    asyncio.run(main())
