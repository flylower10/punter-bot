"""
Scheduled jobs for The Betting Butler.

Uses APScheduler to run timed reminders, deadline enforcement,
and match monitoring (live events + smart auto-resulting).
All times are in Europe/Dublin timezone.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler

from src.config import Config
from src.services.pick_service import get_missing_players
from src.services.week_service import (
    get_or_create_current_week, get_current_week, close_week, is_past_deadline,
)
import src.butler as butler

logger = logging.getLogger(__name__)

_scheduler = None
_send_fn = None

# Polling intervals
POLL_INTERVAL_LIVE = 10     # minutes — during match window
POLL_INTERVAL_EXTRA = 30    # minutes — after expected FT (extra time/delays)
MATCH_WINDOW_HOURS = 2.5    # hours after kickoff when we expect FT
EXTRA_TIME_HOURS = 1        # extra polling window after match window


def init_scheduler(send_message_fn):
    """
    Initialize and start the scheduler.

    send_message_fn should accept (chat_id, text) and send the message
    to the WhatsApp group.
    """
    global _scheduler, _send_fn
    _send_fn = send_message_fn

    _scheduler = BackgroundScheduler(timezone=Config.TIMEZONE)

    # Wednesday 7PM — silently create the week if none exists
    _scheduler.add_job(
        _job_create_week,
        "cron",
        day_of_week="wed",
        hour=19,
        minute=0,
        id="create_week",
    )

    # Thursday 7PM — reminder to all players
    _scheduler.add_job(
        _job_reminder_thursday,
        "cron",
        day_of_week="thu",
        hour=19,
        minute=0,
        id="reminder_thursday",
    )

    # Friday 5PM — reminder to missing players
    _scheduler.add_job(
        _job_reminder_friday,
        "cron",
        day_of_week="fri",
        hour=17,
        minute=0,
        id="reminder_friday",
    )

    # Friday 9:30PM — final warning
    _scheduler.add_job(
        _job_reminder_final,
        "cron",
        day_of_week="fri",
        hour=21,
        minute=30,
        id="reminder_final",
    )

    # Friday 10PM — close the week
    _scheduler.add_job(
        _job_close_week,
        "cron",
        day_of_week="fri",
        hour=22,
        minute=0,
        id="close_week",
    )

    # Daily 7:30PM (Wed–Sun) — fetch tomorrow's fixtures from API-Football
    # Free plan only allows today ± 1 day, so we fetch daily
    _scheduler.add_job(
        _job_fetch_fixtures,
        "cron",
        day_of_week="wed,thu,fri,sat,sun",
        hour=19,
        minute=30,
        id="fetch_fixtures",
    )

    # Monday 10AM — safety sweep auto-result (catches anything missed)
    _scheduler.add_job(
        _job_auto_result,
        "cron",
        day_of_week="mon",
        hour=10,
        minute=0,
        id="auto_result_monday",
    )

    _scheduler.start()
    logger.info("Scheduler started with %d jobs", len(_scheduler.get_jobs()))


def schedule_match_monitor(fixture_api_id, kickoff_iso, week_id):
    """
    Schedule polling jobs for a fixture's match window.

    Creates interval jobs that poll the fixture from kickoff through
    kickoff + 2.5h (every 10 min), then kickoff + 3.5h (every 30 min).

    If kickoff is in the past, schedules immediately at the appropriate interval.

    Args:
        fixture_api_id: API-Football fixture ID.
        kickoff_iso: ISO-format kickoff timestamp.
        week_id: current week ID.
    """
    if not Config.MATCH_MONITOR_ENABLED:
        logger.debug("Match monitor disabled, not scheduling fixture %s", fixture_api_id)
        return

    if not _scheduler:
        logger.warning("Scheduler not initialized, cannot schedule monitor")
        return

    tz = pytz.timezone(Config.TIMEZONE)
    try:
        kickoff = datetime.fromisoformat(kickoff_iso)
        if kickoff.tzinfo is None:
            kickoff = tz.localize(kickoff)
    except (ValueError, TypeError):
        logger.warning("Invalid kickoff time: %s", kickoff_iso)
        return

    now = datetime.now(tz)
    match_end = kickoff + timedelta(hours=MATCH_WINDOW_HOURS)
    extra_end = match_end + timedelta(hours=EXTRA_TIME_HOURS)

    # Don't schedule if the match window has fully passed
    if now > extra_end:
        logger.info("Fixture %s past monitoring window, skipping", fixture_api_id)
        return

    job_id = f"monitor_{fixture_api_id}_{week_id}"

    # Remove existing job for this fixture if any
    existing = _scheduler.get_job(job_id)
    if existing:
        logger.info("Monitor already scheduled for fixture %s", fixture_api_id)
        return

    # Schedule the first poll
    if now < kickoff:
        # Match hasn't started — first poll at kickoff
        start_time = kickoff
    else:
        # Match is already underway — poll immediately
        start_time = now + timedelta(seconds=30)

    _scheduler.add_job(
        _job_monitor_fixture,
        "date",
        run_date=start_time,
        args=[fixture_api_id, week_id, 0],
        id=job_id,
    )
    logger.info("Scheduled monitor for fixture %s at %s (week %s)",
                fixture_api_id, start_time.isoformat(), week_id)


def schedule_monitors_for_week(week_id):
    """
    Schedule monitors for all unresulted matched picks in a week.
    Called on startup to recover from restarts.
    """
    if not Config.MATCH_MONITOR_ENABLED:
        return

    from src.services.match_monitor_service import get_unresulted_picks_for_week
    picks = get_unresulted_picks_for_week(week_id)

    for pick in picks:
        schedule_match_monitor(pick["api_fixture_id"], pick["kickoff"], week_id)

    if picks:
        logger.info("Startup: scheduled %d match monitors for week %s", len(picks), week_id)


def _job_monitor_fixture(fixture_api_id, week_id, poll_count):
    """
    Single poll of a fixture. Posts events, checks for FT, and
    reschedules the next poll if the match isn't finished.
    """
    try:
        from src.services.match_monitor_service import poll_fixtures
        results = poll_fixtures([fixture_api_id], week_id, _send_fn)
        status = results.get(fixture_api_id, "error")

        tz = pytz.timezone(Config.TIMEZONE)
        now = datetime.now(tz)

        if status == "completed":
            logger.info("Fixture %s completed, monitor done", fixture_api_id)
            return

        if status == "skipped":
            return

        # Determine next poll interval
        from src.services.fixture_service import get_fixture_by_api_id
        fixture = get_fixture_by_api_id(fixture_api_id)
        if fixture and fixture.get("kickoff"):
            try:
                kickoff = datetime.fromisoformat(fixture["kickoff"])
                if kickoff.tzinfo is None:
                    kickoff = tz.localize(kickoff)
            except (ValueError, TypeError):
                kickoff = now - timedelta(hours=2)

            match_end = kickoff + timedelta(hours=MATCH_WINDOW_HOURS)
            extra_end = match_end + timedelta(hours=EXTRA_TIME_HOURS)

            if now > extra_end:
                logger.info("Fixture %s past extra time window, stopping monitor", fixture_api_id)
                return

            if now > match_end:
                interval = POLL_INTERVAL_EXTRA
            else:
                interval = POLL_INTERVAL_LIVE
        else:
            interval = POLL_INTERVAL_LIVE

        # Schedule next poll
        next_poll = now + timedelta(minutes=interval)
        next_count = poll_count + 1
        job_id = f"monitor_{fixture_api_id}_{week_id}"

        _scheduler.add_job(
            _job_monitor_fixture,
            "date",
            run_date=next_poll,
            args=[fixture_api_id, week_id, next_count],
            id=job_id,
            replace_existing=True,
        )
        logger.debug("Next poll for fixture %s at %s (poll #%d)",
                      fixture_api_id, next_poll.isoformat(), next_count)

    except Exception:
        logger.exception("Error in monitor job for fixture %s", fixture_api_id)


def _main_group_id():
    """Return the primary group ID for scheduler operations."""
    return Config.GROUP_CHAT_ID or (Config.GROUP_CHAT_IDS[0] if Config.GROUP_CHAT_IDS else "default")


def _send(text):
    """Send a message to the group chat."""
    if _send_fn and Config.GROUP_CHAT_ID:
        _send_fn(Config.GROUP_CHAT_ID, text)


def _job_create_week():
    """Wednesday 7PM: Create the week silently."""
    try:
        week = get_or_create_current_week(group_id=_main_group_id())
        logger.info("Week %s ready (id=%s)", week["week_number"], week["id"])
    except Exception:
        logger.exception("Error in create_week job")


def _job_reminder_thursday():
    """Thursday 7PM: Remind all players that picks are due."""
    try:
        _send(butler.reminder_thursday())
        logger.info("Thursday reminder sent")
    except Exception:
        logger.exception("Error in reminder_thursday job")


def _job_reminder_friday():
    """Friday 5PM: Remind players who haven't submitted."""
    try:
        week = get_current_week(group_id=_main_group_id())
        if not week:
            return

        missing = get_missing_players(week["id"])
        if missing:
            _send(butler.reminder_friday(missing))
            logger.info("Friday reminder sent for %d missing players", len(missing))
        else:
            logger.info("Friday reminder skipped — all picks in")
    except Exception:
        logger.exception("Error in reminder_friday job")


def _job_reminder_final():
    """Friday 9:30PM: Final warning to missing players."""
    try:
        week = get_current_week(group_id=_main_group_id())
        if not week:
            return

        missing = get_missing_players(week["id"])
        if missing:
            _send(butler.reminder_final(missing))
            logger.info("Final reminder sent for %d missing players", len(missing))
        else:
            logger.info("Final reminder skipped — all picks in")
    except Exception:
        logger.exception("Error in reminder_final job")


def _job_close_week():
    """Friday 10PM: Close the week (no more regular picks)."""
    try:
        week = get_current_week(group_id=_main_group_id())
        if not week:
            return

        if week["status"] == "open":
            close_week(week["id"])
            logger.info("Week %s closed (deadline passed)", week["week_number"])
    except Exception:
        logger.exception("Error in close_week job")


def _job_fetch_fixtures():
    """Daily 7:30PM (Wed-Sun): Fetch today/tomorrow fixtures from API-Football."""
    try:
        from src.services.fixture_service import fetch_weekend_fixtures
        count = fetch_weekend_fixtures()
        logger.info("Fetched %d weekend fixtures", count)
    except Exception:
        logger.exception("Error in fetch_fixtures job")


def _job_auto_result():
    """Monday 10AM: Safety sweep — auto-result any remaining matched picks."""
    try:
        from src.services.auto_result_service import auto_result_week
        week = get_current_week(group_id=_main_group_id())
        if not week:
            return

        results = auto_result_week(week["id"])
        if results:
            for announcement in results:
                _send(announcement)
            logger.info("Auto-resulted %d picks", len(results))
        else:
            logger.info("Auto-result: no new results")
    except Exception:
        logger.exception("Error in auto_result job")
