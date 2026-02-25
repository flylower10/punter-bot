"""
API-Football client (v3, free tier: 100 requests/day).

Fetches fixtures and results from api-football.com. Responses are cached
locally to avoid burning quota during development.

Docs: https://www.api-football.com/documentation-v3
"""

import json
import logging
import os
from datetime import datetime, date
from pathlib import Path

import requests

from src.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://v3.football.api-sports.io"
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "api_cache"


def _headers():
    return {
        "x-apisports-key": Config.API_FOOTBALL_KEY,
    }


def _cache_path(endpoint, params):
    """Build a cache file path from the endpoint and params."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = endpoint.strip("/").replace("/", "_")
    param_str = "_".join(f"{k}={v}" for k, v in sorted(params.items()))
    return CACHE_DIR / f"{key}_{param_str}.json"


def _get(endpoint, params, cache_ttl_hours=6):
    """
    Make a GET request to API-Football with local file caching.

    Args:
        endpoint: API endpoint path (e.g. "/fixtures")
        params: Query parameters dict
        cache_ttl_hours: How long to use cached response (0 = always fetch)

    Returns:
        dict — the API response, or None on failure.
    """
    cache_file = _cache_path(endpoint, params)

    # Check cache
    if cache_ttl_hours > 0 and cache_file.exists():
        try:
            stat = cache_file.stat()
            age_hours = (datetime.now().timestamp() - stat.st_mtime) / 3600
            if age_hours < cache_ttl_hours:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                logger.info("API-Football cache hit: %s (%.1fh old)", cache_file.name, age_hours)
                return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Cache read failed: %s", e)

    # Make API request
    if not Config.API_FOOTBALL_KEY:
        logger.warning("API_FOOTBALL_KEY not configured — skipping API call")
        return None

    try:
        resp = requests.get(
            f"{BASE_URL}{endpoint}",
            headers=_headers(),
            params=params,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("API-Football returned %d: %s", resp.status_code, resp.text[:200])
            return None

        data = resp.json()

        # Check for API errors
        errors = data.get("errors", {})
        if errors:
            logger.warning("API-Football errors: %s", errors)
            return None

        # Cache the response
        try:
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
            logger.info("API-Football cached: %s", cache_file.name)
        except OSError as e:
            logger.warning("Cache write failed: %s", e)

        return data

    except requests.Timeout:
        logger.warning("API-Football request timed out")
        return None
    except requests.RequestException as e:
        logger.warning("API-Football request failed: %s", e)
        return None


def _football_season_year():
    """Return the season start year for the current European football season.

    European football seasons run Aug–May. A date in Jan–Jul belongs to the
    season that started the previous August (e.g. Feb 2026 → 2025-26 season → 2025).
    A date in Aug–Dec belongs to the season starting that year.
    """
    today = date.today()
    return today.year if today.month >= 8 else today.year - 1


def get_fixtures_by_date(date_str):
    """
    Fetch fixtures for a specific date.

    Args:
        date_str: Date in YYYY-MM-DD format.

    Returns:
        list of fixture dicts, or empty list on failure.
    """
    data = _get("/fixtures", {"date": date_str}, cache_ttl_hours=6)
    if not data:
        return []
    return data.get("response", [])


def get_fixtures_by_date_range(start_date, end_date, league_id=None):
    """
    Fetch fixtures between two dates.

    NOTE: Requires league + season params, which need a paid API plan for the
    current season. Use get_fixtures_by_date() for free-plan-compatible access.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        league_id: Optional league filter (e.g. 39 for EPL)

    Returns:
        list of fixture dicts, or empty list on failure.
    """
    params = {"from": start_date, "to": end_date}
    if league_id:
        params["league"] = str(league_id)
        params["season"] = str(_football_season_year())

    data = _get("/fixtures", params, cache_ttl_hours=6)
    if not data:
        return []
    return data.get("response", [])


def get_fixture_by_id(fixture_id):
    """
    Fetch a single fixture by its API ID.

    Returns:
        fixture dict, or None.
    """
    data = _get("/fixtures", {"id": str(fixture_id)}, cache_ttl_hours=1)
    if not data:
        return None
    response = data.get("response", [])
    return response[0] if response else None


# Key league IDs for common competitions
LEAGUE_IDS = {
    # England
    "Premier League": 39,
    "Championship": 40,
    "League One": 41,
    "League Two": 42,
    "FA Cup": 45,
    "League Cup": 48,
    "Community Shield": 528,
    # Europe
    "La Liga": 140,
    "Serie A": 135,
    "Bundesliga": 78,
    "Ligue 1": 61,
    "Champions League": 2,
    "Europa League": 3,
    "Conference League": 848,
    # Other
    "Scottish Premiership": 179,
}

# Priority leagues to fetch (covers most picks from the lads)
PRIORITY_LEAGUES = [
    # England — all leagues + cups
    39, 40, 41, 42, 45, 48,
    # Europe — top 4 leagues + European competitions
    140, 135, 78, 61, 2, 3, 848,
    # Scotland
    179,
]
