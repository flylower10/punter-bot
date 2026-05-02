"""Tests for scheduler jobs."""

import src.services.scheduler as scheduler_module
from src.config import Config
from src.db import get_db
from src.services.penalty_service import get_pending_penalties
from src.services.pick_service import submit_pick
from src.services.player_service import get_all_players
from src.services.week_service import get_or_create_current_week


GROUP_ID = "test-group@g.us"


class TestCloseWeekJob:
    def test_late_penalty_suggested_for_missing_players(self, monkeypatch):
        monkeypatch.setattr(Config, "GROUP_CHAT_ID", GROUP_ID)
        monkeypatch.setattr(scheduler_module, "_send_fn", lambda gid, msg: None)

        week = get_or_create_current_week(group_id=GROUP_ID)
        conn = get_db()
        conn.execute("UPDATE weeks SET status = 'open' WHERE id = ?", (week["id"],))
        conn.commit()
        conn.close()

        players = get_all_players()
        # Submit picks for all but the last player
        for p in players[:-1]:
            submit_pick(p["id"], week["id"], "Team to win", 2.0, "2/1", "win")

        scheduler_module._job_close_week()

        pending = get_pending_penalties()
        assert len(pending) == 1
        assert pending[0]["player_id"] == players[-1]["id"]
        assert pending[0]["type"] == "late"
        assert pending[0]["status"] == "suggested"

    def test_no_penalty_when_all_picks_submitted(self, monkeypatch):
        monkeypatch.setattr(Config, "GROUP_CHAT_ID", GROUP_ID)
        monkeypatch.setattr(scheduler_module, "_send_fn", lambda gid, msg: None)

        week = get_or_create_current_week(group_id=GROUP_ID)
        conn = get_db()
        conn.execute("UPDATE weeks SET status = 'open' WHERE id = ?", (week["id"],))
        conn.commit()
        conn.close()

        for p in get_all_players():
            submit_pick(p["id"], week["id"], "Team to win", 2.0, "2/1", "win")

        scheduler_module._job_close_week()

        assert get_pending_penalties() == []

    def test_no_penalty_when_week_already_closed(self, monkeypatch):
        monkeypatch.setattr(Config, "GROUP_CHAT_ID", GROUP_ID)
        monkeypatch.setattr(scheduler_module, "_send_fn", lambda gid, msg: None)

        week = get_or_create_current_week(group_id=GROUP_ID)
        conn = get_db()
        conn.execute("UPDATE weeks SET status = 'closed' WHERE id = ?", (week["id"],))
        conn.commit()
        conn.close()

        scheduler_module._job_close_week()

        assert get_pending_penalties() == []
