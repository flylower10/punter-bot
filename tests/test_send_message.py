"""
Tests for send_message bridge delivery: retry on connection errors and
alerting on final failure so group messages are never silently dropped.
"""

import json

import pytest
import requests

# Direct reference to the real function — immune to any autouse mock that
# replaces the src.app module attribute.
from src.app import send_message


class FakeResponse:
    def __init__(self, status_code, body=""):
        self.status_code = status_code
        self.text = body

    def json(self):
        return json.loads(self.text)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Retry backoff must not slow the test suite down."""
    monkeypatch.setattr("time.sleep", lambda s: None)


@pytest.fixture
def alerts(monkeypatch):
    """Capture Telegram alerts fired from src.app."""
    captured = []
    monkeypatch.setattr("src.app.send_alert", lambda msg: captured.append(msg))
    return captured


class TestSendMessageRetries:
    def test_sends_once_on_success(self, monkeypatch, alerts):
        calls = []
        monkeypatch.setattr(
            requests, "post", lambda *a, **kw: calls.append(a) or FakeResponse(200)
        )

        send_message("chat@g.us", "hello")

        assert len(calls) == 1
        assert alerts == []

    def test_retries_on_connection_error_then_succeeds(self, monkeypatch, alerts):
        calls = []

        def flaky(*a, **kw):
            calls.append(a)
            if len(calls) < 3:
                raise requests.ConnectionError("bridge down")
            return FakeResponse(200)

        monkeypatch.setattr(requests, "post", flaky)

        send_message("chat@g.us", "hello")

        assert len(calls) == 3
        assert alerts == []

    def test_retries_on_503_with_retry_flag(self, monkeypatch, alerts):
        calls = []

        def reconnecting(*a, **kw):
            calls.append(a)
            if len(calls) < 2:
                return FakeResponse(503, '{"retry": true}')
            return FakeResponse(200)

        monkeypatch.setattr(requests, "post", reconnecting)

        send_message("chat@g.us", "hello")

        assert len(calls) == 2
        assert alerts == []


class TestSendMessageAlerts:
    def test_alerts_when_all_retries_fail(self, monkeypatch, alerts):
        def always_fail(*a, **kw):
            raise requests.ConnectionError("bridge down")

        monkeypatch.setattr(requests, "post", always_fail)

        send_message("chat123@g.us", "hello")

        assert len(alerts) == 1
        assert "chat123@g.us" in alerts[0]

    def test_alerts_on_bridge_error_status(self, monkeypatch, alerts):
        monkeypatch.setattr(
            requests, "post", lambda *a, **kw: FakeResponse(500, "boom")
        )

        send_message("chat@g.us", "hello")

        assert len(alerts) == 1
