"""
Match Monitor Service — unified live events + smart auto-resulting.

Polls matched fixtures during their match windows. Extracts goals and red
cards, posts them to the group, and triggers auto-resulting when a match
finishes.

Batches fixtures that share the same kickoff time into a single date-based
API request to stay within the free tier budget.
"""

import logging
from collections import defaultdict
from datetime import datetime

import pytz

from src.config import Config
from src.db import get_db
from src.services.fixture_service import (
    extract_events,
    get_fixture_by_api_id,
    refresh_fixture,
    refresh_fixtures_by_date,
)
from src.services.auto_result_service import auto_result_fixture, COMPLETED_STATUSES
import src.butler as butler

logger = logging.getLogger(__name__)

# Maximum retries after expected FT time before giving up
MAX_RETRIES = 3


def poll_fixtures(fixture_api_ids, week_id, send_fn):
    """
    Poll a batch of fixtures (sharing the same kickoff time).
    Posts new events (goals, red cards) and triggers auto-resulting on FT.

    Args:
        fixture_api_ids: list of API-Football fixture IDs to check.
        week_id: current week ID.
        send_fn: callable(chat_id, text) to send messages.

    Returns:
        dict mapping fixture_api_id → status:
            "completed" — fixture finished, auto-result triggered
            "live" — match still in progress
            "not_started" — match hasn't kicked off yet
            "error" — couldn't fetch/process
    """
    if not Config.MATCH_MONITOR_ENABLED:
        logger.info("Match monitor disabled, skipping poll")
        return {fid: "skipped" for fid in fixture_api_ids}

    target_group = Config.MATCH_MONITOR_GROUP_ID or Config.SHADOW_GROUP_ID
    if not target_group:
        logger.warning("No target group configured for match monitor")
        return {fid: "error" for fid in fixture_api_ids}

    # Try kickoff batching: if we can fetch by date, do it in one call
    _try_batch_refresh(fixture_api_ids)

    results = {}
    for api_id in fixture_api_ids:
        try:
            status = _process_fixture(api_id, week_id, send_fn, target_group)
            results[api_id] = status
        except Exception:
            logger.exception("Error processing fixture %s", api_id)
            results[api_id] = "error"

    return results


def _try_batch_refresh(fixture_api_ids):
    """
    If multiple fixtures share a kickoff date, refresh all fixtures for that
    date in a single API call instead of individual requests.
    """
    # Group fixtures by kickoff date
    date_groups = defaultdict(list)
    for api_id in fixture_api_ids:
        fixture = get_fixture_by_api_id(api_id)
        if fixture and fixture.get("kickoff"):
            try:
                kickoff = datetime.fromisoformat(fixture["kickoff"])
                date_str = kickoff.strftime("%Y-%m-%d")
                date_groups[date_str].append(api_id)
            except (ValueError, TypeError):
                pass

    # If 2+ fixtures share a date, use date-based fetch
    for date_str, ids in date_groups.items():
        if len(ids) >= 2:
            count = refresh_fixtures_by_date(date_str)
            logger.info("Batch-refreshed %d fixtures for %s (covering %d picks)",
                        count, date_str, len(ids))
        else:
            # Single fixture: individual refresh
            for api_id in ids:
                refresh_fixture(api_id)


def _process_fixture(api_id, week_id, send_fn, target_group):
    """
    Process a single fixture: post new events, trigger auto-result if FT.

    Returns:
        "completed", "live", "not_started", or "error"
    """
    fixture = get_fixture_by_api_id(api_id)
    if not fixture:
        return "error"

    status = fixture.get("status", "NS")

    if status == "NS" or status == "TBD":
        return "not_started"

    # Post any new events (goals, red cards)
    if fixture.get("raw_json"):
        _post_new_events(fixture, send_fn, target_group)

    # Check if match is finished
    if status in COMPLETED_STATUSES:
        # Post final score
        ft_msg = butler.match_ended(
            fixture["home_team"], fixture["away_team"],
            fixture.get("home_score", "?"), fixture.get("away_score", "?"),
        )
        # Only post FT if we haven't already (check fixture_events for FT key)
        if _record_event_if_new(api_id, f"FT_{api_id}", "FT", "Full Time"):
            send_fn(target_group, ft_msg)

        # Trigger auto-result for the pick linked to this fixture
        announcements = auto_result_fixture(api_id, week_id)
        for msg in announcements:
            # Auto-result announcements go to main group (existing behaviour)
            main_group = Config.GROUP_CHAT_ID
            if main_group:
                send_fn(main_group, msg)

        return "completed"

    return "live"


def _post_new_events(fixture, send_fn, target_group):
    """Extract events from fixture data and post any that haven't been posted yet."""
    raw = fixture.get("raw_json")
    if not raw:
        return

    import json
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return

    events = extract_events(data)
    api_id = fixture["api_id"]

    for ev in events:
        if _record_event_if_new(api_id, ev["event_key"], ev["event_type"], ev.get("detail")):
            # Build and send event message
            msg = butler.match_event(
                ev["event_type"],
                fixture["home_team"], fixture["away_team"],
                fixture.get("home_score", 0), fixture.get("away_score", 0),
                ev["player"], ev["minute"],
                detail=ev.get("detail"),
            )
            if msg:
                send_fn(target_group, msg)
                logger.info("Posted event: %s %s", ev["event_key"], fixture["home_team"])


def _record_event_if_new(fixture_api_id, event_key, event_type, detail=None):
    """
    Try to insert an event into fixture_events. Returns True if it's new
    (insert succeeded), False if it was already posted (UNIQUE constraint).
    """
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO fixture_events (fixture_api_id, event_key, event_type, detail) "
            "VALUES (?, ?, ?, ?)",
            (fixture_api_id, event_key, event_type, detail),
        )
        conn.commit()
        return True
    except Exception:
        # UNIQUE constraint violation = already posted
        return False
    finally:
        conn.close()


def get_unresulted_picks_for_week(week_id):
    """
    Get matched picks for the current week that don't have a result yet.
    Used for startup recovery to schedule monitors for in-progress matches.

    Returns:
        list of dicts with api_fixture_id and kickoff.
    """
    conn = get_db()
    picks = conn.execute(
        """SELECT p.api_fixture_id, f.kickoff
           FROM picks p
           JOIN fixtures f ON f.api_id = p.api_fixture_id
           LEFT JOIN results r ON r.pick_id = p.id
           WHERE p.week_id = ? AND p.api_fixture_id IS NOT NULL AND r.id IS NULL
           ORDER BY f.kickoff""",
        (week_id,),
    ).fetchall()
    conn.close()
    return [{"api_fixture_id": p["api_fixture_id"], "kickoff": p["kickoff"]} for p in picks]
