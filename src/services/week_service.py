import logging
from datetime import datetime, timedelta

import pytz

from src.config import Config
from src.db import get_db

logger = logging.getLogger(__name__)


def _now():
    """Current time in the configured timezone."""
    tz = pytz.timezone(Config.TIMEZONE)
    return datetime.now(tz)


def get_or_create_current_week(group_id="default"):
    """
    Return the current open week for a group, or create one if none exists.

    Weeks are numbered sequentially within a season (calendar year) per group.
    The deadline is always Friday 10PM in the configured timezone.
    """
    conn = get_db()
    now = _now()
    season = str(now.year)

    # Check for an existing open week for this group
    week = conn.execute(
        "SELECT * FROM weeks WHERE status = 'open' AND season = ? AND group_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (season, group_id),
    ).fetchone()

    if week:
        conn.close()
        return dict(week)

    # Calculate the next Friday 10PM deadline
    deadline = _next_friday_10pm(now)

    # Get next week number for this group
    last_week = conn.execute(
        "SELECT MAX(week_number) as max_num FROM weeks WHERE season = ? AND group_id = ?",
        (season, group_id),
    ).fetchone()
    week_number = (last_week["max_num"] or 0) + 1

    conn.execute(
        "INSERT INTO weeks (week_number, season, group_id, deadline, status) "
        "VALUES (?, ?, ?, ?, 'open')",
        (week_number, season, group_id, deadline.isoformat()),
    )
    conn.commit()

    week = conn.execute(
        "SELECT * FROM weeks WHERE season = ? AND week_number = ? AND group_id = ?",
        (season, week_number, group_id),
    ).fetchone()
    conn.close()

    return dict(week)


def get_current_week(group_id="default"):
    """Return the current open or closed week for a group, or None."""
    conn = get_db()
    season = str(_now().year)
    week = conn.execute(
        "SELECT * FROM weeks WHERE status IN ('open', 'closed') AND season = ? "
        "AND group_id = ? ORDER BY id DESC LIMIT 1",
        (season, group_id),
    ).fetchone()
    conn.close()
    return dict(week) if week else None


def get_week_for_reset(group_id="default"):
    """
    Return a week that can be reset: current open/closed, or most recent completed.
    Used by !resetweek to allow re-testing after a week is completed.
    """
    week = get_current_week(group_id=group_id)
    if week:
        return week
    conn = get_db()
    season = str(_now().year)
    week = conn.execute(
        "SELECT * FROM weeks WHERE status = 'completed' AND season = ? "
        "AND group_id = ? ORDER BY id DESC LIMIT 1",
        (season, group_id),
    ).fetchone()
    conn.close()
    return dict(week) if week else None


def close_week(week_id):
    """Mark a week as closed (deadline passed)."""
    conn = get_db()
    conn.execute("UPDATE weeks SET status = 'closed' WHERE id = ?", (week_id,))
    conn.commit()
    conn.close()


def complete_week(week_id):
    """Mark a week as completed (all results in)."""
    conn = get_db()
    conn.execute("UPDATE weeks SET status = 'completed' WHERE id = ?", (week_id,))
    conn.commit()
    conn.close()


def is_within_submission_window(group_id="default"):
    """
    Check if we're in the pick submission window.

    The window is open when EITHER:
    1. We're in the normal Wed 7PM → Fri 10PM window, OR
    2. The most recent week is completed (all results in) — picks for
       the next week are accepted immediately, OR
    3. A week was opened early and its deadline hasn't passed yet.
    """
    now = _now()
    weekday = now.weekday()  # 0=Mon, 2=Wed, 4=Fri

    # 1. Normal time window: Wed 7PM → Fri 10PM
    if weekday == 2 and now.hour >= 19:
        return True
    if weekday in (3, 4):
        if weekday == 4 and now.hour >= 22:
            pass  # Past the strict deadline, but do NOT short-circuit here.
                  # If the previous week just completed (all results in), the
                  # window re-opens immediately for next week. Fall through to
                  # the DB check below — it handles this case.
        else:
            return True

    # 2. Check DB for early opening
    conn = get_db()
    latest = conn.execute(
        "SELECT status, deadline FROM weeks WHERE group_id = ? ORDER BY id DESC LIMIT 1",
        (group_id,),
    ).fetchone()
    conn.close()

    if latest is None:
        return True  # No weeks exist yet

    if latest["status"] == "completed":
        return True  # All results in — next week open

    if latest["status"] == "open":
        # Week was opened early — accept picks until its deadline
        if latest["deadline"]:
            try:
                deadline = datetime.fromisoformat(latest["deadline"])
                tz = pytz.timezone(Config.TIMEZONE)
                if deadline.tzinfo is None:
                    deadline = tz.localize(deadline)
                if now > deadline:
                    return False
            except (ValueError, TypeError):
                pass
        return True

    # status == 'closed' — results pending
    return False


def is_past_deadline():
    """
    Simple time-only check: are we past Friday 10PM?

    NOTE: Do NOT use this to decide whether to accept picks. Use
    is_within_submission_window() instead — it handles dynamic window
    opening when the previous week completes early, and reads DB state.
    This function is only for contexts where DB state is irrelevant
    (e.g. scheduler jobs that need a quick time check).
    """
    now = _now()
    weekday = now.weekday()

    # Friday after 10PM
    if weekday == 4 and now.hour >= 22:
        return True
    # Saturday or Sunday
    if weekday in (5, 6):
        return True

    return False


def _next_friday_10pm(now):
    """Calculate the next Friday 10PM from the given datetime."""
    tz = pytz.timezone(Config.TIMEZONE)
    days_ahead = 4 - now.weekday()  # Friday = 4
    if days_ahead < 0:
        days_ahead += 7
    elif days_ahead == 0 and now.hour >= 22:
        days_ahead = 7

    friday = now.date() + timedelta(days=days_ahead)
    return tz.localize(datetime(friday.year, friday.month, friday.day, 22, 0, 0))
