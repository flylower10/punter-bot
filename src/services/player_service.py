from src.db import get_db


def lookup_player(sender_phone="", sender_name=""):
    """
    Match a message sender to a player record.

    Tries phone number first (reliable), then falls back to matching
    nickname or name (case-insensitive).

    Returns a dict with player data, or None if no match.
    """
    conn = get_db()

    # Try phone number match first
    if sender_phone:
        player = conn.execute(
            "SELECT * FROM players WHERE phone = ?", (sender_phone,)
        ).fetchone()
        if player:
            conn.close()
            return dict(player)

    # Fall back to nickname/name match
    if sender_name:
        name_lower = sender_name.strip().lower()
        players = conn.execute("SELECT * FROM players").fetchall()
        conn.close()

        for player in players:
            if (
                player["nickname"].lower() == name_lower
                or player["name"].lower() == name_lower
            ):
                return dict(player)

    conn.close()
    return None


def get_all_players():
    """Return all players ordered by rotation position."""
    conn = get_db()
    players = conn.execute(
        "SELECT * FROM players ORDER BY rotation_position"
    ).fetchall()
    conn.close()
    return [dict(p) for p in players]


def get_player_by_id(player_id):
    """Return a single player by ID."""
    conn = get_db()
    player = conn.execute(
        "SELECT * FROM players WHERE id = ?", (player_id,)
    ).fetchone()
    conn.close()
    return dict(player) if player else None


def is_admin(sender_phone):
    """Check if the sender is Ed (admin)."""
    from src.config import Config
    return sender_phone and sender_phone == Config.ADMIN_PHONE


def is_superadmin(sender_phone):
    """Check if the sender is the bot developer (superadmin)."""
    from src.config import Config
    return sender_phone and sender_phone == Config.SUPERADMIN_PHONE


def get_emoji_to_player_map():
    """
    Return a dict mapping emoji -> player dict for players who have emoji set.
    Used for parsing cumulative pick messages (emoji + pick per line).
    Supports multiple emojis per player (comma-separated, e.g. "🍋,🍋🍋🍋").
    """
    conn = get_db()
    players = conn.execute(
        "SELECT * FROM players WHERE emoji IS NOT NULL AND emoji != ''"
    ).fetchall()
    conn.close()

    result = {}
    for p in players:
        emoji_str = (p["emoji"] or "").strip()
        for emoji in emoji_str.split(","):
            emoji = emoji.strip()
            if emoji:
                result[emoji] = dict(p)
    return result


def lookup_player_by_emoji(emoji):
    """Return player dict for the given emoji, or None."""
    return get_emoji_to_player_map().get((emoji or "").strip())
