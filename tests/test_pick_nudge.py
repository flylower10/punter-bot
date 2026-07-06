"""
Tests for the near-deadline shadow nudge: when the emoji guard silently
drops a pick-like message from a player who has no pick yet on a
Thursday/Friday, the shadow (admin) group gets a heads-up so a genuinely
intended pick isn't lost.
"""

from datetime import datetime

import pytest
import pytz

from src.app import _nudge_shadow_if_missing_pick
from src.services.player_service import get_all_players
from src.services.pick_service import submit_pick
from src.services.week_service import get_or_create_current_week

GROUP_ID = "test-group@g.us"
SHADOW_ID = "shadow-group@g.us"

TZ = pytz.timezone("Europe/Dublin")
# 2026-07-02 is a Thursday, 2026-07-06 is a Monday
THURSDAY_EVENING = TZ.localize(datetime(2026, 7, 2, 20, 0))
MONDAY_EVENING = TZ.localize(datetime(2026, 7, 6, 20, 0))


@pytest.fixture
def nudge_env(monkeypatch):
    monkeypatch.setattr("src.config.Config.SHADOW_GROUP_ID", SHADOW_ID)
    monkeypatch.setattr("src.app.is_within_submission_window", lambda group_id: True)


def _get_player(nickname="Kev"):
    return next(p for p in get_all_players() if p["nickname"] == nickname)


class TestShadowNudge:
    def test_nudges_shadow_when_player_missing_pick_near_deadline(
        self, nudge_env, mock_send_message
    ):
        week = get_or_create_current_week(group_id=GROUP_ID)
        player = _get_player()

        _nudge_shadow_if_missing_pick(
            player, "Shelbourne 4/7", GROUP_ID, now=THURSDAY_EVENING
        )

        assert len(mock_send_message) == 1
        chat_id, text = mock_send_message[0]
        assert chat_id == SHADOW_ID
        assert player["name"] in text
        assert "Shelbourne 4/7" in text

    def test_no_nudge_when_player_already_has_pick(
        self, nudge_env, mock_send_message
    ):
        week = get_or_create_current_week(group_id=GROUP_ID)
        player = _get_player()
        submit_pick(player["id"], week["id"], "Liverpool to win", 2.0, "evens", "win")

        _nudge_shadow_if_missing_pick(
            player, "Shelbourne 4/7", GROUP_ID, now=THURSDAY_EVENING
        )

        assert mock_send_message == []

    def test_no_nudge_outside_thursday_friday(self, nudge_env, mock_send_message):
        get_or_create_current_week(group_id=GROUP_ID)
        player = _get_player()

        _nudge_shadow_if_missing_pick(
            player, "Shelbourne 4/7", GROUP_ID, now=MONDAY_EVENING
        )

        assert mock_send_message == []

    def test_no_nudge_when_window_closed(self, monkeypatch, mock_send_message):
        monkeypatch.setattr("src.config.Config.SHADOW_GROUP_ID", SHADOW_ID)
        monkeypatch.setattr(
            "src.app.is_within_submission_window", lambda group_id: False
        )
        get_or_create_current_week(group_id=GROUP_ID)
        player = _get_player()

        _nudge_shadow_if_missing_pick(
            player, "Shelbourne 4/7", GROUP_ID, now=THURSDAY_EVENING
        )

        assert mock_send_message == []

    def test_no_nudge_without_shadow_group_configured(
        self, monkeypatch, mock_send_message
    ):
        monkeypatch.setattr("src.config.Config.SHADOW_GROUP_ID", "")
        monkeypatch.setattr(
            "src.app.is_within_submission_window", lambda group_id: True
        )
        get_or_create_current_week(group_id=GROUP_ID)
        player = _get_player()

        _nudge_shadow_if_missing_pick(
            player, "Shelbourne 4/7", GROUP_ID, now=THURSDAY_EVENING
        )

        assert mock_send_message == []


class TestEmojiGuardCallsNudge:
    def test_emoji_guard_drop_triggers_nudge(self, monkeypatch):
        """handle_pick's emoji-guard branch must invoke the nudge helper."""
        from src.app import app as flask_app, handle_pick
        from src.parsers.message_parser import parse_message

        monkeypatch.setattr("src.config.Config.TEST_MODE", False)
        nudged = []
        monkeypatch.setattr(
            "src.app._nudge_shadow_if_missing_pick",
            lambda player, raw, group_id, now=None: nudged.append((player["nickname"], raw)),
        )

        parsed = parse_message("Shelbourne 4/7", "Kev", "")
        assert parsed["type"] == "pick"

        with flask_app.test_request_context():
            reply = handle_pick(parsed)

        assert reply is None
        assert nudged == [("Kev", "Shelbourne 4/7")]
