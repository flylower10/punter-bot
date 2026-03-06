"""Tests for _cmd_confirm penalty confirmation UX."""

from src.app import _cmd_confirm
from src.services.penalty_service import suggest_penalty, get_pending_penalties
from src.services.player_service import get_all_players
from src.services.week_service import get_or_create_current_week


def _admin_parsed(sender="Ed"):
    """Return a parsed dict for an admin sender."""
    return {"sender": sender, "sender_phone": ""}


def _non_admin_parsed():
    return {"sender": "RandomPerson", "sender_phone": ""}


def _setup_penalty(nickname="DA"):
    """Suggest a penalty for the given player and return (player, penalty)."""
    week = get_or_create_current_week()
    players = get_all_players()
    player = next(p for p in players if p["nickname"] == nickname)
    penalty = suggest_penalty(player["id"], week["id"], "streak_3")
    return player, penalty


class TestConfirmShorthand:
    """!confirm [player] works without the 'penalty' keyword."""

    def test_confirm_by_nickname(self):
        _setup_penalty("DA")
        result = _cmd_confirm(_admin_parsed(), ["DA"])
        assert "penalty" not in result.lower() or "confirmed" in result.lower() or "Mr Declan" in result

    def test_confirm_by_real_name(self):
        _setup_penalty("DA")
        result = _cmd_confirm(_admin_parsed(), ["Declan"])
        assert "No player found" not in result
        assert "No pending penalty" not in result

    def test_confirm_by_name_case_insensitive(self):
        _setup_penalty("DA")
        result = _cmd_confirm(_admin_parsed(), ["declan"])
        assert "No player found" not in result
        assert "No pending penalty" not in result

    def test_confirm_by_nickname_case_insensitive(self):
        _setup_penalty("DA")
        result = _cmd_confirm(_admin_parsed(), ["da"])
        assert "No player found" not in result
        assert "No pending penalty" not in result


class TestConfirmWithKeyword:
    """!confirm penalty [player] still works (backwards compatible)."""

    def test_confirm_penalty_nickname(self):
        _setup_penalty("DA")
        result = _cmd_confirm(_admin_parsed(), ["penalty", "DA"])
        assert "No player found" not in result
        assert "No pending penalty" not in result

    def test_confirm_penalty_real_name(self):
        _setup_penalty("DA")
        result = _cmd_confirm(_admin_parsed(), ["penalty", "Declan"])
        assert "No player found" not in result
        assert "No pending penalty" not in result


class TestConfirmNoArgs:
    """!confirm with no args lists pending penalties."""

    def test_no_args_no_pending(self):
        result = _cmd_confirm(_admin_parsed(), [])
        assert "No penalties awaiting confirmation" in result

    def test_no_args_with_pending(self):
        _setup_penalty("DA")
        result = _cmd_confirm(_admin_parsed(), [])
        assert "Pending penalties:" in result
        assert "Mr Declan" in result

    def test_penalty_keyword_only_lists_pending(self):
        _setup_penalty("DA")
        result = _cmd_confirm(_admin_parsed(), ["penalty"])
        assert "Pending penalties:" in result
        assert "Mr Declan" in result


class TestConfirmErrors:
    """Error messages are clear and helpful."""

    def test_nonexistent_player(self):
        result = _cmd_confirm(_admin_parsed(), ["Ghostface"])
        assert "No player found matching 'Ghostface'" in result

    def test_no_pending_penalty_for_valid_player(self):
        result = _cmd_confirm(_admin_parsed(), ["DA"])
        assert "No pending penalty found for Mr Declan" in result

    def test_non_admin_rejected(self):
        _setup_penalty("DA")
        result = _cmd_confirm(_non_admin_parsed(), ["DA"])
        assert "Only an admin" in result
