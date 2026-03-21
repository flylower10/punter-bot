"""
Pick-to-fixture matching service.

Two-tier matching approach:
  1. Exact alias match — look up team name in team_aliases table
  2. Fuzzy string match — difflib against cached fixture team names

Enrichment is best-effort. If matching fails, the pick is stored without
enrichment. Never blocks pick submission.
"""

import logging
import re
from difflib import SequenceMatcher

from src.db import get_db
from src.services.fixture_service import get_upcoming_fixtures

logger = logging.getLogger(__name__)

# Minimum similarity score for fuzzy matching (0-1)
FUZZY_THRESHOLD = 0.8


def match_pick(description, bet_type="win", sport="football", include_started=False):
    """
    Try to match a pick description to a cached fixture.

    Args:
        description: The raw pick text (e.g. "Liverpool 2/1", "Arsenal to beat Chelsea")
        bet_type: The detected bet type (win, btts, over_under, etc.)
        sport: The detected sport (e.g. "football", "rugby", "nfl")
        include_started: If True, also match against in-play/finished fixtures
            (used by re-enrichment for picks submitted before kickoff).

    Returns:
        dict with enrichment data, or None if no match found:
        {
            "sport": "football",
            "competition": "Premier League",
            "event_name": "Arsenal vs Chelsea",
            "market_type": "win",
            "api_fixture_id": 12345,
        }
    """
    if not description:
        return None

    # Extract team name(s) from the pick text
    team_names = _extract_team_names(description)
    if not team_names:
        return None

    fixtures = get_upcoming_fixtures(sport=sport, include_started=include_started)
    if not fixtures:
        logger.info("No cached fixtures — skipping match")
        return None

    # Tier 1: Exact alias match
    result = _match_by_alias(team_names, fixtures, sport=sport)
    if result:
        logger.info("Tier 1 alias match: %s → %s", description[:50], result["event_name"])
        result["market_type"] = bet_type
        return result

    # Tier 2: Fuzzy string match
    result = _match_by_fuzzy(team_names, fixtures, sport=sport)
    if result:
        logger.info("Tier 2 fuzzy match: %s → %s", description[:50], result["event_name"])
        result["market_type"] = bet_type
        return result

    logger.info("No match found for: %s", description[:50])
    return None


def _extract_team_names(description):
    """
    Extract team name(s) from pick text.

    Handles formats like:
    - "Liverpool 2/1"
    - "Arsenal to beat Chelsea"
    - "Man Utd BTTS 6/4"
    - "Liverpool/Arsenal over 2.5"

    Returns list of extracted team name strings (1 or 2).
    """
    text = description.strip()

    # Remove odds (fractional, decimal, evens)
    text = re.sub(r"\b\d+/\d+\b", "", text)
    text = re.sub(r"\b\d+\.\d{1,2}\b", "", text)
    text = re.sub(r"\bevens?\b", "", text, flags=re.IGNORECASE)

    # Remove bet type keywords
    text = re.sub(
        r"\b(btts|over|under|ht[/_]?ft|handicap|to\s+win|to\s+beat|"
        r"both\s+teams\s+to\s+score|draw|no\s+draw|"
        r"cards?|bookings?|corners?|shots?|clean\s+sheet|anytime|scorer?|"
        r"fouls?|offsides?|throw[\s-]ins?)\b",
        " ", text, flags=re.IGNORECASE,
    )

    # Remove score targets (e.g. "2.5", "1.5 goals")
    text = re.sub(r"\b\d+\.?\d*\s*goals?\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+\.5\b", "", text)

    # Split on common separators: vs, v, /, @, +
    parts = re.split(r"\s+(?:vs?\.?|@)\s+|\s*/\s*|\s+\+\s+", text, flags=re.IGNORECASE)

    # Clean up each part
    names = []
    for part in parts:
        cleaned = part.strip().strip(".,;:!?()").strip()
        # Must have at least 2 chars and look like a team name (has letters)
        if cleaned and len(cleaned) >= 2 and re.search(r"[a-zA-Z]", cleaned):
            names.append(cleaned)

    return names[:2]  # Max 2 teams


def _resolve_alias(name, sport="football"):
    """
    Look up a team name in the aliases table, optionally filtered by sport.

    Tries sport-specific alias first, then falls back to any sport.
    Returns the canonical name if found, otherwise the original name.
    """
    conn = get_db()
    # Try sport-specific alias first
    row = conn.execute(
        "SELECT canonical_name FROM team_aliases "
        "WHERE alias = ? COLLATE NOCASE AND sport = ?",
        (name.strip(), sport),
    ).fetchone()
    if not row:
        # Fall back to any sport
        row = conn.execute(
            "SELECT canonical_name FROM team_aliases WHERE alias = ? COLLATE NOCASE",
            (name.strip(),),
        ).fetchone()
    conn.close()
    return row["canonical_name"] if row else name


def _match_by_alias(team_names, fixtures, sport="football"):
    """
    Tier 1: Resolve team names through the alias table, then find an exact
    match in the fixture list.
    """
    resolved = [_resolve_alias(name, sport=sport) for name in team_names]

    for fixture in fixtures:
        home = fixture["home_team"].lower()
        away = fixture["away_team"].lower()

        for name in resolved:
            name_lower = name.lower()
            if name_lower in home or home in name_lower:
                return _fixture_to_enrichment(fixture)
            if name_lower in away or away in name_lower:
                return _fixture_to_enrichment(fixture)

    return None


def _match_by_fuzzy(team_names, fixtures, sport="football"):
    """
    Tier 2: Use string similarity to find the closest matching fixture.
    """
    best_score = 0
    best_fixture = None

    for fixture in fixtures:
        for team_field in ("home_team", "away_team"):
            fixture_team = fixture[team_field].lower()
            for name in team_names:
                # Try both the raw name and alias-resolved name
                for candidate in (name.lower(), _resolve_alias(name, sport=sport).lower()):
                    score = SequenceMatcher(None, candidate, fixture_team).ratio()
                    if score > best_score:
                        best_score = score
                        best_fixture = fixture

    if best_score >= FUZZY_THRESHOLD and best_fixture:
        return _fixture_to_enrichment(best_fixture)

    return None


def _fixture_to_enrichment(fixture):
    """Convert a fixture dict to enrichment data for a pick."""
    return {
        "sport": fixture.get("sport", "football"),
        "competition": fixture.get("competition", ""),
        "event_name": f"{fixture['home_team']} vs {fixture['away_team']}",
        "market_type": "win",
        "api_fixture_id": fixture.get("api_id"),
        "kickoff": fixture.get("kickoff", ""),
    }
