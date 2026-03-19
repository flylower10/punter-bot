import logging
from datetime import datetime

from src.db import get_db
from src.services.player_service import get_all_players

logger = logging.getLogger(__name__)


def submit_pick(player_id, week_id, description, odds_decimal, odds_original, bet_type, sport=None):
    """
    Store a pick for a player in a given week.

    Uses INSERT OR REPLACE so re-submissions update the existing pick.
    Attempts to enrich the pick by matching it to a cached fixture (best-effort).
    Returns (pick_dict, is_update, changed, previous_description).
    previous_description: the old pick text when it's an update, else None.
    """
    conn = get_db()

    # Check if this player already has a pick for this week
    existing = conn.execute(
        "SELECT * FROM picks WHERE week_id = ? AND player_id = ?",
        (week_id, player_id),
    ).fetchone()

    previous_description = None

    # Detect sport from pick text if not provided by caller
    if not sport:
        from src.parsers.message_parser import detect_sport
        sport = detect_sport(description)

    # Best-effort enrichment — never block pick submission
    enrichment = _try_enrich(description, bet_type, sport)

    # Use enrichment sport if available, otherwise fall back to detected sport
    pick_sport = enrichment.get("sport") or sport

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
            "bet_type = ?, submitted_at = ?, "
            "sport = ?, api_fixture_id = ?, market_price = ? "
            "WHERE week_id = ? AND player_id = ?",
            (description, odds_decimal, odds_original, bet_type,
             datetime.utcnow().isoformat(),
             pick_sport, enrichment.get("api_fixture_id"), enrichment.get("market_price"),
             week_id, player_id),
        )
        is_update = True
    else:
        conn.execute(
            "INSERT INTO picks (week_id, player_id, description, odds_decimal, "
            "odds_original, bet_type, submitted_at, "
            "sport, api_fixture_id, market_price) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (week_id, player_id, description, odds_decimal, odds_original,
             bet_type, datetime.utcnow().isoformat(),
             pick_sport, enrichment.get("api_fixture_id"), enrichment.get("market_price")),
        )
        is_update = False
        changed = True

    conn.commit()

    pick = conn.execute(
        "SELECT * FROM picks WHERE week_id = ? AND player_id = ?",
        (week_id, player_id),
    ).fetchone()
    conn.close()

    # Schedule match monitor if pick was matched to a fixture
    _try_schedule_monitor(enrichment, week_id)

    return dict(pick), is_update, changed, previous_description


# Sports that have no fixture API — odds-only enrichment
ODDS_ONLY_SPORTS = {"tennis", "golf", "boxing", "gaa_football", "gaa_hurling", "formula1"}


def _try_enrich(description, bet_type, sport="football", include_started=False):
    """
    Attempt to match a pick to a fixture and look up market odds.
    Returns empty dict on any failure — enrichment is best-effort.

    For odds-only sports (tennis, golf, boxing), skips fixture matching
    and queries The Odds API directly for market prices.
    """
    if sport in ODDS_ONLY_SPORTS:
        return _try_enrich_odds_only(description, sport)

    try:
        from src.services.match_service import match_pick
        result = match_pick(description, bet_type, sport=sport, include_started=include_started)

        # Cross-sport fallback: if the default sport found no match, search all fixtures
        if not result and sport == "football":
            result = match_pick(description, bet_type, sport=None, include_started=include_started)
            if result:
                logger.info("Cross-sport fallback matched: %s → %s (%s)",
                            description[:40], result.get("event_name", "?"), result.get("sport", "?"))

        if result:
            logger.info("Enriched pick: %s → %s", description[:40], result.get("event_name", "?"))
            # Try to get market price from The Odds API
            enriched_sport = result.get("sport") or sport
            try:
                from src.api.odds_api import get_best_odds_for_selection
                from src.services.match_service import _extract_team_names
                teams = _extract_team_names(description)
                if teams and result.get("event_name"):
                    price = get_best_odds_for_selection(
                        result["event_name"], teams[0],
                        competition=result.get("competition"),
                        sport=enriched_sport,
                    )
                    if price:
                        result["market_price"] = price
                        logger.info("Market price: %s @ %.2f", teams[0], price)
            except Exception as e:
                logger.warning("Market price lookup failed (non-blocking): %s", e)
            return result
    except Exception as e:
        logger.warning("Enrichment failed (non-blocking): %s", e)
    return {}


def _try_enrich_odds_only(description, sport):
    """
    Odds-only enrichment for sports without fixture APIs (tennis, golf, boxing).

    Queries The Odds API directly for market prices without requiring a fixture match.
    Returns enrichment dict with sport and market_price, or empty dict.
    """
    try:
        from src.api.odds_api import get_best_odds_for_selection
        from src.services.match_service import _extract_team_names

        teams = _extract_team_names(description)
        if not teams:
            return {"sport": sport}

        # For odds-only sports, search without an event_name — use the team/player name
        # as the event name since we don't have fixture data
        price = get_best_odds_for_selection(
            teams[0], teams[0], sport=sport,
        )
        result = {"sport": sport}
        if price:
            result["market_price"] = price
            logger.info("Odds-only price for %s: %s @ %.2f", sport, teams[0], price)
        return result
    except Exception as e:
        logger.warning("Odds-only enrichment failed (non-blocking): %s", e)
        return {"sport": sport}


def _try_schedule_monitor(enrichment, week_id):
    """Schedule a match monitor for this pick's fixture, if matched."""
    api_fixture_id = enrichment.get("api_fixture_id")
    if not api_fixture_id:
        return
    sport = enrichment.get("sport")
    try:
        from src.services.fixture_service import get_fixture_by_api_id
        fixture = get_fixture_by_api_id(api_fixture_id, sport=sport)
        if fixture and fixture.get("kickoff"):
            from src.services.scheduler import schedule_match_monitor
            schedule_match_monitor(api_fixture_id, fixture["kickoff"], week_id, sport=sport)
    except Exception as e:
        logger.warning("Failed to schedule match monitor (non-blocking): %s", e)


def re_enrich_unmatched_picks(week_id):
    """
    Re-try enrichment for picks that haven't been matched to a fixture yet.

    Called after new fixtures are fetched — picks submitted before the fixture
    was cached get a second chance at matching. Also schedules match monitors
    for any newly matched picks.

    Returns:
        int — number of picks enriched.
    """
    conn = get_db()
    unmatched = conn.execute(
        "SELECT id, description, bet_type, sport FROM picks "
        "WHERE week_id = ? AND api_fixture_id IS NULL",
        (week_id,),
    ).fetchall()
    conn.close()

    if not unmatched:
        return 0

    enriched = 0
    for pick in unmatched:
        enrichment = _try_enrich(pick["description"], pick["bet_type"],
                                 sport=pick["sport"] or "football", include_started=True)
        if enrichment.get("api_fixture_id"):
            conn = get_db()
            conn.execute(
                "UPDATE picks SET sport = ?, api_fixture_id = ?, market_price = ? "
                "WHERE id = ?",
                (enrichment.get("sport"),
                 enrichment.get("api_fixture_id"), enrichment.get("market_price"),
                 pick["id"]),
            )
            conn.commit()
            conn.close()
            _try_schedule_monitor(enrichment, week_id)
            enriched += 1
            logger.info("Re-enriched pick %d: %s → %s",
                        pick["id"], pick["description"][:40],
                        enrichment.get("event_name", "?"))

    return enriched


def update_pick_market_price(pick_id, market_price):
    """Update the market_price on a pick (from The Odds API)."""
    conn = get_db()
    conn.execute(
        "UPDATE picks SET market_price = ? WHERE id = ?",
        (market_price, pick_id),
    )
    conn.commit()
    conn.close()


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


def get_picks_for_week_by_kickoff(week_id):
    """Return all picks for a week, ordered by fixture kickoff time (NULLs last)."""
    conn = get_db()
    picks = conn.execute(
        "SELECT p.*, pl.nickname, pl.formal_name, pl.emoji, "
        "r.outcome as result_outcome, "
        "f.kickoff, f.home_team, f.away_team, f.status as fixture_status "
        "FROM picks p "
        "JOIN players pl ON p.player_id = pl.id "
        "LEFT JOIN results r ON r.pick_id = p.id "
        "LEFT JOIN fixtures f ON f.api_id = p.api_fixture_id AND f.sport = p.sport "
        "WHERE p.week_id = ? "
        "ORDER BY f.kickoff IS NULL, f.kickoff, p.submitted_at",
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


def get_matched_picks_for_week(week_id):
    """Return picks that have been matched to a fixture (have api_fixture_id)."""
    conn = get_db()
    picks = conn.execute(
        "SELECT p.*, pl.nickname, pl.formal_name, pl.emoji "
        "FROM picks p "
        "JOIN players pl ON p.player_id = pl.id "
        "WHERE p.week_id = ? AND p.api_fixture_id IS NOT NULL "
        "ORDER BY p.submitted_at",
        (week_id,),
    ).fetchall()
    conn.close()
    return [dict(p) for p in picks]
