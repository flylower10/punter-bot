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
from src.services.penalty_service import suggest_penalty
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

    # Friday 7PM — reminder to missing players
    _scheduler.add_job(
        _job_reminder_friday,
        "cron",
        day_of_week="fri",
        hour=19,
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

    # Fixture fetches — optimised for free plan (today ± 1 day)
    # Each run fetches today + tomorrow, so timing determines which days we cover.
    # Thu 7PM:  Thu+Fri  — Friday fixtures ready when picks arrive
    # Fri 11AM: Fri+Sat  — Saturday fixtures ready early for pick matching
    # Fri 9:30PM: refresh — final re-enrichment sweep before deadline
    # Sat 8AM:  Sat+Sun  — Sunday fixtures ready first thing
    # Sun 8AM:  Sun+Mon  — Monday fixtures ready early
    _scheduler.add_job(
        _job_fetch_fixtures, "cron",
        day_of_week="thu", hour=19, minute=0,
        id="fetch_fixtures_thu",
    )
    _scheduler.add_job(
        _job_fetch_fixtures, "cron",
        day_of_week="fri", hour=11, minute=0,
        id="fetch_fixtures_fri_am",
    )
    _scheduler.add_job(
        _job_fetch_fixtures, "cron",
        day_of_week="fri", hour=21, minute=30,
        id="fetch_fixtures_fri_pm",
    )
    _scheduler.add_job(
        _job_fetch_fixtures, "cron",
        day_of_week="sat", hour=8, minute=0,
        id="fetch_fixtures_sat",
    )
    _scheduler.add_job(
        _job_fetch_fixtures, "cron",
        day_of_week="sun", hour=8, minute=0,
        id="fetch_fixtures_sun",
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


def schedule_match_monitor(fixture_api_id, kickoff_iso, week_id, sport=None):
    """
    Ensure the week-level monitor is scheduled for this fixture's week.
    Thin wrapper — all fixtures for a week are polled together by one job.

    Args:
        fixture_api_id: API-Football fixture ID (used for logging only).
        kickoff_iso: ISO-format kickoff timestamp (unused; week monitor queries DB).
        week_id: current week ID.
        sport: Sport name (unused; week monitor reads sport from picks).
    """
    if not Config.MATCH_MONITOR_ENABLED:
        logger.debug("Match monitor disabled, not scheduling fixture %s", fixture_api_id)
        return
    schedule_week_monitor(week_id)


def schedule_week_monitor(week_id):
    """
    Schedule (or update) a single week-level monitor job.

    One job per week polls all active fixtures together and sends one bundled
    message per poll cycle. Replaces per-fixture monitor jobs.
    """
    if not Config.MATCH_MONITOR_ENABLED or not _scheduler:
        return

    from src.services.match_monitor_service import get_unresulted_picks_for_week

    picks = get_unresulted_picks_for_week(week_id)
    if not picks:
        logger.debug("No unresulted picks for week %s, not scheduling monitor", week_id)
        return

    tz = pytz.timezone(Config.TIMEZONE)
    now = datetime.now(tz)
    job_id = f"week_monitor_{week_id}"

    # Find earliest future kickoff among unstarted fixtures
    earliest_future_ko = None
    for pick in picks:
        kickoff_str = pick.get("kickoff")
        if not kickoff_str:
            continue
        try:
            ko = datetime.fromisoformat(kickoff_str)
            if ko.tzinfo is None:
                ko = tz.localize(ko)
        except (ValueError, TypeError):
            continue
        if ko > now and (earliest_future_ko is None or ko < earliest_future_ko):
            earliest_future_ko = ko

    # If any fixtures are already live, start immediately; otherwise wait for kickoff
    start_time = (
        earliest_future_ko
        if (earliest_future_ko and earliest_future_ko > now)
        else now + timedelta(seconds=30)
    )

    # Leave the existing job alone if it fires earlier than what we'd schedule
    existing = _scheduler.get_job(job_id)
    if existing and existing.next_run_time and existing.next_run_time <= start_time:
        logger.debug("Week monitor already scheduled for week %s at %s",
                     week_id, existing.next_run_time.isoformat())
        return

    _scheduler.add_job(
        _job_monitor_week,
        "date",
        run_date=start_time,
        args=[week_id],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info("Scheduled week monitor for week %s at %s", week_id, start_time.isoformat())


def schedule_monitors_for_week(week_id):
    """
    Schedule the week monitor for all unresulted matched picks in a week.
    Called on startup to recover from restarts.
    """
    if not Config.MATCH_MONITOR_ENABLED:
        return

    schedule_week_monitor(week_id)

    from src.services.match_monitor_service import get_unresulted_picks_for_week
    picks = get_unresulted_picks_for_week(week_id)
    if picks:
        logger.info("Startup: scheduled week monitor for week %s (%d picks)", week_id, len(picks))


def _job_monitor_week(week_id):
    """
    Poll all active fixtures for the week in one job.
    Bundles all new events into a single message per cycle.
    Reschedules itself until all fixtures complete.
    """
    try:
        from src.services.match_monitor_service import (
            get_unresulted_picks_for_week,
            _collect_new_events,
            _record_event_if_new,
        )
        from src.services.fixture_service import get_fixture_by_api_id, refresh_fixture
        from src.services.auto_result_service import auto_result_fixture, COMPLETED_STATUSES
        from src.services.result_service import week_has_loss

        if not Config.MATCH_MONITOR_ENABLED:
            return

        target_group = Config.MATCH_MONITOR_GROUP_ID or Config.SHADOW_GROUP_ID
        if not target_group:
            logger.warning("No target group configured for match monitor")
            return

        tz = pytz.timezone(Config.TIMEZONE)
        now = datetime.now(tz)

        picks = get_unresulted_picks_for_week(week_id)
        if not picks:
            logger.info("Week monitor %s: no unresulted picks, stopping", week_id)
            return

        # Deduplicate picks by fixture api_id
        seen = {}
        for pick in picks:
            api_id = pick["api_fixture_id"]
            if api_id not in seen:
                seen[api_id] = pick

        acca_alive = not week_has_loss(week_id)

        # Refresh fixtures that are already live/completed OR whose kickoff has
        # passed but whose cached status is still NS. Without the latter check,
        # matches never transition from NS to live in the cache (bootstrap problem:
        # refresh was gated on the status it was supposed to update).
        utc = pytz.utc
        now_utc = datetime.now(utc)
        for api_id, pick in seen.items():
            sport = pick.get("sport")
            fixture = get_fixture_by_api_id(api_id, sport=sport)
            if not fixture:
                continue
            cached_status = fixture.get("status", "NS")
            kickoff_passed = False
            kickoff_str = pick.get("kickoff") or fixture.get("kickoff")
            if kickoff_str:
                try:
                    ko = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                    if ko.tzinfo is None:
                        ko = utc.localize(ko)
                    kickoff_passed = now_utc >= ko
                except (ValueError, TypeError):
                    pass
            if cached_status not in ("NS", "TBD") or kickoff_passed:
                refresh_fixture(api_id, sport=sport)

        # Collect events, detect HT, and track currently live fixtures
        fixture_events_map = {}  # (home, away) -> [event_dicts]
        completed_fixtures = []
        live_keys = set()  # fixture keys currently in play (not NS/TBD/completed)

        for api_id, pick in seen.items():
            sport = pick.get("sport")
            fixture = get_fixture_by_api_id(api_id, sport=sport)
            if not fixture:
                continue

            status = fixture.get("status", "NS")
            if status in ("NS", "TBD"):
                continue  # Not started yet — will be picked up in a later poll

            home = fixture.get("home_team", "")
            away = fixture.get("away_team", "")
            key = (home, away)

            if status not in COMPLETED_STATUSES:
                live_keys.add(key)

            # Collect new goals/red cards
            if acca_alive and fixture.get("raw_json"):
                events = _collect_new_events(fixture)
                if events:
                    fixture_events_map.setdefault(key, []).extend(events)

            # Halftime score — post once per fixture (deduped)
            if acca_alive and status == "HT":
                ht_event_key = f"HT_{api_id}"
                if _record_event_if_new(api_id, ht_event_key, "HT", "Half Time"):
                    fixture_events_map.setdefault(key, []).append({
                        "event_type": "HT",
                        "home_score": fixture.get("home_score") or 0,
                        "away_score": fixture.get("away_score") or 0,
                        "player": None, "minute": None, "detail": None,
                    })

            # FT: trigger auto-result but don't add to bundle — result announcement covers it
            if status in COMPLETED_STATUSES:
                completed_fixtures.append(api_id)

        # Simultaneous fixtures: when bundle fires, include current score for quiet ones
        if len(live_keys) >= 2 and fixture_events_map:
            for api_id, pick in seen.items():
                sport = pick.get("sport")
                fixture = get_fixture_by_api_id(api_id, sport=sport)
                if not fixture:
                    continue
                status = fixture.get("status", "NS")
                if status in ("NS", "TBD") or status in COMPLETED_STATUSES:
                    continue
                home = fixture.get("home_team", "")
                away = fixture.get("away_team", "")
                key = (home, away)
                if key not in fixture_events_map:
                    fixture_events_map[key] = [{
                        "event_type": "Score",
                        "home_score": fixture.get("home_score") or 0,
                        "away_score": fixture.get("away_score") or 0,
                        "player": None, "minute": None, "detail": None,
                    }]

        # Send one bundled message for all events/scores this cycle
        if fixture_events_map:
            msg = butler.match_event_bundle(fixture_events_map)
            if msg:
                _send_fn(target_group, msg)

        # Trigger auto-result for completed fixtures (always, even if acca dead)
        for api_id in completed_fixtures:
            announcements = auto_result_fixture(api_id, week_id)
            for msg in announcements:
                _send_fn(target_group, msg)

        # Stop if nothing left to watch
        remaining = get_unresulted_picks_for_week(week_id)
        if not remaining:
            logger.info("Week monitor %s: all fixtures completed, stopping", week_id)
            return

        # Reschedule based on what's still active
        next_poll = _next_week_poll_time(remaining, now, tz)
        job_id = f"week_monitor_{week_id}"
        _scheduler.add_job(
            _job_monitor_week,
            "date",
            run_date=next_poll,
            args=[week_id],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=300,
        )
        logger.debug("Week monitor %s: next poll at %s", week_id, next_poll.isoformat())

    except Exception:
        logger.exception("Error in week monitor job for week %s", week_id)


def _next_week_poll_time(picks, now, tz):
    """
    Calculate when to schedule the next week monitor poll.

    - Live fixtures within match window   → POLL_INTERVAL_LIVE
    - Live fixtures all past match window → POLL_INTERVAL_EXTRA
    - Only NS/future fixtures             → earliest kickoff time
    """
    from src.services.fixture_service import get_fixture_by_api_id
    from src.services.auto_result_service import COMPLETED_STATUSES

    seen = {}
    for pick in picks:
        api_id = pick["api_fixture_id"]
        if api_id not in seen:
            seen[api_id] = pick

    has_live = False
    all_past_match_window = True
    earliest_future_ko = None

    for api_id, pick in seen.items():
        sport = pick.get("sport")
        fixture = get_fixture_by_api_id(api_id, sport=sport)
        if not fixture:
            continue

        status = fixture.get("status", "NS")

        if status in ("NS", "TBD"):
            kickoff_str = fixture.get("kickoff")
            if kickoff_str:
                try:
                    ko = datetime.fromisoformat(kickoff_str)
                    if ko.tzinfo is None:
                        ko = tz.localize(ko)
                    if ko > now:
                        if earliest_future_ko is None or ko < earliest_future_ko:
                            earliest_future_ko = ko
                    else:
                        # Kickoff has passed but API still reports NS — treat as live
                        # so we keep polling rather than waiting for the next fixture
                        has_live = True
                        match_end = ko + timedelta(hours=MATCH_WINDOW_HOURS)
                        if now < match_end:
                            all_past_match_window = False
                except (ValueError, TypeError):
                    pass
        elif status not in COMPLETED_STATUSES:
            has_live = True
            kickoff_str = fixture.get("kickoff")
            if kickoff_str:
                try:
                    ko = datetime.fromisoformat(kickoff_str)
                    if ko.tzinfo is None:
                        ko = tz.localize(ko)
                    match_end = ko + timedelta(hours=MATCH_WINDOW_HOURS)
                    if now < match_end:
                        all_past_match_window = False
                except (ValueError, TypeError):
                    all_past_match_window = False

    if has_live:
        interval = POLL_INTERVAL_EXTRA if all_past_match_window else POLL_INTERVAL_LIVE
        return now + timedelta(minutes=interval)

    if earliest_future_ko and earliest_future_ko > now:
        return earliest_future_ko

    return now + timedelta(minutes=POLL_INTERVAL_LIVE)


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
    """Friday 7PM: Remind players who haven't submitted."""
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

            missing = get_missing_players(week["id"])
            for player in missing:
                suggest_penalty(player["id"], week["id"], "late")
                _send(butler.penalty_suggested(player, 0, "late", 0))
                logger.info("Late penalty suggested for %s (week %s)", player["name"], week["week_number"])
    except Exception:
        logger.exception("Error in close_week job")


def _job_fetch_fixtures():
    """Daily 7:30PM (Wed-Sun): Fetch today/tomorrow fixtures for all configured sports."""
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
