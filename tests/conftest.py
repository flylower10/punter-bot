"""
Shared test fixtures for service tests.

Sets up a temporary SQLite database with the schema and seeded players
before each test, and cleans up afterward.
"""

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def test_db(monkeypatch):
    """Create a fresh temporary database for each test."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    monkeypatch.setattr("src.config.Config.DB_PATH", db_path)
    monkeypatch.setattr("src.config.Config.TIMEZONE", "Europe/Dublin")
    monkeypatch.setattr("src.config.Config.TEST_MODE", True)
    monkeypatch.setattr("src.config.Config.ROTATION_ORDER", [])  # Use DB rotation_position
    monkeypatch.setattr("src.config.Config.LLM_ENABLED", False)
    monkeypatch.setattr("src.config.Config.GROQ_API_KEY", "")
    monkeypatch.setattr("src.config.Config.API_FOOTBALL_KEY", "")
    monkeypatch.setattr("src.config.Config.ODDS_API_KEY", "")

    from src.db import init_db
    init_db()

    yield db_path

    os.unlink(db_path)


@pytest.fixture(autouse=True)
def mock_send_message(monkeypatch):
    """Capture outgoing bridge messages instead of hitting the network.

    Without this, any webhook test that produces a reply spends ~3s in
    send_message retrying against a bridge that isn't running.
    Tests for send_message itself import the real function directly,
    so this patch doesn't affect them.
    """
    sent = []
    monkeypatch.setattr(
        "src.app.send_message", lambda chat_id, text: sent.append((chat_id, text))
    )
    return sent
