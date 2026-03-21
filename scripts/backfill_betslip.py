#!/usr/bin/env python3
"""
Backfill a bet slip for a previous week from a local image file.

Usage (run on the server from the punter-bot directory):
    python3 scripts/backfill_betslip.py --week-id 12 --image /tmp/slip.jpg
    python3 scripts/backfill_betslip.py --week-id 12 --image /tmp/slip.jpg --dry-run

Requires: GROQ_API_KEY in .env, and the DB to be accessible (DB_PATH in .env or default).
"""

import argparse
import base64
import json
import sys
from pathlib import Path

# Add project root to path so src imports work
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env before importing Config
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.config import Config
from src.db import get_db, init_db
from src import llm_client
from src.services.bet_slip_service import match_legs_to_picks, record_bet_slip, update_confirmed_odds
from src.services.pick_service import get_picks_for_week


def main():
    parser = argparse.ArgumentParser(description="Backfill bet slip for a past week")
    parser.add_argument("--week-id", type=int, required=True, help="Week ID from the weeks table")
    parser.add_argument("--image", required=True, help="Path to the bet slip image")
    parser.add_argument("--dry-run", action="store_true", help="Extract and match but don't write to DB")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"Error: image not found: {image_path}")
        sys.exit(1)

    if not Config.GROQ_API_KEY:
        print("Error: GROQ_API_KEY not set in .env")
        sys.exit(1)

    init_db()

    # Resolve week + placer
    conn = get_db()
    week = conn.execute("SELECT * FROM weeks WHERE id = ?", (args.week_id,)).fetchone()
    if not week:
        print(f"Error: no week found with id={args.week_id}")
        conn.close()
        sys.exit(1)

    # Check for existing bet slip
    existing = conn.execute("SELECT id FROM bet_slips WHERE week_id = ?", (args.week_id,)).fetchone()
    conn.close()

    if existing and not args.dry_run:
        print(f"Warning: bet_slips row already exists for week {args.week_id} (id={existing['id']}). Proceeding anyway.")

    placer_id = week["placer_id"]
    if not placer_id:
        print(f"Warning: week {args.week_id} has no placer_id recorded — bet_slips row will have placer_id=NULL")

    print(f"Week {week['week_number']} (id={week['id']}, status={week['status']}, placer_id={placer_id})")

    # Read and encode image
    suffix = image_path.suffix.lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    mime = mime_map.get(suffix, "image/jpeg")
    image_b64 = base64.b64encode(image_path.read_bytes()).decode()
    print(f"Image: {image_path.name} ({len(image_b64)} bytes b64, {mime})")

    # Extract via Groq vision
    print("Calling Groq vision...")
    extracted = llm_client.read_bet_slip(image_b64, mime)
    if not extracted:
        print("Error: Groq extraction returned nothing — check GROQ_API_KEY and model availability")
        sys.exit(1)

    print(f"Extracted:")
    print(f"  stake:           {extracted.get('stake')}")
    print(f"  total_odds:      {extracted.get('total_odds')}")
    print(f"  potential_return:{extracted.get('potential_return')}")
    legs = extracted.get("legs") or []
    print(f"  legs ({len(legs)}):")
    for leg in legs:
        print(f"    {leg.get('selection')} @ {leg.get('odds')}")

    # Match legs to picks
    picks = get_picks_for_week(args.week_id)
    if not picks:
        print(f"Warning: no picks found for week {args.week_id}")
    else:
        print(f"\nMatching against {len(picks)} picks:")
        for p in picks:
            print(f"  [{p['id']}] {p['description']}")

    matched = match_legs_to_picks(legs, picks) if picks else []
    print(f"\nMatched {len(matched)} leg(s):")
    for pick_id, odds in matched:
        pick = next((p for p in picks if p["id"] == pick_id), None)
        desc = pick["description"] if pick else "?"
        print(f"  pick {pick_id} ({desc}) → confirmed_odds={odds}")

    if args.dry_run:
        print("\n[dry-run] No changes written to DB.")
        return

    # Write to DB
    if placer_id:
        record_bet_slip(args.week_id, placer_id, extracted)
        print(f"\nInserted bet_slips row for week {args.week_id}")
    else:
        print("\nSkipping bet_slips insert — no placer_id on week")

    if matched:
        update_confirmed_odds(matched)
        print(f"Updated confirmed_odds on {len(matched)} pick(s)")

    print("Done.")


if __name__ == "__main__":
    main()
