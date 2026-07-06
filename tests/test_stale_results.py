"""
Tests for the stale-results nudge: picks still unresulted hours after
their fixture kicked off should be surfaced to the shadow (admin) group
instead of waiting for players to prod the bot in the main chat.
"""

from datetime import datetime, timedelta

import pytest
import pytz

import src.services.scheduler as scheduler
from src.db import get_db
from src.services.player_service import get_all_players
from src.services.pick_service import submit_pick
from src.services.week_service import get_or_create_current_week

GROUP_ID = "test-group@g.us"
SHADOW_ID = "shadow-group@g.us"
TZ = pytz.timezone("Europe/Dublin")


def _insert_fixture(api_id, kickoff_dt, sport="football"):
    conn = get_db()
    conn.execute(
        "INSERT INTO fixtures (api_id, sport, competition, home_team, away_team, kickoff) "
        "VALUES (?, ?, 'Premier League', 'Liverpool', 'Everton', ?)",
        (api_id, sport, kickoff_dt.isoformat()),
    )
    conn.commit()
    conn.close()


def _match_pick_to_fixture(pick_id, api_id, sport="football"):
    conn = get_db()
    conn.execute(
        "UPDATE picks SET api_fixture_id = ?, sport = ? WHERE id = ?",
        (api_id, sport, pick_id),
    )
    conn.commit()
    conn.close()


def _record_result(pick_id):
    conn = get_db()
    conn.execute(
        "INSERT INTO results (pick_id, outcome) VALUES (?, 'win')", (pick_id,)
    )
    conn.commit()
    conn.close()


def _close_week(week_id):
    conn = get_db()
    conn.execute("UPDATE weeks SET status = 'closed' WHERE id = ?", (week_id,))
    conn.commit()
    conn.close()


@pytest.fixture
def stale_env(monkeypatch):
    sent = []
    monkeypatch.setattr("src.config.Config.SHADOW_GROUP_ID", SHADOW_ID)
    monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", GROUP_ID)
    monkeypatch.setattr(scheduler, "_send_fn", lambda chat_id, text: sent.append((chat_id, text)))
    return sent


class TestStaleResultsJob:
    def test_alerts_shadow_for_pick_unresulted_long_after_kickoff(self, stale_env):
        week = get_or_create_current_week(group_id=GROUP_ID)
        player = next(p for p in get_all_players() if p["nickname"] == "Kev")
        pick, _, _, _ = submit_pick(
            player["id"], week["id"], "Liverpool to win", 2.0, "evens", "win"
        )
        _insert_fixture(9001, datetime.now(TZ) - timedelta(hours=8))
        _match_pick_to_fixture(pick["id"], 9001)
        _close_week(week["id"])

        scheduler._job_stale_results()

        assert len(stale_env) == 1
        chat_id, text = stale_env[0]
        assert chat_id == SHADOW_ID
        assert "Kev" in text
        assert "Liverpool to win" in text

    def test_no_alert_when_result_recorded(self, stale_env):
        week = get_or_create_current_week(group_id=GROUP_ID)
        player = next(p for p in get_all_players() if p["nickname"] == "Kev")
        pick, _, _, _ = submit_pick(
            player["id"], week["id"], "Liverpool to win", 2.0, "evens", "win"
        )
        _insert_fixture(9001, datetime.now(TZ) - timedelta(hours=8))
        _match_pick_to_fixture(pick["id"], 9001)
        _record_result(pick["id"])
        _close_week(week["id"])

        scheduler._job_stale_results()

        assert stale_env == []

    def test_no_alert_for_recent_kickoff(self, stale_env):
        week = get_or_create_current_week(group_id=GROUP_ID)
        player = next(p for p in get_all_players() if p["nickname"] == "Kev")
        pick, _, _, _ = submit_pick(
            player["id"], week["id"], "Liverpool to win", 2.0, "evens", "win"
        )
        _insert_fixture(9001, datetime.now(TZ) - timedelta(hours=1))
        _match_pick_to_fixture(pick["id"], 9001)
        _close_week(week["id"])

        scheduler._job_stale_results()

        assert stale_env == []

    def test_no_alert_when_week_still_open(self, stale_env):
        week = get_or_create_current_week(group_id=GROUP_ID)
        player = next(p for p in get_all_players() if p["nickname"] == "Kev")
        pick, _, _, _ = submit_pick(
            player["id"], week["id"], "Liverpool to win", 2.0, "evens", "win"
        )
        _insert_fixture(9001, datetime.now(TZ) - timedelta(hours=8))
        _match_pick_to_fixture(pick["id"], 9001)
        # week left open — bet not placed yet, results not expected

        scheduler._job_stale_results()

        assert stale_env == []

    def test_no_alert_without_shadow_group(self, stale_env, monkeypatch):
        monkeypatch.setattr("src.config.Config.SHADOW_GROUP_ID", "")
        week = get_or_create_current_week(group_id=GROUP_ID)
        player = next(p for p in get_all_players() if p["nickname"] == "Kev")
        pick, _, _, _ = submit_pick(
            player["id"], week["id"], "Liverpool to win", 2.0, "evens", "win"
        )
        _insert_fixture(9001, datetime.now(TZ) - timedelta(hours=8))
        _match_pick_to_fixture(pick["id"], 9001)
        _close_week(week["id"])

        scheduler._job_stale_results()

        assert stale_env == []
