"""
Tests for webhook error handling: an unhandled exception in a message
handler must not turn into a silent 500 — the webhook should respond
cleanly and fire a Telegram alert so the failure is visible.
"""

import pytest

from src.app import app as flask_app

GROUP_ID = "test-group@g.us"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", GROUP_ID)
    monkeypatch.setattr("src.config.Config.GROUP_CHAT_IDS", [])
    monkeypatch.setattr("src.config.Config.SHADOW_GROUP_ID", "")
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def alerts(monkeypatch):
    captured = []
    monkeypatch.setattr("src.app.send_alert", lambda msg: captured.append(msg))
    return captured


class TestWebhookErrorHandling:
    def test_handler_exception_returns_error_response_not_500(
        self, client, monkeypatch, alerts
    ):
        def boom(parsed):
            raise RuntimeError("boom")

        monkeypatch.setattr("src.app.handle_command", boom)

        resp = client.post(
            "/webhook",
            json={"sender": "Kev", "body": "!help", "group_id": GROUP_ID},
        )

        assert resp.status_code == 200
        assert resp.get_json()["action"] == "error"

    def test_handler_exception_sends_alert_with_context(
        self, client, monkeypatch, alerts
    ):
        def boom(parsed):
            raise RuntimeError("boom")

        monkeypatch.setattr("src.app.handle_command", boom)

        client.post(
            "/webhook",
            json={"sender": "Kev", "body": "!help", "group_id": GROUP_ID},
        )

        assert len(alerts) == 1
        assert "Kev" in alerts[0]
        assert "!help" in alerts[0]

    def test_healthy_message_does_not_alert(self, client, alerts):
        resp = client.post(
            "/webhook",
            json={"sender": "Kev", "body": "morning lads", "group_id": GROUP_ID},
        )

        assert resp.status_code == 200
        assert alerts == []
