"""
Price tracker — detect new listings, price changes, and listing age.

Compares today's Bayut scrape against historical snapshots to identify:
- New listings (appeared today)
- Removed listings (disappeared)
- Price drops > 5% (motivated sellers)
- Price increases
- Listing age (days since first seen)

Usage:
    from listing_matcher.price_tracker import snapshot_and_diff
    changes = snapshot_and_diff()  # saves today's snapshot + returns diff
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

BAYUT_CSV = Path("data/bayut_palm_listings.csv")
HISTORY_DIR = Path("data/bayut_history")
TRACKER_JSON = Path("data/bayut_tracker.json")


def _load_tracker() -> dict:
    """Load persistent tracker state (first-seen dates, last prices)."""
    if TRACKER_JSON.exists():
        try:
            return json.loads(TRACKER_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"listings": {}, "last_snapshot": None}


def _save_tracker(tracker: dict):
    TRACKER_JSON.parent.mkdir(parents=True, exist_ok=True)
    TRACKER_JSON.write_text(json.dumps(tracker, indent=2, default=str), encoding="utf-8")


def snapshot_and_diff() -> dict:
    """
    Save today's Bayut data as a snapshot and compute diff against previous.

    Returns:
        {
            "date": "2026-04-07",
            "total_listings": 3038,
            "new_listings": [...],
            "removed_listings": [...],
            "price_drops": [...],      # >5% decrease
            "price_increases": [...],  # >5% increase
            "stats": { "new": N, "removed": N, "price_drops": N, "price_increases": N }
        }
    """
    if not BAYUT_CSV.exists():
        return {"error": "No Bayut data file found"}

    today = datetime.now().strftime("%Y-%m-%d")
    df = pd.read_csv(BAYUT_CSV, low_memory=False)

    if df.empty:
        return {"error": "Bayut CSV is empty"}

    # Save daily snapshot
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = HISTORY_DIR / f"{today}.csv"
    df.to_csv(snapshot_path, index=False)

    # Load tracker
    tracker = _load_tracker()
    listings_state = tracker.get("listings", {})

    # Current listings keyed by URL
    current = {}
    for _, row in df.iterrows():
        url = str(row.get("listing_url", "")).strip()
        if not url:
            continue
        current[url] = {
            "building": row.get("building_name", ""),
            "bedrooms": row.get("bedrooms"),
            "size_sqft": row.get("size_sqft"),
            "price": row.get("price_aed"),
            "listing_type": row.get("listing_type", ""),
        }

    previous_urls = set(listings_state.keys())
    current_urls = set(current.keys())

    # New listings
    new_urls = current_urls - previous_urls
    new_listings = []
    for url in new_urls:
        info = current[url]
        listings_state[url] = {
            "first_seen": today,
            "last_price": info["price"],
            "building": info["building"],
        }
        new_listings.append({**info, "url": url, "first_seen": today})

    # Removed listings
    removed_urls = previous_urls - current_urls
    removed_listings = []
    for url in removed_urls:
        prev = listings_state.pop(url, {})
        removed_listings.append({
            "url": url,
            "building": prev.get("building", ""),
            "first_seen": prev.get("first_seen"),
            "last_price": prev.get("last_price"),
            "days_listed": (datetime.now() - datetime.strptime(prev["first_seen"], "%Y-%m-%d")).days if prev.get("first_seen") else None,
        })

    # Price changes (existing listings)
    price_drops = []
    price_increases = []
    for url in current_urls & previous_urls:
        prev = listings_state.get(url, {})
        old_price = prev.get("last_price")
        new_price = current[url]["price"]

        if old_price and new_price and old_price > 0:
            pct_change = ((new_price - old_price) / old_price) * 100

            if pct_change <= -5:
                price_drops.append({
                    **current[url],
                    "url": url,
                    "old_price": old_price,
                    "new_price": new_price,
                    "pct_change": round(pct_change, 1),
                    "first_seen": prev.get("first_seen"),
                })
            elif pct_change >= 5:
                price_increases.append({
                    **current[url],
                    "url": url,
                    "old_price": old_price,
                    "new_price": new_price,
                    "pct_change": round(pct_change, 1),
                })

        # Update last price
        listings_state[url] = {
            **prev,
            "last_price": new_price,
            "building": current[url]["building"],
        }

    # Save updated tracker
    tracker["listings"] = listings_state
    tracker["last_snapshot"] = today
    _save_tracker(tracker)

    return {
        "date": today,
        "total_listings": len(current),
        "new_listings": sorted(new_listings, key=lambda x: x.get("price") or 0, reverse=True),
        "removed_listings": removed_listings,
        "price_drops": sorted(price_drops, key=lambda x: x.get("pct_change", 0)),
        "price_increases": sorted(price_increases, key=lambda x: x.get("pct_change", 0), reverse=True),
        "stats": {
            "new": len(new_listings),
            "removed": len(removed_listings),
            "price_drops": len(price_drops),
            "price_increases": len(price_increases),
        },
    }


def get_listing_age(listing_url: str) -> int | None:
    """Get days since listing was first seen. Returns None if unknown."""
    tracker = _load_tracker()
    info = tracker.get("listings", {}).get(listing_url)
    if not info or not info.get("first_seen"):
        return None
    first = datetime.strptime(info["first_seen"], "%Y-%m-%d")
    return (datetime.now() - first).days


def get_price_history(listing_url: str) -> list[dict]:
    """Get price history from daily snapshots for a specific listing."""
    history = []
    if not HISTORY_DIR.exists():
        return history

    for csv_path in sorted(HISTORY_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(csv_path, low_memory=False)
            match = df[df["listing_url"] == listing_url]
            if not match.empty:
                row = match.iloc[0]
                history.append({
                    "date": csv_path.stem,
                    "price": row.get("price_aed"),
                    "building": row.get("building_name"),
                })
        except Exception:
            continue

    return history
