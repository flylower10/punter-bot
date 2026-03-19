"""
Auto-resulting service.

When matched fixtures complete, automatically records win/loss based on
score data. Handles win, BTTS, over/under, and HT/FT bet types.

Unmatched picks (no api_fixture_id) remain pending for manual resulting.
"""

import logging
import re

from src.db import get_db
from src.services.fixture_service import get_fixture_by_api_id, refresh_fixture
from src.services.pick_service import get_matched_picks_for_week
from src.services.result_service import record_result, get_consecutive_losses, all_results_in
from src.services.week_service import complete_week
from src.services.penalty_service import suggest_penalty
from src.services.stats_service import get_leaderboard
from src.services.rotation_service import get_next_placer, add_to_penalty_queue
import src.butler as butler

logger = logging.getLogger(__name__)

# Fixture statuses that indicate a completed match
COMPLETED_STATUSES = {"FT", "AET", "PEN"}


def auto_result_week(week_id):
    """
    Check all matched picks for a week and auto-result any whose fixtures
    have completed.

    Returns:
        list of announcement strings to send to the group, or empty list.
    """
    picks = get_matched_picks_for_week(week_id)
    if not picks:
        return []

    announcements = []

    for pick in picks:
        # Skip picks that already have a result
        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM results WHERE pick_id = ?", (pick["id"],)
        ).fetchone()
        conn.close()
        if existing:
            continue

        fixture_id = pick["api_fixture_id"]
        if not fixture_id:
            continue

        # Refresh the fixture to get latest score
        pick_sport = pick.get("sport")
        fixture = refresh_fixture(fixture_id, sport=pick_sport)
        if not fixture:
            fixture = get_fixture_by_api_id(fixture_id, sport=pick_sport)
        if not fixture:
            continue

        # Only process completed fixtures
        if fixture.get("status") not in COMPLETED_STATUSES:
            continue

        # Determine outcome
        outcome = _evaluate_pick(pick, fixture)
        if not outcome:
            logger.warning("Could not evaluate pick %d against fixture %d", pick["id"], fixture_id)
            continue

        # Record the result
        score_str = f"{fixture.get('home_score', '?')}-{fixture.get('away_score', '?')}"
        result = record_result(pick["id"], outcome, confirmed_by="auto")

        # Update result with score
        conn = get_db()
        conn.execute(
            "UPDATE results SET score = ? WHERE pick_id = ?",
            (score_str, pick["id"]),
        )
        conn.commit()
        conn.close()

        # Build announcement
        player = {"formal_name": pick["formal_name"], "nickname": pick["nickname"],
                   "emoji": pick.get("emoji", ""), "id": pick["player_id"]}

        streak = get_consecutive_losses(pick["player_id"])
        streak_str = f"{streak}L" if streak > 0 and outcome == "loss" else None

        announcement = butler.result_announced(
            player, pick["description"], pick["odds_original"], outcome,
            streak=streak_str,
        )

        # Check for penalties
        penalty_thresholds = {3: "streak_3", 5: "streak_5", 7: "streak_7", 10: "streak_10"}
        penalty_amounts = {3: 0, 5: 50, 7: 100, 10: 200}
        if streak in penalty_thresholds:
            suggest_penalty(pick["player_id"], week_id, penalty_thresholds[streak])
            announcement += "\n\n" + butler.penalty_suggested(
                player, streak, penalty_thresholds[streak], penalty_amounts[streak]
            )

        announcements.append(announcement)
        logger.info("Auto-resulted: %s — %s (%s)", pick["formal_name"], outcome, score_str)

    # Check if all results are now in
    if announcements and all_results_in(week_id):
        from src.services.result_service import get_week_results
        results = get_week_results(week_id)
        complete_week(week_id)
        losers = [r for r in results if r["outcome"] == "loss"]
        if len(losers) == 1:
            add_to_penalty_queue(losers[0]["player_id"], "sole loser", week_id, front=True)
        leaderboard = get_leaderboard()
        next_placer = get_next_placer()

        week = get_db().execute("SELECT week_number FROM weeks WHERE id = ?", (week_id,)).fetchone()
        week_number = week["week_number"] if week else "?"

        announcements.append(
            butler.week_complete_summary(
                results, week_number, leaderboard or [], next_placer or {}
            )
        )

    return announcements


def auto_result_fixture(api_fixture_id, week_id):
    """
    Auto-result the single pick linked to a specific fixture in a given week.
    Called by the match monitor when a fixture completes.

    Returns:
        list of announcement strings (0 or 1 items, plus optional week summary).
    """
    conn = get_db()
    pick = conn.execute(
        "SELECT p.*, pl.nickname, pl.formal_name, pl.emoji, pl.id as player_id "
        "FROM picks p "
        "JOIN players pl ON p.player_id = pl.id "
        "WHERE p.week_id = ? AND p.api_fixture_id = ?",
        (week_id, api_fixture_id),
    ).fetchone()

    if not pick:
        conn.close()
        return []

    pick = dict(pick)

    # Skip if already resulted
    existing = conn.execute(
        "SELECT id FROM results WHERE pick_id = ?", (pick["id"],)
    ).fetchone()
    conn.close()
    if existing:
        return []

    fixture = get_fixture_by_api_id(api_fixture_id, sport=pick.get("sport"))
    if not fixture:
        return []

    if fixture.get("status") not in COMPLETED_STATUSES:
        return []

    outcome = _evaluate_pick(pick, fixture)
    if not outcome:
        logger.warning("Could not evaluate pick %d against fixture %d", pick["id"], api_fixture_id)
        return []

    # Record the result
    score_str = f"{fixture.get('home_score', '?')}-{fixture.get('away_score', '?')}"
    record_result(pick["id"], outcome, confirmed_by="auto")

    conn = get_db()
    conn.execute(
        "UPDATE results SET score = ? WHERE pick_id = ?",
        (score_str, pick["id"]),
    )
    conn.commit()
    conn.close()

    # Build announcement
    player = {"formal_name": pick["formal_name"], "nickname": pick["nickname"],
               "emoji": pick.get("emoji", ""), "id": pick["player_id"]}

    streak = get_consecutive_losses(pick["player_id"])
    streak_str = f"{streak}L" if streak > 0 and outcome == "loss" else None

    announcement = butler.result_announced(
        player, pick["description"], pick["odds_original"], outcome,
        streak=streak_str,
    )

    # Check for penalties
    penalty_thresholds = {3: "streak_3", 5: "streak_5", 7: "streak_7", 10: "streak_10"}
    penalty_amounts = {3: 0, 5: 50, 7: 100, 10: 200}
    if streak in penalty_thresholds:
        suggest_penalty(pick["player_id"], week_id, penalty_thresholds[streak])
        announcement += "\n\n" + butler.penalty_suggested(
            player, streak, penalty_thresholds[streak], penalty_amounts[streak]
        )

    announcements = [announcement]
    logger.info("Auto-resulted fixture %d: %s — %s (%s)",
                api_fixture_id, pick["formal_name"], outcome, score_str)

    # Check if all results are now in
    if all_results_in(week_id):
        from src.services.result_service import get_week_results
        results = get_week_results(week_id)
        complete_week(week_id)
        losers = [r for r in results if r["outcome"] == "loss"]
        if len(losers) == 1:
            add_to_penalty_queue(losers[0]["player_id"], "sole loser", week_id, front=True)
        leaderboard = get_leaderboard()
        next_placer = get_next_placer()

        conn = get_db()
        week = conn.execute("SELECT week_number FROM weeks WHERE id = ?", (week_id,)).fetchone()
        conn.close()
        week_number = week["week_number"] if week else "?"

        announcements.append(
            butler.week_complete_summary(
                results, week_number, leaderboard or [], next_placer or {}
            )
        )

    return announcements


def _evaluate_pick(pick, fixture):
    """
    Determine win/loss for a pick based on the fixture score.

    Args:
        pick: Pick dict with bet_type, description
        fixture: Fixture dict with scores

    Returns:
        "win", "loss", or None if cannot evaluate.
    """
    bet_type = pick.get("bet_type", "win")
    sport = fixture.get("sport", "football")
    home_score = fixture.get("home_score")
    away_score = fixture.get("away_score")

    if home_score is None or away_score is None:
        return None

    home_team = fixture.get("home_team", "").lower()
    away_team = fixture.get("away_team", "").lower()

    if bet_type == "win":
        return _evaluate_win(pick, home_team, away_team, home_score, away_score, sport)
    elif bet_type == "btts":
        # BTTS is football-specific (both teams to score)
        if sport != "football":
            return None
        return _evaluate_btts(home_score, away_score)
    elif bet_type == "over_under":
        return _evaluate_over_under(pick, home_score, away_score)
    elif bet_type == "ht_ft":
        # HT/FT is football-specific
        if sport != "football":
            return None
        return _evaluate_ht_ft(pick, fixture, sport)
    elif bet_type == "handicap":
        return _evaluate_handicap(pick, home_team, away_team, home_score, away_score, sport)
    else:
        # Default to win evaluation for unknown bet types
        return _evaluate_win(pick, home_team, away_team, home_score, away_score, sport)


def _evaluate_win(pick, home_team, away_team, home_score, away_score, sport="football"):
    """
    Evaluate a win/match result pick.

    Determines which team was picked, then checks if they won.
    """
    description = pick.get("description", "").lower()

    # Try to figure out which team was picked (with alias fallback)
    picked_home = _team_in_text_with_aliases(home_team, description, sport)
    picked_away = _team_in_text_with_aliases(away_team, description, sport)

    # Check for draw pick
    if re.search(r"\bdraw\b", description, re.IGNORECASE):
        return "win" if home_score == away_score else "loss"

    if picked_home and not picked_away:
        return "win" if home_score > away_score else "loss"
    elif picked_away and not picked_home:
        return "win" if away_score > home_score else "loss"
    elif picked_home and picked_away:
        # Both teams mentioned — likely "X to beat Y" format
        # The first team mentioned is usually the pick
        home_pos = description.find(home_team[:4].lower()) if len(home_team) >= 4 else -1
        away_pos = description.find(away_team[:4].lower()) if len(away_team) >= 4 else -1
        if home_pos >= 0 and (away_pos < 0 or home_pos < away_pos):
            return "win" if home_score > away_score else "loss"
        else:
            return "win" if away_score > home_score else "loss"

    # Can't determine which team — skip
    return None


def _evaluate_btts(home_score, away_score):
    """Both Teams To Score: win if both teams scored at least 1."""
    return "win" if home_score > 0 and away_score > 0 else "loss"


def _evaluate_over_under(pick, home_score, away_score):
    """Over/Under: check if total goals is over or under the target."""
    description = pick.get("description", "")
    total_goals = home_score + away_score

    # Extract the target (e.g. "over 2.5" or "under 1.5")
    over_match = re.search(r"over\s+(\d+\.?\d*)", description, re.IGNORECASE)
    under_match = re.search(r"under\s+(\d+\.?\d*)", description, re.IGNORECASE)

    if over_match:
        target = float(over_match.group(1))
        return "win" if total_goals > target else "loss"
    elif under_match:
        target = float(under_match.group(1))
        return "win" if total_goals < target else "loss"

    return None


def _evaluate_ht_ft(pick, fixture, sport="football"):
    """
    Half-Time/Full-Time: check if the HT and FT results match the pick.

    Common format: "Liverpool HT/FT" means Liverpool leading at HT and winning at FT.
    """
    ht_home = fixture.get("ht_home_score")
    ht_away = fixture.get("ht_away_score")
    ft_home = fixture.get("home_score")
    ft_away = fixture.get("away_score")

    if any(v is None for v in (ht_home, ht_away, ft_home, ft_away)):
        return None

    description = pick.get("description", "").lower()
    home_team = fixture.get("home_team", "").lower()
    away_team = fixture.get("away_team", "").lower()

    picked_home = _team_in_text_with_aliases(home_team, description, sport)
    picked_away = _team_in_text_with_aliases(away_team, description, sport)

    if picked_home:
        # Picked team leading at HT AND winning at FT
        ht_winning = ht_home > ht_away
        ft_winning = ft_home > ft_away
        return "win" if ht_winning and ft_winning else "loss"
    elif picked_away:
        ht_winning = ht_away > ht_home
        ft_winning = ft_away > ft_home
        return "win" if ht_winning and ft_winning else "loss"

    return None


def _evaluate_handicap(pick, home_team, away_team, home_score, away_score, sport="football"):
    """
    Evaluate a handicap pick. Works for all sports.

    Parses the handicap value from the description and applies it.
    """
    description = pick.get("description", "")

    # Extract handicap value (e.g. "-13", "+7.5")
    handicap_match = re.search(r"([+-])\s*(\d+\.?\d*)", description)
    if not handicap_match:
        return None

    sign = handicap_match.group(1)
    value = float(handicap_match.group(2))
    handicap = value if sign == "+" else -value

    # Determine which team has the handicap
    picked_home = _team_in_text_with_aliases(home_team, description, sport)
    picked_away = _team_in_text_with_aliases(away_team, description, sport)

    if picked_home and not picked_away:
        adjusted = (home_score + handicap) - away_score
    elif picked_away and not picked_home:
        adjusted = (away_score + handicap) - home_score
    else:
        return None

    if adjusted > 0:
        return "win"
    elif adjusted < 0:
        return "loss"
    return None  # Dead heat / push — can't determine


def _team_in_text(team_name, text):
    """Check if a team name (or a significant prefix) appears in text."""
    if not team_name or not text:
        return False
    team_lower = team_name.lower()
    text_lower = text.lower()

    # Direct substring match
    if team_lower in text_lower:
        return True

    # Try first word of team name (e.g. "Arsenal" from "Arsenal FC")
    first_word = team_lower.split()[0] if team_lower else ""
    if first_word and len(first_word) >= 4 and first_word in text_lower:
        return True

    # Try without common suffixes (football + rugby + other sports)
    for suffix in (" fc", " city", " united", " town",
                   " rugby", " rfc",
                   " sc", " cf"):
        if team_lower.endswith(suffix):
            base = team_lower[:-len(suffix)]
            if base and len(base) >= 4 and base in text_lower:
                return True

    return False


def _team_in_text_with_aliases(team_name, text, sport="football"):
    """Check if a team appears in text, using alias table as fallback."""
    if _team_in_text(team_name, text):
        return True

    # Try resolving chunks of the description through the alias table
    from src.services.match_service import _resolve_alias

    # Strip odds from end (fractional like "8/15" or decimal like "1.53")
    cleaned = re.sub(r'\s+\d+/\d+\s*$', '', text)
    cleaned = re.sub(r'\s+\d+\.\d+\s*$', '', cleaned)

    # Split on common bet phrases to isolate team name chunks
    chunks = re.split(
        r'\b(?:to win|to beat|to draw|draw|ht/ft|over|under)\b',
        cleaned, flags=re.IGNORECASE
    )

    team_lower = team_name.lower()
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk or len(chunk) < 3:
            continue
        canonical = _resolve_alias(chunk, sport)
        if canonical.lower() == team_lower:
            return True

    return False
