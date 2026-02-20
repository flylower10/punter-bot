from datetime import datetime

from src.db import get_db
from src.services.player_service import get_all_players
from src.services.week_service import is_past_deadline


def submit_pick(player_id, week_id, description, odds_decimal, odds_original, bet_type):
    """
    Store a pick for a player in a given week.

    Uses INSERT OR REPLACE so re-submissions update the existing pick.
    Returns (pick_dict, is_update, changed, previous_description).
    previous_description: the old pick text when it's an update, else None.
    """
    conn = get_db()

    # Check if this player already has a pick for this week
    existing = conn.execute(
        "SELECT * FROM picks WHERE week_id = ? AND player_id = ?",
        (week_id, player_id),
    ).fetchone()

    is_late = 1 if is_past_deadline() else 0
    previous_description = None

    if existing:
        existing = dict(existing)
        previous_description = existing["description"]
        changed = (
            existing["description"] != description
            or str(existing["odds_original"]) != str(odds_original)
            or float(existing["odds_decimal"]) != float(odds_decimal)
            or existing["bet_type"] != bet_type
        )
        conn.execute(
            "UPDATE picks SET description = ?, odds_decimal = ?, odds_original = ?, "
            "bet_type = ?, submitted_at = ?, is_late = ? "
            "WHERE week_id = ? AND player_id = ?",
            (description, odds_decimal, odds_original, bet_type,
             datetime.utcnow().isoformat(), is_late, week_id, player_id),
        )
        is_update = True
    else:
        conn.execute(
            "INSERT INTO picks (week_id, player_id, description, odds_decimal, "
            "odds_original, bet_type, submitted_at, is_late) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (week_id, player_id, description, odds_decimal, odds_original,
             bet_type, datetime.utcnow().isoformat(), is_late),
        )
        is_update = False
        changed = True

    conn.commit()

    pick = conn.execute(
        "SELECT * FROM picks WHERE week_id = ? AND player_id = ?",
        (week_id, player_id),
    ).fetchone()
    conn.close()

    return dict(pick), is_update, changed, previous_description


def get_picks_for_week(week_id):
    """Return all picks for a given week, joined with player info and result if available."""
    conn = get_db()
    picks = conn.execute(
        "SELECT p.*, pl.nickname, pl.formal_name, pl.emoji, r.outcome as result_outcome "
        "FROM picks p "
        "JOIN players pl ON p.player_id = pl.id "
        "LEFT JOIN results r ON r.pick_id = p.id "
        "WHERE p.week_id = ? ORDER BY p.submitted_at",
        (week_id,),
    ).fetchall()
    conn.close()
    return [dict(p) for p in picks]


def get_missing_players(week_id):
    """Return players who haven't submitted a pick for this week."""
    conn = get_db()
    all_players = get_all_players()
    submitted_ids = set()

    picks = conn.execute(
        "SELECT player_id FROM picks WHERE week_id = ?", (week_id,)
    ).fetchall()
    conn.close()

    for pick in picks:
        submitted_ids.add(pick["player_id"])

    return [p for p in all_players if p["id"] not in submitted_ids]


def all_picks_in(week_id):
    """Check if all 6 players have submitted picks."""
    return len(get_missing_players(week_id)) == 0


def get_player_pick(week_id, player_id):
    """Return a specific player's pick for a week, or None."""
    conn = get_db()
    pick = conn.execute(
        "SELECT * FROM picks WHERE week_id = ? AND player_id = ?",
        (week_id, player_id),
    ).fetchone()
    conn.close()
    return dict(pick) if pick else None
