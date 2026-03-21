#!/usr/bin/env python3
"""
One-off backfill: bet slip from week 2, ~Fri 28 Feb 2025 (Paddy Power).

Bookmaker:  Paddy Power (Power Up boost applied)
Bet type:   6 Folds
Stake:      €20.00
Pre-boost:  29.28/1 = 30.28 decimal → €605.68 return
Boosted:    33.68/1 = 34.68 decimal → €693.67 return (Power Up +€87.99)

Individual leg odds are NOT shown on this slip format. confirmed_odds is
inferred from the pick's own odds_decimal (submitted price) for each matched leg.

Run from the server punter-bot directory:
    python3 scripts/backfill_betslip_wk27feb.py
    python3 scripts/backfill_betslip_wk27feb.py --dry-run
"""

import argparse
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.db import get_db, init_db
from src.services.pick_service import get_picks_for_week
from src.services.bet_slip_service import update_confirmed_odds

EXTRACTED = {
    "stake": 20.00,
    "total_odds": round(605.68 / 20, 4),   # 30.284 (pre-boost, 29.28/1)
    "potential_return": 693.67,             # boosted payout (Power Up +€87.99)
}

# Selections as they appear on the slip — no individual odds available
SELECTIONS = [
    "Dublin",       # Roscommon v Dublin - Handicap Betting
    "Cavan",        # Cavan v Louth - Match Winner
    "Bournemouth",  # Bournemouth v Sunderland - Match Odds
    "Yes",          # Newcastle v Everton - Both Teams to Score
    "Man Utd",      # Man Utd v Crystal Palace - Match Odds
    "Ipswich",      # Ipswich v Swansea - Match Odds
]


def match_selections_to_picks(selections, picks, threshold=0.5):
    """
    Fuzzy-match slip selection strings to pick descriptions.
    Returns list of (pick_id, confirmed_odds) where confirmed_odds comes
    from the pick's own odds_decimal (no slip odds available for this slip).
    """
    matched = []
    for selection in selections:
        sel_lower = selection.lower().strip()
        best_ratio = 0.0
        best_pick = None
        for pick in picks:
            desc = (pick.get("description") or "").lower().strip()
            ratio = difflib.SequenceMatcher(None, sel_lower, desc).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_pick = pick
        if best_pick and best_ratio >= threshold:
            confirmed_odds = best_pick.get("odds_decimal")
            matched.append((best_pick["id"], confirmed_odds))
            print(
                f"  MATCH  '{selection}' → [{best_pick['id']}] '{best_pick['description']}' "
                f"(ratio={best_ratio:.2f}, confirmed_odds={confirmed_odds})"
            )
        else:
            best_desc = best_pick["description"] if best_pick else "none"
            print(f"  MISS   '{selection}' (best={best_ratio:.2f} '{best_desc}')")
    return matched


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_db()
    conn = get_db()

    week = conn.execute(
        "SELECT * FROM weeks WHERE week_number = 2 ORDER BY id DESC LIMIT 1"
    ).fetchone()

    if not week:
        print("Error: could not find week 2. "
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

    print(f"\nMatching {len(SELECTIONS)} selections against picks:")
    matched = match_selections_to_picks(SELECTIONS, picks)
    print(f"\nMatched {len(matched)}/{len(SELECTIONS)} selections.")

    # Verify: product of matched odds_decimal vs total_odds
    if matched:
        product = 1.0
        for _, odds in matched:
            if odds:
                product *= odds
        print(f"\nProduct of matched picks' odds_decimal: {product:.4f}")
        print(f"Slip total_odds (pre-boost):             {EXTRACTED['total_odds']}")
        diff_pct = abs(product - EXTRACTED["total_odds"]) / EXTRACTED["total_odds"] * 100
        print(f"Difference: {diff_pct:.1f}%  {'(looks good)' if diff_pct < 10 else '(large gap — submitted odds may differ from placed odds)'}")

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
        print(f"Set confirmed_odds (from picks.odds_decimal) on {len(matched)} pick(s).")

    print("Done.")


if __name__ == "__main__":
    main()
