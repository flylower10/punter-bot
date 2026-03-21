#!/usr/bin/env python3
"""
One-off backfill: bet slip from week 5, Sat 21 Mar 2026 (bet365).

Bet ref: JB2115006861W
Placed:  Sat 21 Mar 09:11, bet365
Stake:   €20.00
Return:  €562.50

5 legs visible on slip. 6th leg cut off — inferred at 2.25 decimal (5/4):
    28.125 (total) / 12.5 (visible product) = 2.25

TODO: fill in MISSING_SELECTION with the 6th pick description before running.

Run from the server punter-bot directory:
    python3 scripts/backfill_betslip_wk21mar.py
    python3 scripts/backfill_betslip_wk21mar.py --dry-run
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

MISSING_SELECTION = "Plymouth"  # 6/5 = 2.2 decimal

EXTRACTED = {
    "stake": 20.00,
    "total_odds": round(562.50 / 20, 4),  # 28.125
    "potential_return": 562.50,
    "legs": [
        {"selection": "Over 5.5 cards",   "odds": 2.0},                 # 1/1
        {"selection": "Yes BTTS",          "odds": round(10 / 6, 4)},   # 4/6 = 1.6667 (Sheff Utd v Wrexham)
        {"selection": "Fulham",            "odds": 1.5},                 # 1/2
        {"selection": "Mayo",              "odds": 1.5},                 # 1/2 (Draw No Bet, v Roscommon)
        {"selection": "Everton (+1)",      "odds": round(10 / 6, 4)},   # 4/6 = 1.6667 (Handicap)
        {"selection": MISSING_SELECTION,   "odds": round(11 / 5, 4)},   # 6/5 = 2.2
    ],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_db()
    conn = get_db()

    week = conn.execute(
        "SELECT * FROM weeks WHERE week_number = 5 ORDER BY id DESC LIMIT 1"
    ).fetchone()

    if not week:
        print("Error: could not find week 5.")
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
