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


def get_or_create_current_week():
    """
    Return the current open week, or create one if none exists.

    Weeks are numbered sequentially within a season (calendar year).
    The deadline is always Friday 10PM in the configured timezone.
    """
    conn = get_db()
    now = _now()
    season = str(now.year)

    # Check for an existing open week
    week = conn.execute(
        "SELECT * FROM weeks WHERE status = 'open' AND season = ? ORDER BY id DESC LIMIT 1",
        (season,),
    ).fetchone()

    if week:
        conn.close()
        return dict(week)

    # Calculate the next Friday 10PM deadline
    deadline = _next_friday_10pm(now)

    # Get next week number
    last_week = conn.execute(
        "SELECT MAX(week_number) as max_num FROM weeks WHERE season = ?",
        (season,),
    ).fetchone()
    week_number = (last_week["max_num"] or 0) + 1

    conn.execute(
        "INSERT INTO weeks (week_number, season, deadline, status) VALUES (?, ?, ?, 'open')",
        (week_number, season, deadline.isoformat()),
    )
    conn.commit()

    week = conn.execute(
        "SELECT * FROM weeks WHERE season = ? AND week_number = ?",
        (season, week_number),
    ).fetchone()
    conn.close()

    # New week = new persona
    try:
        from src.llm_client import reset_persona
        persona = reset_persona()
        if persona:
            logger.info("New week %d — persona: %s", week_number, persona.get("name", "?"))
    except Exception:
        pass

    return dict(week)


def get_current_week():
    """Return the current open or closed week, or None."""
    conn = get_db()
    season = str(_now().year)
    week = conn.execute(
        "SELECT * FROM weeks WHERE status IN ('open', 'closed') AND season = ? ORDER BY id DESC LIMIT 1",
        (season,),
    ).fetchone()
    conn.close()
    return dict(week) if week else None


def get_week_for_reset():
    """
    Return a week that can be reset: current open/closed, or most recent completed.
    Used by !resetweek to allow re-testing after a week is completed.
    """
    week = get_current_week()
    if week:
        return week
    conn = get_db()
    season = str(_now().year)
    week = conn.execute(
        "SELECT * FROM weeks WHERE status = 'completed' AND season = ? ORDER BY id DESC LIMIT 1",
        (season,),
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


def is_within_submission_window():
    """
    Check if we're in the pick submission window.
    Wednesday 7PM -> Friday 10PM (configured timezone).
    """
    now = _now()
    weekday = now.weekday()  # 0=Mon, 2=Wed, 4=Fri

    # Wednesday after 7PM
    if weekday == 2 and now.hour >= 19:
        return True
    # Thursday or Friday before 10PM
    if weekday in (3, 4):
        if weekday == 4 and now.hour >= 22:
            return False
        return True

    return False


def is_past_deadline():
    """Check if we're past Friday 10PM."""
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
