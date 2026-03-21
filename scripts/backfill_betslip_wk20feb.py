#!/usr/bin/env python3
"""
One-off backfill: bet slip from week 1, Fri 20 Feb 2026 (Novibet).

Bookmaker:  Novibet
Bet type:   Accumulator, 6 choices
Stake:      €20.00
Total odds: ~40/1 (pre-boost return €805.75 → 40.29 decimal)
Boost:      +20% → €966.90

All 6 leg odds are visible on the slip.

Run from the server punter-bot directory:
    python3 scripts/backfill_betslip_wk20feb.py
    python3 scripts/backfill_betslip_wk20feb.py --dry-run
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
    "total_odds": round(805.75 / 20, 4),  # 40.2875 (pre-boost; slip shows ~40/1)
    "potential_return": 966.90,            # boosted payout (+20%)
    "legs": [
        {"selection": "Scotland -18.5", "odds": round(19 / 10, 4)},  # 9/10  = 1.9
        {"selection": "Italy +27.5",    "odds": round(11 / 6,  4)},  # 5/6   = 1.8333
        {"selection": "Aston Villa",    "odds": round(37 / 20, 4)},  # 17/20 = 1.85
        {"selection": "Liverpool",      "odds": round(11 / 6,  4)},  # 5/6   = 1.8333
        {"selection": "Yes",            "odds": round(37 / 20, 4)},  # 17/20 = 1.85 (BTTS Wimbledon v Bradford)
        {"selection": "Ireland +10.5",  "odds": round(37 / 20, 4)},  # 17/20 = 1.85
    ],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_db()
    conn = get_db()

    week = conn.execute(
        "SELECT * FROM weeks WHERE week_number = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()

    if not week:
        print("Error: could not find week 1. "
              "Run: SELECT id, week_number, status, created_at FROM weeks ORDER BY id DESC LIMIT 10;")
        conn.close()
        sys.exit(1)

    print(f"Week {week['week_number']} (id={week['id']}, status={week['status']}, "
          f"placer_id={week['placer_id']}, created_at={week['created_at']})")

    existing = conn.execute(
        "SELECT id FROM bet_slips WHERE week_id = ?", (week["id"],)
    ).fetchone()
    if existing:
        print(f"Warning: bet_slips row already exists (id={existing['id']}) for this week.")

    conn.close()

    picks = get_picks_for_week(week["id"])
    print(f"\n{len(picks)} picks this week:")
    for p in picks:
        print(f"  [{p['id']}] {p['description']}  (odds_decimal={p.get('odds_decimal')})")

    print(f"\nExtracted legs:")
    for leg in EXTRACTED["legs"]:
        print(f"  {leg['selection']:20s}  {leg['odds']}")

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

    conn = get_db()
    if week["placer_id"]:
        conn.execute(
            """
            INSERT INTO bet_slips (week_id, placer_id, total_odds, stake, potential_return)
            VALUES (?, ?, ?, ?, ?)
            """,
            (week["id"], week["placer_id"],
             EXTRACTED["total_odds"], EXTRACTED["stake"], EXTRACTED["potential_return"]),
        )
        conn.commit()
        print(f"\nInserted bet_slips row.")
    else:
        print("\nWarning: no placer_id on week — skipping bet_slips insert.")
    conn.close()

    if matched:
        update_confirmed_odds(matched)
        print(f"Updated confirmed_odds on {len(matched)} pick(s).")

    print("Done.")


if __name__ == "__main__":
    main()
