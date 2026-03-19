from datetime import datetime

from src.db import get_db

# Penalty amounts by type
PENALTY_AMOUNTS = {
    "late": 0,
    "streak_3": 0,      # pay for next week's bet (no vault)
    "streak_5": 50,
    "streak_7": 100,
    "streak_10": 200,
}

# Maps consecutive loss count → penalty type string
PENALTY_THRESHOLDS = {3: "streak_3", 5: "streak_5", 7: "streak_7", 10: "streak_10"}


def suggest_penalty(player_id, week_id, penalty_type):
    """
    Create a pending penalty suggestion for Ed to confirm.

    Returns the penalty dict.
    """
    amount = PENALTY_AMOUNTS.get(penalty_type, 0)
    conn = get_db()

    # Check if this exact penalty already exists for this player/week/type
    existing = conn.execute(
        "SELECT * FROM penalties WHERE player_id = ? AND week_id = ? AND type = ?",
        (player_id, week_id, penalty_type),
    ).fetchone()

    if existing:
        conn.close()
        return dict(existing)

    conn.execute(
        "INSERT INTO penalties (player_id, week_id, type, amount, status, created_at) "
        "VALUES (?, ?, ?, ?, 'suggested', ?)",
        (player_id, week_id, penalty_type, amount, datetime.utcnow().isoformat()),
    )
    conn.commit()

    penalty = conn.execute(
        "SELECT * FROM penalties WHERE player_id = ? AND week_id = ? AND type = ?",
        (player_id, week_id, penalty_type),
    ).fetchone()
    conn.close()
    return dict(penalty)


def confirm_penalty(penalty_id, confirmed_by=""):
    """
    Confirm a pending penalty and add to vault if applicable.

    Returns (penalty_dict, vault_total) or None if not found.
    """
    conn = get_db()

    penalty = conn.execute(
        "SELECT * FROM penalties WHERE id = ? AND status = 'suggested'",
        (penalty_id,),
    ).fetchone()

    if not penalty:
        conn.close()
        return None

    conn.execute(
        "UPDATE penalties SET status = 'confirmed', confirmed_by = ? WHERE id = ?",
        (confirmed_by, penalty_id),
    )

    # Add to vault if there's an amount
    if penalty["amount"] > 0:
        conn.execute(
            "INSERT INTO vault (penalty_id, amount, description, created_at) "
            "VALUES (?, ?, ?, ?)",
            (penalty_id, penalty["amount"],
             f"Penalty: {penalty['type']} for player {penalty['player_id']}",
             datetime.utcnow().isoformat()),
        )

    conn.commit()

    vault_total = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM vault").fetchone()[0]
    penalty = conn.execute("SELECT * FROM penalties WHERE id = ?", (penalty_id,)).fetchone()
    conn.close()

    return dict(penalty), vault_total


def get_pending_penalties():
    """Return all unconfirmed penalties with player info."""
    conn = get_db()
    penalties = conn.execute(
        "SELECT p.*, pl.nickname, pl.formal_name FROM penalties p "
        "JOIN players pl ON p.player_id = pl.id "
        "WHERE p.status = 'suggested' ORDER BY p.created_at",
    ).fetchall()
    conn.close()
    return [dict(p) for p in penalties]



def get_pending_penalty_for_player_id(player_id):
    """Return the most recent pending penalty for a player by player ID."""
    conn = get_db()
    penalty = conn.execute(
        "SELECT p.* FROM penalties p "
        "WHERE p.status = 'suggested' AND p.player_id = ? "
        "ORDER BY p.created_at DESC LIMIT 1",
        (player_id,),
    ).fetchone()
    conn.close()
    return dict(penalty) if penalty else None


def get_vault_total():
    """Return the total vault balance."""
    conn = get_db()
    total = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM vault").fetchone()[0]
    conn.close()
    return total
