"""
Regression tests for submission window enforcement.

Live failure: general chat after Friday 10pm was classified as a pick,
triggering a visible 'submission window is currently closed' reply to the
group. Root cause: TEST_MODE bypasses all window checks in existing tests,
so the classification → window check path was never exercised.

These tests set TEST_MODE=False and patch is_within_submission_window
to test enforcement in isolation from the real clock.
"""

import pytest

from src.services.player_service import get_all_players
from src.services.pick_service import submit_pick
from src.services.week_service import get_or_create_current_week


GROUP_ID = "test-group@g.us"


@pytest.fixture
def enforcement_client(monkeypatch):
    """
    Flask test client with window enforcement active (TEST_MODE=False).

    The conftest sets TEST_MODE=True for all tests. This fixture overrides
    it so the window check and emoji guard fire as they do in production.
    Seeded players have no emoji, so the emoji guard passes for all messages.
    """
    monkeypatch.setattr("src.config.Config.TEST_MODE", False)
    monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", GROUP_ID)
    monkeypatch.setattr("src.config.Config.GROUP_CHAT_IDS", [])
    monkeypatch.setattr("src.config.Config.SHADOW_GROUP_ID", "")
    monkeypatch.setattr("src.app.send_message", lambda *a, **kw: None)
    from src.app import app as flask_app
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def _post(client, body, sender="Kev"):
    return client.post("/webhook", json={
        "sender": sender,
        "sender_phone": "",
        "body": body,
        "group_id": GROUP_ID,
    })


class TestWindowClosed:
    """Outside the submission window (is_within_submission_window returns False)."""

    def test_real_pick_outside_window_returns_window_closed(self, enforcement_client, monkeypatch):
        """
        A pick with the player's emoji outside the window must get a 'window closed' reply.
        The emoji is required in production mode — without it the emoji guard fires first
        and silently ignores the message.
        """
        monkeypatch.setattr(
            "src.app.is_within_submission_window",
            lambda group_id="default": False,
        )
        # Kev's emoji is 🧌 (seeded in db.py). Include it so the emoji guard passes.
        resp = _post(enforcement_client, "🧌 Liverpool 2/1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "replied"
        assert "window" in data["reply"].lower()

    def test_general_chat_outside_window_produces_no_reply(self, enforcement_client, monkeypatch):
        """
        Core live failure: general chat after the Friday 10pm deadline must NOT
        produce any bot reply. Only real picks should trigger 'window closed'.
        """
        monkeypatch.setattr(
            "src.app.is_within_submission_window",
            lambda group_id="default": False,
        )
        resp = _post(enforcement_client, "Great result lads, well played")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "no_reply"

    def test_common_football_chat_outside_window_produces_no_reply(self, enforcement_client, monkeypatch):
        """
        Post-match chat like 'What a game, 2-1 to Liverpool' must not trigger
        a 'window closed' reply even though it contains score-like numbers.
        """
        monkeypatch.setattr(
            "src.app.is_within_submission_window",
            lambda group_id="default": False,
        )
        resp = _post(enforcement_client, "What a game, 2-1 to Liverpool")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "no_reply"

    def test_command_still_works_outside_window(self, enforcement_client, monkeypatch):
        """Commands like !rotation are not gated by the submission window."""
        monkeypatch.setattr(
            "src.app.is_within_submission_window",
            lambda group_id="default": False,
        )
        resp = _post(enforcement_client, "!rotation")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "replied"


class TestWindowOpen:
    """Inside the submission window — picks accepted, general chat silently ignored."""

    def test_real_pick_inside_window_accepted(self, enforcement_client, monkeypatch):
        """A pick with emoji inside the window must be accepted (no 'window closed' reply)."""
        monkeypatch.setattr(
            "src.app.is_within_submission_window",
            lambda group_id="default": True,
        )
        resp = _post(enforcement_client, "🧌 Liverpool 2/1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "window" not in (data.get("reply") or "").lower()

    def test_general_chat_inside_window_produces_no_reply(self, enforcement_client, monkeypatch):
        """General chat inside the window must also produce no reply."""
        monkeypatch.setattr(
            "src.app.is_within_submission_window",
            lambda group_id="default": True,
        )
        resp = _post(enforcement_client, "Morning lads, should be a good weekend")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "no_reply"
