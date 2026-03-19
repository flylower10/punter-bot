"""Tests for pick_service."""

from datetime import datetime, timedelta

from src.db import get_db
from src.services.pick_service import (
    submit_pick, get_picks_for_week, get_missing_players, all_picks_in, get_player_pick,
)
from src.services.player_service import get_all_players
from src.services.week_service import get_or_create_current_week


class TestSubmitPick:
    def test_submit_new_pick(self):
        week = get_or_create_current_week()
        players = get_all_players()
        player = players[0]

        pick, is_update, changed, _ = submit_pick(
            player_id=player["id"],
            week_id=week["id"],
            description="Man Utd to win",
            odds_decimal=3.0,
            odds_original="2/1",
            bet_type="win",
        )

        assert pick is not None
        assert pick["description"] == "Man Utd to win"
        assert pick["odds_original"] == "2/1"
        assert is_update is False
        assert changed is True

    def test_submit_pick_update(self):
        week = get_or_create_current_week()
        players = get_all_players()
        player = players[0]

        submit_pick(player["id"], week["id"], "Man Utd", 3.0, "2/1", "win")
        pick, is_update, changed, _ = submit_pick(player["id"], week["id"], "Arsenal", 2.5, "6/4", "win")

        assert pick["description"] == "Arsenal"
        assert pick["odds_original"] == "6/4"
        assert is_update is True
        assert changed is True

    def test_submit_pick_unchanged_resubmission(self):
        """Re-submitting same pick returns changed=False."""
        week = get_or_create_current_week()
        players = get_all_players()
        player = players[0]

        submit_pick(player["id"], week["id"], "Man Utd 2/1", 3.0, "2/1", "win")
        pick, is_update, changed, _ = submit_pick(player["id"], week["id"], "Man Utd 2/1", 3.0, "2/1", "win")

        assert is_update is True
        assert changed is False


class TestGetPicks:
    def test_get_picks_for_week(self):
        week = get_or_create_current_week()
        players = get_all_players()

        submit_pick(players[0]["id"], week["id"], "Pick 1", 2.0, "evens", "win")
        submit_pick(players[1]["id"], week["id"], "Pick 2", 3.0, "2/1", "win")

        picks = get_picks_for_week(week["id"])
        assert len(picks) == 2

    def test_get_missing_players(self):
        week = get_or_create_current_week()
        players = get_all_players()

        # Submit for first 2 players
        submit_pick(players[0]["id"], week["id"], "Pick 1", 2.0, "evens", "win")
        submit_pick(players[1]["id"], week["id"], "Pick 2", 3.0, "2/1", "win")

        missing = get_missing_players(week["id"])
        assert len(missing) == 4  # 6 total - 2 submitted

    def test_all_picks_in(self):
        week = get_or_create_current_week()
        players = get_all_players()

        # Submit for all players
        for i, player in enumerate(players):
            submit_pick(player["id"], week["id"], f"Pick {i}", 2.0, "evens", "win")

        assert all_picks_in(week["id"]) is True

    def test_not_all_picks_in(self):
        week = get_or_create_current_week()
        players = get_all_players()

        submit_pick(players[0]["id"], week["id"], "Pick 1", 2.0, "evens", "win")

        assert all_picks_in(week["id"]) is False

    def test_get_player_pick(self):
        week = get_or_create_current_week()
        players = get_all_players()

        submit_pick(players[0]["id"], week["id"], "Arsenal BTTS", 2.5, "6/4", "btts")

        pick = get_player_pick(week["id"], players[0]["id"])
        assert pick is not None
        assert pick["description"] == "Arsenal BTTS"

    def test_get_player_pick_none(self):
        week = get_or_create_current_week()
        players = get_all_players()

        pick = get_player_pick(week["id"], players[0]["id"])
        assert pick is None


class TestCrossSportFallback:
    """Cross-sport fixture fallback: football-default picks match non-football fixtures."""

    def _insert_fixture(self, sport, home_team, away_team, api_id=99999):
        """Insert a fixture into the DB for matching."""
        conn = get_db()
        kickoff = (datetime.utcnow() + timedelta(days=1)).isoformat()
        conn.execute(
            """INSERT OR REPLACE INTO fixtures
               (api_id, sport, competition, home_team, away_team,
                kickoff, status, fetched_at, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, 'NS', ?, '{}')""",
            (api_id, sport, "Six Nations", home_team, away_team,
             kickoff, datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()

    def test_football_default_matches_rugby_fixture(self):
        """A pick like 'Ireland -26' defaults to football, but should match a rugby fixture."""
        self._insert_fixture("rugby", "Ireland", "Italy")

        week = get_or_create_current_week()
        players = get_all_players()
        player = players[0]

        pick, _, _, _ = submit_pick(
            player_id=player["id"],
            week_id=week["id"],
            description="Ireland",
            odds_decimal=1.5,
            odds_original="1/2",
            bet_type="handicap",
            sport="football",  # default detection
        )

        assert pick["sport"] == "rugby"
        assert pick["api_fixture_id"] == 99999

    def test_no_fallback_when_football_matches(self):
        """When a football fixture matches, no cross-sport fallback needed."""
        self._insert_fixture("football", "Ireland", "Wales", api_id=11111)
        self._insert_fixture("rugby", "Ireland", "Italy", api_id=22222)

        week = get_or_create_current_week()
        players = get_all_players()
        player = players[0]

        pick, _, _, _ = submit_pick(
            player_id=player["id"],
            week_id=week["id"],
            description="Ireland",
            odds_decimal=2.0,
            odds_original="evens",
            bet_type="win",
            sport="football",
        )

        # Should match the football fixture, not the rugby one
        assert pick["sport"] == "football"
        assert pick["api_fixture_id"] == 11111
