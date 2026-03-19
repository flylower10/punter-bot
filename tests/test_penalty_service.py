"""Tests for penalty_service."""

from src.services.penalty_service import (
    suggest_penalty, confirm_penalty, get_pending_penalties,
    get_pending_penalty_for_player_id,
    get_vault_total,
)
from src.services.player_service import get_all_players
from src.services.week_service import get_or_create_current_week


class TestSuggestPenalty:
    def test_suggest_streak_penalty(self):
        week = get_or_create_current_week()
        players = get_all_players()

        penalty = suggest_penalty(players[0]["id"], week["id"], "streak_3")
        assert penalty["type"] == "streak_3"
        assert penalty["status"] == "suggested"
        assert penalty["amount"] == 0

    def test_suggest_streak_5_penalty(self):
        week = get_or_create_current_week()
        players = get_all_players()

        penalty = suggest_penalty(players[0]["id"], week["id"], "streak_5")
        assert penalty["amount"] == 50

    def test_duplicate_penalty_returns_existing(self):
        week = get_or_create_current_week()
        players = get_all_players()

        p1 = suggest_penalty(players[0]["id"], week["id"], "streak_3")
        p2 = suggest_penalty(players[0]["id"], week["id"], "streak_3")
        assert p1["id"] == p2["id"]


class TestConfirmPenalty:
    def test_confirm_penalty(self):
        week = get_or_create_current_week()
        players = get_all_players()

        penalty = suggest_penalty(players[0]["id"], week["id"], "streak_5")
        result = confirm_penalty(penalty["id"], confirmed_by="Ed")

        assert result is not None
        confirmed, vault_total = result
        assert confirmed["status"] == "confirmed"
        assert vault_total == 50

    def test_confirm_zero_amount_penalty(self):
        week = get_or_create_current_week()
        players = get_all_players()

        penalty = suggest_penalty(players[0]["id"], week["id"], "streak_3")
        result = confirm_penalty(penalty["id"], confirmed_by="Ed")

        confirmed, vault_total = result
        assert confirmed["status"] == "confirmed"
        assert vault_total == 0  # No vault entry for streak_3

    def test_confirm_nonexistent_penalty(self):
        result = confirm_penalty(999)
        assert result is None


class TestPendingPenalties:
    def test_get_pending_penalties(self):
        week = get_or_create_current_week()
        players = get_all_players()

        suggest_penalty(players[0]["id"], week["id"], "streak_3")
        suggest_penalty(players[1]["id"], week["id"], "streak_5")

        pending = get_pending_penalties()
        assert len(pending) == 2

    def test_confirmed_not_in_pending(self):
        week = get_or_create_current_week()
        players = get_all_players()

        p1 = suggest_penalty(players[0]["id"], week["id"], "streak_3")
        suggest_penalty(players[1]["id"], week["id"], "streak_5")
        confirm_penalty(p1["id"])

        pending = get_pending_penalties()
        assert len(pending) == 1


    def test_get_pending_for_player_id(self):
        week = get_or_create_current_week()
        players = get_all_players()

        suggest_penalty(players[0]["id"], week["id"], "streak_3")

        penalty = get_pending_penalty_for_player_id(players[0]["id"])
        assert penalty is not None
        assert penalty["type"] == "streak_3"

    def test_get_pending_for_unknown_player_id(self):
        penalty = get_pending_penalty_for_player_id(999)
        assert penalty is None


class TestVault:
    def test_vault_starts_at_zero(self):
        assert get_vault_total() == 0

    def test_vault_accumulates(self):
        week = get_or_create_current_week()
        players = get_all_players()

        p1 = suggest_penalty(players[0]["id"], week["id"], "streak_5")  # 50
        p2 = suggest_penalty(players[1]["id"], week["id"], "streak_7")  # 100
        confirm_penalty(p1["id"])
        confirm_penalty(p2["id"])

        assert get_vault_total() == 150
