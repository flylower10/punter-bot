from src.db import get_db
from src.services.player_service import get_all_players


def get_player_stats(player_id):
    """
    Calculate stats for a single player.

    Returns dict with: wins, losses, total, win_rate, streak, form
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

    if not results:
        return {
            "wins": 0, "losses": 0, "total": 0,
            "win_rate": 0.0, "streak": "-", "form": "-",
        }

    outcomes = [r["outcome"] for r in results]
    wins = outcomes.count("win")
    losses = outcomes.count("loss")
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0.0

    # Current streak (from most recent)
    streak_count = 0
    streak_type = outcomes[0] if outcomes else None
    for outcome in outcomes:
        if outcome == streak_type:
            streak_count += 1
        else:
            break
    streak_emoji = "\u2705" if streak_type == "win" else "\u274c"
    streak = streak_emoji * streak_count

    # Form: last 10 results (most recent first, displayed left to right)
    form_results = outcomes[:10]
    form = "".join("\u2705" if o == "win" else "\u274c" for o in reversed(form_results))

    return {
        "wins": wins,
        "losses": losses,
        "total": total,
        "win_rate": win_rate,
        "streak": streak,
        "form": form,
    }


def get_leaderboard():
    """
    Get all players ranked by win rate.

    Returns list of dicts with player info + stats.
    """
    players = get_all_players()
    entries = []

    for player in players:
        stats = get_player_stats(player["id"])
        if stats["total"] > 0:
            entries.append({
                "player_id": player["id"],
                "formal_name": player["formal_name"],
                "nickname": player["nickname"],
                **stats,
            })

    # Sort by win rate descending
    entries.sort(key=lambda e: e["win_rate"], reverse=True)
    return entries
