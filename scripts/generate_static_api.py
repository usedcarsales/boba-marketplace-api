#!/usr/bin/env python3
"""
Generate static JSON API files from the card cache.
These can be served directly by the frontend (Next.js public dir)
or a CDN, enabling a fully functional card browser without a database.

Output structure:
  frontend/public/api/
    cards/
      index.json           # Paginated card list (page 1, 50 per page)
      page-2.json          # Page 2, etc.
      filters.json         # All filter options
      sets.json            # Set list with counts
      [id].json            # Individual card detail (by radish_id)
    stats.json             # Overall stats
"""

import json
import math
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
CACHE_FILE = PROJECT_ROOT / "data" / "radish_cards.json"
OUTPUT_DIR = PROJECT_ROOT / "frontend" / "public" / "api"

PAGE_SIZE = 48  # 4 columns x 12 rows


def classify_card_type(card: dict) -> str:
    card_num = (card.get("card_number") or "").upper()
    if card_num.startswith("HD-"):
        return "Hot Dog"
    elif card_num.startswith("BPL-"):
        return "Bonus Play"
    elif card_num.startswith("PL-"):
        return "Play"
    elif card.get("power") and card["power"] > 0:
        return "Hero"
    elif "play" in (card.get("parallel") or "").lower():
        return "Play"
    elif "hot dog" in (card.get("parallel") or "").lower():
        return "Hot Dog"
    return "Hero"


def transform(raw: dict) -> dict:
    return {
        "id": raw["id"],
        "name": raw.get("name", "Unknown"),
        "card_number": raw.get("card_number", ""),
        "card_type": classify_card_type(raw),
        "set_name": raw.get("set", "Unknown"),
        "year": raw.get("year"),
        "parallel": raw.get("parallel"),
        "weapon": raw.get("weapon") or None,
        "power": raw.get("power") if raw.get("power") else None,
        "last_sale_price": raw.get("lastSalePrice"),
        "last_sale_date": raw.get("lastSaleDate"),
        "avg_price_30d": raw.get("avgPriceLast30Days"),
        "total_sales": raw.get("totalSales", 0),
        "sales_last_30d": raw.get("salesLast30Days", 0),
        "image_url": raw.get("image"),
        "last_sale_image": raw.get("lastSaleImage"),
    }


def main():
    if not CACHE_FILE.exists():
        print(f"[!] Cache not found: {CACHE_FILE}")
        print("    Run seed_cards.py first")
        sys.exit(1)

    with open(CACHE_FILE) as f:
        data = json.load(f)

    cards = [transform(c) for c in data["cards"]]
    print(f"[*] Transforming {len(cards)} cards...")

    # Sort by name
    cards.sort(key=lambda c: c["name"].lower())

    # Create output dirs
    cards_dir = OUTPUT_DIR / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    # ── Paginated card list ───────────────────────────────────────
    total_pages = math.ceil(len(cards) / PAGE_SIZE)
    for page in range(1, total_pages + 1):
        start = (page - 1) * PAGE_SIZE
        end = start + PAGE_SIZE
        page_data = {
            "cards": cards[start:end],
            "total": len(cards),
            "page": page,
            "limit": PAGE_SIZE,
            "total_pages": total_pages,
        }
        filename = "index.json" if page == 1 else f"page-{page}.json"
        with open(cards_dir / filename, "w") as f:
            json.dump(page_data, f)
        if page % 50 == 0:
            print(f"  [*] Generated page {page}/{total_pages}")

    print(f"[✓] Generated {total_pages} card list pages")

    # ── Filter options ────────────────────────────────────────────
    sets = sorted(set(c["set_name"] for c in cards))
    weapons = sorted(set(c["weapon"] for c in cards if c["weapon"]))
    parallels = sorted(set(c["parallel"] for c in cards if c["parallel"]))
    card_types = sorted(set(c["card_type"] for c in cards))
    years = sorted(set(c["year"] for c in cards if c["year"]))

    filters = {
        "sets": sets,
        "weapons": weapons,
        "parallels": parallels,
        "card_types": card_types,
        "years": years,
    }
    with open(cards_dir / "filters.json", "w") as f:
        json.dump(filters, f, indent=2)
    print("[✓] Generated filters.json")

    # ── Set list with counts ──────────────────────────────────────
    set_counts = {}
    for c in cards:
        s = c["set_name"]
        set_counts[s] = set_counts.get(s, 0) + 1
    sets_data = [{"name": s, "count": set_counts[s]} for s in sorted(set_counts.keys())]
    with open(cards_dir / "sets.json", "w") as f:
        json.dump(sets_data, f, indent=2)
    print(f"[✓] Generated sets.json ({len(sets_data)} sets)")

    # ── Overall stats ─────────────────────────────────────────────
    priced = [c for c in cards if c["last_sale_price"]]
    with_images = [c for c in cards if c["image_url"]]
    stats = {
        "total_cards": len(cards),
        "cards_with_pricing": len(priced),
        "cards_with_images": len(with_images),
        "total_sets": len(sets),
        "total_weapons": len(weapons),
        "total_parallels": len(parallels),
        "avg_price": round(sum(c["last_sale_price"] for c in priced) / len(priced), 2) if priced else 0,
        "most_expensive": max((c["last_sale_price"] for c in priced), default=0),
    }
    with open(OUTPUT_DIR / "stats.json", "w") as f:
        json.dump(stats, f, indent=2)
    print("[✓] Generated stats.json")

    # ── Search index (lightweight) ────────────────────────────────
    # Small JSON with just id, name, set, card_number for client-side search
    search_index = [
        {
            "id": c["id"],
            "n": c["name"],
            "s": c["set_name"],
            "cn": c["card_number"],
            "w": c["weapon"],
            "p": c["parallel"],
        }
        for c in cards
    ]
    with open(cards_dir / "search-index.json", "w") as f:
        json.dump(search_index, f)
    search_size = (cards_dir / "search-index.json").stat().st_size / (1024 * 1024)
    print(f"[✓] Generated search-index.json ({search_size:.1f} MB)")

    total_size = sum(f.stat().st_size for f in OUTPUT_DIR.rglob("*.json")) / (1024 * 1024)
    print(f"\n[✓] Total static API size: {total_size:.1f} MB")
    print(f"    Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
