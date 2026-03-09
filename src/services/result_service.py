from datetime import datetime

from src.db import get_db
from src.services.pick_service import get_picks_for_week


def record_result(pick_id, outcome, confirmed_by=""):
    """
    Record a result for a pick.

    Returns the result dict, or None if already recorded.
    """
    conn = get_db()

    # Check if result already exists
    existing = conn.execute(
        "SELECT * FROM results WHERE pick_id = ?", (pick_id,)
    ).fetchone()

    if existing:
        # Update existing result
        conn.execute(
            "UPDATE results SET outcome = ?, confirmed_by = ?, confirmed_at = ? WHERE pick_id = ?",
            (outcome, confirmed_by, datetime.utcnow().isoformat(), pick_id),
        )
    else:
        conn.execute(
            "INSERT INTO results (pick_id, outcome, confirmed_by, confirmed_at) VALUES (?, ?, ?, ?)",
            (pick_id, outcome, confirmed_by, datetime.utcnow().isoformat()),
        )

    conn.commit()
    result = conn.execute(
        "SELECT * FROM results WHERE pick_id = ?", (pick_id,)
    ).fetchone()
    conn.close()
    return dict(result)


def week_has_loss(week_id):
    """Check if any pick in this week has a recorded loss."""
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM results r JOIN picks p ON r.pick_id = p.id "
        "WHERE p.week_id = ? AND r.outcome = 'loss' LIMIT 1",
        (week_id,),
    ).fetchone()
    conn.close()
    return row is not None


def get_consecutive_losses(player_id):
    """
    Count the current consecutive loss streak for a player.

    Looks at results in reverse chronological order, counting losses
    until a win or void is found.
    """
    conn = get_db()
    results = conn.execute(
        "SELECT r.outcome FROM results r "
        "JOIN picks p ON r.pick_id = p.id "
        "WHERE p.player_id = ? AND r.outcome IN ('win', 'loss') "
        "ORDER BY r.confirmed_at DESC",
        (player_id,),
    ).fetchall()
    conn.close()

    streak = 0
    for result in results:
        if result["outcome"] == "loss":
            streak += 1
        else:
            break

    return streak


def get_week_results(week_id):
    """Return all results for a week, joined with pick and player info."""
    conn = get_db()
    results = conn.execute(
        "SELECT r.*, p.description, p.odds_original, p.bet_type, "
        "p.player_id, pl.nickname, pl.formal_name "
        "FROM results r "
        "JOIN picks p ON r.pick_id = p.id "
        "JOIN players pl ON p.player_id = pl.id "
        "WHERE p.week_id = ? "
        "ORDER BY r.confirmed_at",
        (week_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in results]


def all_results_in(week_id):
    """Check if all picks for this week have results."""
    picks = get_picks_for_week(week_id)
    if not picks:
        return False

    conn = get_db()
    pick_ids = [p["id"] for p in picks]
    placeholders = ",".join("?" * len(pick_ids))
    count = conn.execute(
        f"SELECT COUNT(*) FROM results WHERE pick_id IN ({placeholders}) "
        f"AND outcome != 'pending'",
        pick_ids,
    ).fetchone()[0]
    conn.close()

    return count == len(picks)


def override_result(player_id, week_id, outcome, confirmed_by=""):
    """Manually override a result for a player in a given week."""
    conn = get_db()
    pick = conn.execute(
        "SELECT id FROM picks WHERE week_id = ? AND player_id = ?",
        (week_id, player_id),
    ).fetchone()
    conn.close()

    if not pick:
        return None

    return record_result(pick["id"], outcome, confirmed_by)
