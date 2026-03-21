#!/usr/bin/env python3
"""
One-off backfill: bet slip from Fri 13 Mar 2025 (manually extracted from screenshot).

Bet ref: DX6940028191W
Placed:  Fri 13 Mar 15:03, bet365
Stake:   €20.00
Return:  €1,231.07

Run from the server punter-bot directory:
    python3 scripts/backfill_betslip_wk13mar.py
    python3 scripts/backfill_betslip_wk13mar.py --dry-run
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.db import get_db, init_db
from src.services.bet_slip_service import match_legs_to_picks, record_bet_slip, update_confirmed_odds
from src.services.pick_service import get_picks_for_week

EXTRACTED = {
    "stake": 20.00,
    "total_odds": round(1231.07 / 20, 4),  # 61.5535
    "potential_return": 1231.07,
    "legs": [
        {"selection": "Ireland -2.5",   "odds": round(21 / 13, 4)},  # 8/13  = 1.6154
        {"selection": "Wales +3.5",     "odds": round(21 / 11, 4)},  # 10/11 = 1.9091
        {"selection": "Gaelic Warrior", "odds": 4.0},                # 3/1   = 4.0
        {"selection": "Man Utd",        "odds": round(19 / 11, 4)},  # 8/11  = 1.7273
        {"selection": "Kerry",          "odds": round(13 / 9,  4)},  # 4/9   = 1.4444
        {"selection": "Dublin +1",      "odds": 2.0},                # 1/1   = 2.0 (inferred: 61.5535 / 30.777)
    ],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_db()
    conn = get_db()

    # Find the week that was open/closed around 13 Mar 2025
    week = conn.execute(
        "SELECT * FROM weeks WHERE created_at LIKE '2025-03-1%' ORDER BY id DESC LIMIT 1"
    ).fetchone()

    if not week:
        # Fallback: most recent completed week
        week = conn.execute(
            "SELECT * FROM weeks WHERE status = 'completed' ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if not week:
        print("Error: could not find a week for 13 Mar 2025. "
              "Run: SELECT id, week_number, status, created_at FROM weeks ORDER BY id DESC LIMIT 10;")
        conn.close()
        sys.exit(1)

    print(f"Week {week['week_number']} (id={week['id']}, status={week['status']}, "
          f"placer_id={week['placer_id']}, created_at={week['created_at']})")

    # Check for existing slip
    existing = conn.execute(
        "SELECT id FROM bet_slips WHERE week_id = ?", (week["id"],)
    ).fetchone()
    if existing:
        print(f"Warning: bet_slips row already exists (id={existing['id']}) for this week.")

    picks = get_picks_for_week(week["id"])
    conn.close()

    print(f"\n{len(picks)} picks this week:")
    for p in picks:
        print(f"  [{p['id']}] {p['description']}")

    print(f"\nExtracted legs:")
    for leg in EXTRACTED["legs"]:
        print(f"  {leg['selection']:25s}  {leg['odds']}")

    matched = match_legs_to_picks(EXTRACTED["legs"], picks)
    print(f"\nMatched {len(matched)}/{len(EXTRACTED['legs'])} legs:")
    for pick_id, odds in matched:
        pick = next((p for p in picks if p["id"] == pick_id), None)
        print(f"  pick {pick_id} ({pick['description'] if pick else '?'}) → confirmed_odds={odds}")

    unmatched = len(EXTRACTED["legs"]) - len(matched)
    if unmatched:
        print(f"  ({unmatched} leg(s) unmatched — check WARNING lines above)")

    if args.dry_run:
        print("\n[dry-run] No changes written.")
        return

    if week["placer_id"]:
        record_bet_slip(week["id"], week["placer_id"], EXTRACTED)
        print(f"\nInserted bet_slips row.")
    else:
        print("\nWarning: week has no placer_id — skipping bet_slips insert.")
        print("Set it manually: UPDATE weeks SET placer_id = <id> WHERE id = <week_id>;")

    if matched:
        update_confirmed_odds(matched)
        print(f"Updated confirmed_odds on {len(matched)} pick(s).")

    print("Done.")


if __name__ == "__main__":
    main()
