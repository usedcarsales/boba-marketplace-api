#!/usr/bin/env python3
"""
Fetch filter options from Radish Price Guide API.
Useful for understanding the full taxonomy of BoBA cards.

API: GET https://radishpriceguide.com/api/boba/getFilterOptions
"""

import asyncio
import json
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).parent.parent.parent / "data"
FILTER_CACHE = DATA_DIR / "radish_filters.json"


async def fetch_filters():
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get("https://radishpriceguide.com/api/boba/getFilterOptions")
        resp.raise_for_status()
        data = resp.json()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(FILTER_CACHE, "w") as f:
        json.dump(data, f, indent=2)

    print("BoBA Card Taxonomy (from Radish)")
    print("=" * 50)

    for key, values in sorted(data.items()):
        if isinstance(values, list):
            print(f"\n{key} ({len(values)}):")
            for v in sorted(values):
                print(f"  - {v}")

    print(f"\nSaved to {FILTER_CACHE}")


if __name__ == "__main__":
    asyncio.run(fetch_filters())
