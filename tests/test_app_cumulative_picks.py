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

        week = get_or_create_current_week(group_id="test-group@g.us")
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
        week = get_or_create_current_week(group_id="test-group@g.us")
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
        assert "Mr Aidan" not in data["reply"]  # Pawn not re-acknowledged
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

    def test_cumulative_accepts_bare_team_names(self, test_db, monkeypatch):
        """Bare team names like 'Villa' in cumulative format are accepted (emoji = pick context)."""
        _seed_player_emojis()
        monkeypatch.setattr("src.app.is_within_submission_window", lambda: True)
        monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", "test-group@g.us")

        from src.app import create_app

        app = create_app()
        client = app.test_client()

        body = (
            "♟️ Villa\n"
            "🔫 QPR 21/20\n"
            "👴🏻 Scotland + 8\n"
            "🍗 Wales +32.5 10/11\n"
            "🍋🍋🍋 leics/Soton BTTS 4/6\n"
            "🧌 Ireland -16 🏉"
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

        week = get_or_create_current_week(group_id="test-group@g.us")
        picks = get_picks_for_week(week["id"])
        descriptions = {p["nickname"]: p["description"] for p in picks}

        assert descriptions["Pawn"] == "Villa"
        assert descriptions["Nialler"] == "QPR 21/20"
        assert "Scotland + 8" in descriptions["DA"]
        assert "Wales +32.5 10/11" in descriptions["Nug"]
        assert "leics/Soton BTTS 4/6" in descriptions["Ed"]
        assert "Ireland -16" in descriptions["Kev"]

    def test_cumulative_replacement_pick_detected(self, test_db, monkeypatch):
        """When changing pick (e.g. Dortmund -> Villa), cumulative message updates correctly."""
        _seed_player_emojis()
        monkeypatch.setattr("src.app.is_within_submission_window", lambda: True)
        monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", "test-group@g.us")

        from src.app import create_app
        from src.services.pick_service import submit_pick
        from src.services.week_service import get_or_create_current_week
        from src.services.player_service import get_all_players

        app = create_app()
        client = app.test_client()

        # First: Pawn had Dortmund
        week = get_or_create_current_week(group_id="test-group@g.us")
        players = get_all_players()
        pawn = next(p for p in players if p["nickname"] == "Pawn")
        submit_pick(pawn["id"], week["id"], "Dortmund 6/10", 1.6, "6/10", "win")

        # User sends cumulative message with Villa (Dortmund had started)
        body = (
            "♟️ Villa\n"
            "🔫 QPR 21/20\n"
            "👴🏻 Scotland + 8\n"
            "🍗 Wales +32.5 10/11\n"
            "🍋🍋🍋 leics/Soton BTTS 4/6\n"
            "🧌 Ireland -16"
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
        picks = get_picks_for_week(week["id"])
        pawn_pick = next(p for p in picks if p["nickname"] == "Pawn")
        assert pawn_pick["description"] == "Villa"

    def test_placer_screenshot_records_bet_placed(self, test_db, monkeypatch):
        """When next placer posts a screenshot (all picks in), record bet as placed."""
        _seed_player_emojis()
        monkeypatch.setattr("src.app.is_within_submission_window", lambda: True)
        monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", "test-group@g.us")

        from src.app import create_app
        from src.services.week_service import get_or_create_current_week
        from src.services.rotation_service import get_next_placer
        from src.services.pick_service import submit_pick
        from src.services.player_service import get_all_players

        app = create_app()
        client = app.test_client()

        week = get_or_create_current_week(group_id="test-group@g.us")
        players = get_all_players()

        # Submit all 6 picks so "all picks in"
        for p in players:
            submit_pick(p["id"], week["id"], f"{p['nickname']} pick 2/1", 3.0, "2/1", "win")

        # Kev is next (no history)
        placer = get_next_placer()
        assert placer["nickname"] == "Kev"

        # Kev posts screenshot (has_media, TEST_MODE prefix for sender)
        resp = client.post(
            "/webhook",
            json={
                "sender": "Kevin",
                "sender_phone": "",
                "body": "Kev: ",  # Caption with prefix; could be empty
                "group_id": "test-group@g.us",
                "has_media": True,
            },
            content_type="application/json",
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "replied"
        assert "Mr Kevin" in data["reply"]
        assert "Bet slip received" in data["reply"]

        # Complete week so get_next_placer uses it; Nialler should be next
        from src.db import get_db
        conn = get_db()
        conn.execute("UPDATE weeks SET status = 'completed' WHERE id = ?", (week["id"],))
        conn.commit()
        conn.close()

        next_placer = get_next_placer()
        assert next_placer["nickname"] == "Nialler"

    def test_placer_text_confirmation_records_bet_placed(self, test_db, monkeypatch):
        """When next placer posts text like 'placed' or 'bet slip' (no media), also record."""
        _seed_player_emojis()
        monkeypatch.setattr("src.app.is_within_submission_window", lambda: True)
        monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", "test-group@g.us")

        from src.app import create_app
        from src.services.week_service import get_or_create_current_week
        from src.services.rotation_service import get_next_placer
        from src.services.pick_service import submit_pick
        from src.services.player_service import get_all_players

        app = create_app()
        client = app.test_client()

        week = get_or_create_current_week(group_id="test-group@g.us")
        players = get_all_players()

        for p in players:
            submit_pick(p["id"], week["id"], f"{p['nickname']} pick 2/1", 3.0, "2/1", "win")

        placer = get_next_placer()
        assert placer["nickname"] == "Kev"

        # Kev posts "placed" (no image - e.g. forwarded msg, doc, or plain text)
        resp = client.post(
            "/webhook",
            json={
                "sender": "Kevin",
                "sender_phone": "",
                "body": "Kev: placed",
                "group_id": "test-group@g.us",
                "has_media": False,
            },
            content_type="application/json",
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "replied"
        assert "Mr Kevin" in data["reply"]
        assert "Bet slip received" in data["reply"]

    def test_admin_forwarding_placer_screenshot_records_bet(self, test_db, monkeypatch):
        """When Ed forwards the placer's screenshot, record the bet as placed."""
        _seed_player_emojis()
        monkeypatch.setattr("src.app.is_within_submission_window", lambda: True)
        monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", "test-group@g.us")

        from src.app import create_app
        from src.services.week_service import get_or_create_current_week
        from src.services.rotation_service import get_next_placer
        from src.services.pick_service import submit_pick
        from src.services.player_service import get_all_players

        app = create_app()
        client = app.test_client()

        week = get_or_create_current_week(group_id="test-group@g.us")
        players = get_all_players()

        for p in players:
            submit_pick(p["id"], week["id"], f"{p['nickname']} pick 2/1", 3.0, "2/1", "win")

        placer = get_next_placer()
        assert placer["nickname"] == "Kev"

        # Ed reposts/forwards the placer's screenshot (sender is Ed, not Kev)
        resp = client.post(
            "/webhook",
            json={
                "sender": "Edmund",
                "sender_phone": "",
                "body": "Ed: ",
                "group_id": "test-group@g.us",
                "has_media": True,
            },
            content_type="application/json",
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "replied"
        assert "Mr Kevin" in data["reply"]
        assert "Bet slip received" in data["reply"]


class TestPickUpdateGuardrails:
    """Test that single-message picks are rejected when the player already has a pick."""

    def test_single_message_accepted_when_no_existing_pick(self, test_db, monkeypatch):
        """A player with no pick can submit via single message (no emoji prefix)."""
        monkeypatch.setattr("src.app.is_within_submission_window", lambda: True)
        monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", "test-group@g.us")

        from src.app import create_app

        app = create_app()
        client = app.test_client()

        resp = client.post(
            "/webhook",
            json={
                "sender": "Ronan",
                "sender_phone": "",
                "body": "Bournemouth 4/5",
                "group_id": "test-group@g.us",
                "has_media": False,
            },
            content_type="application/json",
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "replied"

        week = get_or_create_current_week(group_id="test-group@g.us")
        picks = get_picks_for_week(week["id"])
        assert len(picks) == 1
        assert picks[0]["nickname"] == "Nug"

    def test_single_message_ignored_when_player_has_pick(self, test_db, monkeypatch):
        """A player who already has a pick is ignored on single message (no emoji prefix)."""
        monkeypatch.setattr("src.app.is_within_submission_window", lambda: True)
        monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", "test-group@g.us")

        from src.app import create_app
        from src.services.pick_service import submit_pick
        from src.services.player_service import get_all_players

        app = create_app()
        client = app.test_client()

        # Pre-submit a pick for Nug
        week = get_or_create_current_week(group_id="test-group@g.us")
        players = get_all_players()
        nug = next(p for p in players if p["nickname"] == "Nug")
        submit_pick(nug["id"], week["id"], "Bournemouth 4/5", 1.8, "4/5", "win")

        # Now Nug sends a chat message that looks like a pick
        resp = client.post(
            "/webhook",
            json={
                "sender": "Ronan",
                "sender_phone": "",
                "body": "Arsenal 6/4",
                "group_id": "test-group@g.us",
                "has_media": False,
            },
            content_type="application/json",
        )

        assert resp.status_code == 200
        data = resp.get_json()
        # Should be silently dropped — treated as chat, no reply
        assert data["action"] == "no_reply"

        # Pick should remain unchanged
        picks = get_picks_for_week(week["id"])
        nug_pick = next(p for p in picks if p["nickname"] == "Nug")
        assert nug_pick["description"] == "Bournemouth 4/5"

    def test_emoji_prefix_update_accepted_when_player_has_pick(self, test_db, monkeypatch):
        """A player who already has a pick can update via emoji prefix (cumulative path)."""
        _seed_player_emojis()
        monkeypatch.setattr("src.app.is_within_submission_window", lambda: True)
        monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", "test-group@g.us")

        from src.app import create_app
        from src.services.pick_service import submit_pick
        from src.services.player_service import get_all_players

        app = create_app()
        client = app.test_client()

        # Pre-submit a pick for Nug
        week = get_or_create_current_week(group_id="test-group@g.us")
        players = get_all_players()
        nug = next(p for p in players if p["nickname"] == "Nug")
        submit_pick(nug["id"], week["id"], "Bournemouth 4/5", 1.8, "4/5", "win")

        # Nug sends emoji-prefixed update
        resp = client.post(
            "/webhook",
            json={
                "sender": "Nugent",
                "sender_phone": "",
                "body": "\U0001F357 Arsenal 6/4",
                "group_id": "test-group@g.us",
                "has_media": False,
            },
            content_type="application/json",
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "replied"
        assert "Updated" in data["reply"]

        # Pick should be updated
        picks = get_picks_for_week(week["id"])
        nug_pick = next(p for p in picks if p["nickname"] == "Nug")
        assert nug_pick["description"] == "Arsenal 6/4"
