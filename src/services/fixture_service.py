"""
Fixture caching and management service.

Fetches fixtures from API-Football and stores them locally in the fixtures
table. Provides lookup methods for pick matching and auto-resulting.
"""

import json
import logging
from datetime import datetime, timedelta

import pytz

from src.config import Config
from src.db import get_db
from src.api.api_football import (
    get_fixtures_by_date_range,
    get_fixtures_by_date,
    get_fixture_by_id,
    PRIORITY_LEAGUES,
)

logger = logging.getLogger(__name__)


def fetch_weekend_fixtures():
    """
    Fetch fixtures for the upcoming weekend (Friday to Monday).

    Called by the scheduler on Wednesday evening. Fetches from priority leagues
    to keep within the free tier budget (~3-5 requests per cycle).

    Returns:
        int — number of fixtures cached.
    """
    tz = pytz.timezone(Config.TIMEZONE)
    now = datetime.now(tz)

    # Calculate next Friday to Monday
    days_to_friday = (4 - now.weekday()) % 7
    if days_to_friday == 0 and now.hour >= 22:
        days_to_friday = 7
    friday = (now + timedelta(days=days_to_friday)).date()
    monday = friday + timedelta(days=3)

    start_date = friday.isoformat()
    end_date = monday.isoformat()
    logger.info("Fetching fixtures for %s to %s", start_date, end_date)

    total_cached = 0
    for league_id in PRIORITY_LEAGUES:
        fixtures = get_fixtures_by_date_range(start_date, end_date, league_id=league_id)
        if fixtures:
            cached = _cache_fixtures(fixtures)
            total_cached += cached
            logger.info("Cached %d fixtures for league %d", cached, league_id)

    logger.info("Total fixtures cached: %d", total_cached)
    return total_cached


def _cache_fixtures(api_fixtures):
    """
    Store API-Football fixtures in the local database.

    Uses INSERT OR REPLACE to update existing fixtures (e.g. when scores come in).

    Args:
        api_fixtures: List of fixture dicts from API-Football response.

    Returns:
        int — number of fixtures stored.
    """
    conn = get_db()
    count = 0

    for fixture_data in api_fixtures:
        try:
            fixture = fixture_data.get("fixture", {})
            league = fixture_data.get("league", {})
            teams = fixture_data.get("teams", {})
            goals = fixture_data.get("goals", {})
            score = fixture_data.get("score", {})

            api_id = fixture.get("id")
            if not api_id:
                continue

            # Extract half-time scores
            ht = score.get("halftime", {})
            ht_home = ht.get("home")
            ht_away = ht.get("away")

            conn.execute(
                """INSERT OR REPLACE INTO fixtures
                   (api_id, sport, competition, competition_id,
                    home_team, away_team, kickoff, status,
                    home_score, away_score, ht_home_score, ht_away_score,
                    fetched_at, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    api_id,
                    "football",
                    league.get("name", "Unknown"),
                    league.get("id"),
                    teams.get("home", {}).get("name", "Unknown"),
                    teams.get("away", {}).get("name", "Unknown"),
                    fixture.get("date", ""),
                    fixture.get("status", {}).get("short", "NS"),
                    goals.get("home"),
                    goals.get("away"),
                    ht_home,
                    ht_away,
                    datetime.utcnow().isoformat(),
                    json.dumps(fixture_data),
                ),
            )
            count += 1
        except Exception as e:
            logger.warning("Failed to cache fixture: %s", e)

    conn.commit()
    conn.close()
    return count


def get_upcoming_fixtures(days_ahead=4):
    """
    Get cached fixtures that haven't started yet, within the next N days.

    Returns:
        list of fixture dicts from the local database.
    """
    tz = pytz.timezone(Config.TIMEZONE)
    now = datetime.now(tz)
    cutoff = (now + timedelta(days=days_ahead)).isoformat()

    conn = get_db()
    fixtures = conn.execute(
        "SELECT * FROM fixtures WHERE kickoff > ? AND kickoff < ? "
        "AND status IN ('NS', 'TBD') ORDER BY kickoff",
        (now.isoformat(), cutoff),
    ).fetchall()
    conn.close()
    return [dict(f) for f in fixtures]


def get_completed_fixtures():
    """
    Get cached fixtures that have finished (for auto-resulting).

    Returns fixtures with status FT (full time), AET (after extra time),
    or PEN (penalties).
    """
    conn = get_db()
    fixtures = conn.execute(
        "SELECT * FROM fixtures WHERE status IN ('FT', 'AET', 'PEN') "
        "ORDER BY kickoff DESC"
    ).fetchall()
    conn.close()
    return [dict(f) for f in fixtures]


def get_fixture_by_api_id(api_id):
    """Look up a cached fixture by its API-Football ID."""
    conn = get_db()
    fixture = conn.execute(
        "SELECT * FROM fixtures WHERE api_id = ?", (api_id,)
    ).fetchone()
    conn.close()
    return dict(fixture) if fixture else None


def refresh_fixture(api_id):
    """
    Re-fetch a single fixture from API-Football and update the cache.
    Used to check for score updates during auto-resulting.
    """
    fixture_data = get_fixture_by_id(api_id)
    if fixture_data:
        _cache_fixtures([fixture_data])
        return get_fixture_by_api_id(api_id)
    return None


def refresh_fixtures_by_date(date_str):
    """
    Re-fetch all fixtures for a given date and update the cache.
    Used for kickoff batching — one request covers multiple fixtures.

    Args:
        date_str: Date in YYYY-MM-DD format.

    Returns:
        int — number of fixtures updated.
    """
    fixtures = get_fixtures_by_date(date_str)
    if fixtures:
        return _cache_fixtures(fixtures)
    return 0


def extract_events(raw_json):
    """
    Parse goal and red card events from an API-Football fixture response.

    Args:
        raw_json: JSON string or dict of the API-Football fixture data.

    Returns:
        list of dicts with keys: event_key, event_type, detail, minute, team, player
    """
    if isinstance(raw_json, str):
        try:
            data = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            return []
    else:
        data = raw_json

    events_raw = data.get("events", [])
    if not events_raw:
        return []

    results = []
    for ev in events_raw:
        ev_type = ev.get("type", "")
        detail = ev.get("detail", "")

        # Only goals and red cards
        if ev_type == "Goal":
            event_type = "Goal"
        elif ev_type == "Card" and detail == "Red Card":
            event_type = "RedCard"
        else:
            continue

        minute = ev.get("time", {}).get("elapsed")
        team = ev.get("team", {}).get("name", "")
        player_name = ev.get("player", {}).get("name", "")

        # Build dedup key: "Goal_23_Salah" or "RedCard_68_Rice"
        event_key = f"{event_type}_{minute}_{player_name}"

        results.append({
            "event_key": event_key,
            "event_type": event_type,
            "detail": detail,
            "minute": minute,
            "team": team,
            "player": player_name,
        })

    return results


def get_fixture_list_for_matching():
    """
    Build a concise fixture list string for LLM matching.
    Used as context when the LLM tries to match a pick to a fixture.

    Returns:
        str — formatted list like "1. Arsenal vs Chelsea (EPL, Sat 3pm)\n2. ..."
    """
    fixtures = get_upcoming_fixtures()
    if not fixtures:
        return ""

    lines = []
    for i, f in enumerate(fixtures, 1):
        try:
            kickoff = datetime.fromisoformat(f["kickoff"])
            time_str = kickoff.strftime("%a %H:%M")
        except (ValueError, TypeError):
            time_str = "TBD"
        lines.append(
            f"{i}. {f['home_team']} vs {f['away_team']} "
            f"({f['competition']}, {time_str}) [id:{f['api_id']}]"
        )
    return "\n".join(lines)
