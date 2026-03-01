"""Tests for auto-result service: team matching, alias resolution, pick evaluation."""

import json

from src.db import get_db
from src.services.auto_result_service import (
    _team_in_text,
    _team_in_text_with_aliases,
    _evaluate_pick,
    auto_result_fixture,
)
from src.services.pick_service import submit_pick
from src.services.player_service import get_all_players
from src.services.week_service import get_or_create_current_week
from src.services.result_service import record_result


def _insert_fixture(api_id=12345, status="FT", home="Liverpool", away="Arsenal",
                     home_score=2, away_score=1, kickoff="2026-03-01T15:00:00+00:00",
                     sport="football"):
    """Insert a fixture directly into the DB."""
    conn = get_db()
    conn.execute(
        """INSERT OR REPLACE INTO fixtures
           (api_id, sport, competition, competition_id, home_team, away_team,
            kickoff, status, home_score, away_score)
           VALUES (?, ?, 'Premier League', 39, ?, ?, ?, ?, ?, ?)""",
        (api_id, sport, home, away, kickoff, status, home_score, away_score),
    )
    conn.commit()
    conn.close()


def _insert_alias(alias, canonical, sport="football"):
    """Insert a team alias into the DB."""
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO team_aliases (alias, canonical_name, sport) VALUES (?, ?, ?)",
        (alias, canonical, sport),
    )
    conn.commit()
    conn.close()


def _setup_pick_with_fixture(player_idx=0, api_id=12345, fixture_status="FT",
                              home="Liverpool", away="Arsenal",
                              home_score=2, away_score=1,
                              description="Liverpool to win", bet_type="win",
                              sport="football"):
    """Create a week, fixture, and matched pick."""
    week = get_or_create_current_week()
    players = get_all_players()
    player = players[player_idx]

    _insert_fixture(api_id=api_id, status=fixture_status, home=home, away=away,
                    home_score=home_score, away_score=away_score, sport=sport)

    pick, _, _, _ = submit_pick(player["id"], week["id"], description, 2.0, "evens", bet_type)
    conn = get_db()
    conn.execute("UPDATE picks SET api_fixture_id = ? WHERE id = ?", (api_id, pick["id"]))
    conn.commit()
    conn.close()

    return week, player, pick


# --- Tests: _team_in_text (existing behavior) ---

class TestTeamInText:
    def test_exact_match(self):
        assert _team_in_text("Liverpool", "Liverpool to win") is True

    def test_case_insensitive(self):
        assert _team_in_text("liverpool", "LIVERPOOL to win") is True

    def test_first_word_match(self):
        assert _team_in_text("Arsenal FC", "Arsenal to beat Chelsea") is True

    def test_suffix_stripped(self):
        assert _team_in_text("Manchester United", "Manchester to win") is True

    def test_no_match(self):
        assert _team_in_text("Manchester United", "Man United 8/15") is False

    def test_short_name_no_match(self):
        assert _team_in_text("Crystal Palace", "Man United 8/15") is False


# --- Tests: _team_in_text_with_aliases ---

class TestTeamInTextWithAliases:
    def test_direct_match_no_alias_needed(self):
        assert _team_in_text_with_aliases("Liverpool", "Liverpool to win") is True

    def test_alias_resolves_man_united(self):
        _insert_alias("Man United", "Manchester United")
        assert _team_in_text_with_aliases(
            "manchester united", "Man United 8/15"
        ) is True

    def test_alias_resolves_man_utd(self):
        _insert_alias("Man Utd", "Manchester United")
        assert _team_in_text_with_aliases(
            "manchester united", "Man Utd 8/15"
        ) is True

    def test_alias_with_to_win_phrase(self):
        _insert_alias("Man United", "Manchester United")
        assert _team_in_text_with_aliases(
            "manchester united", "Man United to win 8/15"
        ) is True

    def test_alias_with_decimal_odds(self):
        _insert_alias("Man United", "Manchester United")
        assert _team_in_text_with_aliases(
            "manchester united", "Man United 1.53"
        ) is True

    def test_no_alias_no_match(self):
        """Without alias in DB, abbreviated name should not match."""
        assert _team_in_text_with_aliases(
            "manchester united", "Man United 8/15"
        ) is False

    def test_alias_wrong_team(self):
        _insert_alias("Man United", "Manchester United")
        assert _team_in_text_with_aliases(
            "crystal palace", "Man United 8/15"
        ) is False


# --- Tests: _evaluate_pick with aliases ---

class TestEvaluatePickWithAliases:
    def test_win_pick_with_alias(self):
        _insert_alias("Man United", "Manchester United")

        pick = {"description": "Man United 8/15", "bet_type": "win"}
        fixture = {
            "sport": "football",
            "home_team": "Manchester United",
            "away_team": "Crystal Palace",
            "home_score": 2, "away_score": 1,
            "status": "FT",
        }
        assert _evaluate_pick(pick, fixture) == "win"

    def test_loss_pick_with_alias(self):
        _insert_alias("Man United", "Manchester United")

        pick = {"description": "Man United 8/15", "bet_type": "win"}
        fixture = {
            "sport": "football",
            "home_team": "Manchester United",
            "away_team": "Crystal Palace",
            "home_score": 0, "away_score": 1,
            "status": "FT",
        }
        assert _evaluate_pick(pick, fixture) == "loss"

    def test_auto_result_fixture_with_alias(self):
        """End-to-end: auto_result_fixture resolves alias and produces correct result."""
        _insert_alias("Man United", "Manchester United")

        week, player, pick = _setup_pick_with_fixture(
            api_id=13792,
            description="Man United 8/15",
            home="Manchester United", away="Crystal Palace",
            home_score=2, away_score=1,
            fixture_status="FT",
        )

        announcements = auto_result_fixture(13792, week["id"])
        assert len(announcements) >= 1

        # Verify the result was recorded
        conn = get_db()
        result = conn.execute(
            "SELECT outcome FROM results WHERE pick_id = ?", (pick["id"],)
        ).fetchone()
        conn.close()
        assert result["outcome"] == "win"
