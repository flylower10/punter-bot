"""Integration tests for emoji-based cumulative pick submission via webhook."""

import pytest

from src.db import get_db
from src.parsers.message_parser import parse_cumulative_picks
from src.services.player_service import get_emoji_to_player_map
from src.services.pick_service import get_picks_for_week
from src.services.week_service import get_or_create_current_week, is_within_submission_window


def _seed_player_emojis():
    """Add emojis to seeded players for cumulative pick tests."""
    conn = get_db()
    emojis = {
        "Ed": "🍋,🍋🍋🍋",
        "Kev": "🧌",
        "DA": "👴🏻",
        "Nug": "🍗",
        "Nialler": "🔫",
        "Pawn": "♟️",
    }
    for nickname, emoji in emojis.items():
        conn.execute("UPDATE players SET emoji = ? WHERE nickname = ?", (emoji, nickname))
    conn.commit()
    conn.close()


class TestCumulativePickWebhook:
    """Test cumulative emoji+pick format through the webhook."""

    def test_webhook_parses_and_stores_cumulative_picks(self, test_db, monkeypatch):
        """POST cumulative message to webhook; verify all picks stored."""
        _seed_player_emojis()
        monkeypatch.setattr(
            "src.app.is_within_submission_window",
            lambda: True,
        )
        monkeypatch.setattr(
            "src.config.Config.GROUP_CHAT_ID",
            "test-group@g.us",
        )

        from src.app import create_app

        app = create_app()
        client = app.test_client()

        # Cumulative message: Pawn, Kev, Ed picks
        body = (
            "♟️ Dortmund to beat Mainz 6/10\n"
            "🧌 Liverpool to win 2/1\n"
            "🍋 Man City Brentford BTTS 8/11"
        )

        resp = client.post(
            "/webhook",
            json={
                "sender": "Aidan",
                "sender_phone": "",
                "body": body,
                "group_id": "test-group@g.us",
                "has_media": False,
            },
            content_type="application/json",
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "replied"
        assert "Noted and recorded" in data["reply"] or "Updated" in data["reply"]

        week = get_or_create_current_week()
        picks = get_picks_for_week(week["id"])
        assert len(picks) == 3

        descriptions = {p["description"]: p["nickname"] for p in picks}
        assert "Dortmund to beat Mainz 6/10" in descriptions
        assert descriptions["Dortmund to beat Mainz 6/10"] == "Pawn"
        assert "Liverpool to win 2/1" in descriptions
        assert descriptions["Liverpool to win 2/1"] == "Kev"
        assert "Man City Brentford BTTS 8/11" in descriptions
        assert descriptions["Man City Brentford BTTS 8/11"] == "Ed"

    def test_cumulative_only_acknowledges_new_picks(self, test_db, monkeypatch):
        """When adding a pick to an existing thread, only acknowledge the new pick."""
        _seed_player_emojis()
        monkeypatch.setattr("src.app.is_within_submission_window", lambda: True)
        monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", "test-group@g.us")

        from src.app import create_app
        from src.services.pick_service import submit_pick
        from src.services.week_service import get_or_create_current_week
        from src.services.player_service import get_all_players

        app = create_app()
        client = app.test_client()

        # First: submit Pawn and Kev picks
        week = get_or_create_current_week()
        players = get_all_players()
        pawn = next(p for p in players if p["nickname"] == "Pawn")
        kev = next(p for p in players if p["nickname"] == "Kev")
        ed = next(p for p in players if p["nickname"] == "Ed")

        submit_pick(pawn["id"], week["id"], "Dortmund 6/10", 1.6, "6/10", "win")
        submit_pick(kev["id"], week["id"], "Liverpool 2/1", 3.0, "2/1", "win")

        # Second: cumulative message with existing picks + Ed's new pick
        body = (
            "♟️ Dortmund 6/10\n"
            "🧌 Liverpool 2/1\n"
            "🍋 Man City BTTS 8/11"
        )
        resp = client.post(
            "/webhook",
            json={
                "sender": "Aidan",
                "sender_phone": "",
                "body": body,
                "group_id": "test-group@g.us",
                "has_media": False,
            },
            content_type="application/json",
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "replied"
        # Should only acknowledge Ed's new pick, not Pawn/Kev re-submissions
        assert "Mr Edmund" in data["reply"]
        assert "Manchester City BTTS" in data["reply"]  # Formal display (Man City -> Manchester City)
        assert "Master" not in data["reply"]  # Pawn not re-acknowledged
        assert "Mr Kevin" not in data["reply"]  # Kev not re-acknowledged

    def test_parse_cumulative_with_emoji_map(self, test_db):
        """parse_cumulative_picks extracts picks when players have emojis."""
        _seed_player_emojis()
        emoji_map = get_emoji_to_player_map()

        assert "♟️" in emoji_map
        assert "🍋" in emoji_map
        assert "🍋🍋🍋" in emoji_map

        text = "♟️ Dortmund 6/10\n🧌 Liverpool 2/1"
        results = parse_cumulative_picks(text, emoji_map)

        assert len(results) == 2
        assert results[0][0]["nickname"] == "Pawn"
        assert results[0][1]["odds_original"] == "6/10"
        assert results[1][0]["nickname"] == "Kev"
        assert results[1][1]["odds_original"] == "2/1"
