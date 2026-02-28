"""Tests for kickoff-ordered picks in all_picks_in announcement."""

from datetime import datetime

import pytz

from src.db import get_db
from src.services.pick_service import (
    submit_pick, get_picks_for_week_by_kickoff,
)
from src.services.player_service import get_all_players
from src.services.week_service import get_or_create_current_week
import src.butler as butler


def _insert_fixture(api_id, home, away, kickoff_iso):
    """Insert a fixture row for testing."""
    conn = get_db()
    conn.execute(
        "INSERT INTO fixtures (api_id, sport, competition, home_team, away_team, kickoff) "
        "VALUES (?, 'football', 'Premier League', ?, ?, ?)",
        (api_id, home, away, kickoff_iso),
    )
    conn.commit()
    conn.close()


def _link_pick_to_fixture(pick_id, api_fixture_id):
    """Set api_fixture_id on an existing pick."""
    conn = get_db()
    conn.execute(
        "UPDATE picks SET api_fixture_id = ? WHERE id = ?",
        (api_fixture_id, pick_id),
    )
    conn.commit()
    conn.close()


class TestGetPicksForWeekByKickoff:
    def test_returns_kickoff_fields(self):
        """Matched picks include kickoff, home_team, away_team from fixture join."""
        week = get_or_create_current_week()
        players = get_all_players()

        _insert_fixture(1001, "Arsenal", "Chelsea", "2026-03-07T15:00:00")
        pick, _, _, _ = submit_pick(players[0]["id"], week["id"], "Arsenal to win", 2.0, "evens", "win")
        _link_pick_to_fixture(pick["id"], 1001)

        picks = get_picks_for_week_by_kickoff(week["id"])
        assert len(picks) == 1
        assert picks[0]["kickoff"] == "2026-03-07T15:00:00"
        assert picks[0]["home_team"] == "Arsenal"
        assert picks[0]["away_team"] == "Chelsea"

    def test_unmatched_picks_have_null_kickoff(self):
        """Unmatched picks have None for kickoff/home_team/away_team."""
        week = get_or_create_current_week()
        players = get_all_players()

        submit_pick(players[0]["id"], week["id"], "Dublin to win", 2.0, "evens", "win")

        picks = get_picks_for_week_by_kickoff(week["id"])
        assert len(picks) == 1
        assert picks[0]["kickoff"] is None
        assert picks[0]["home_team"] is None
        assert picks[0]["away_team"] is None

    def test_matched_before_unmatched(self):
        """Matched picks (with kickoff) come before unmatched picks."""
        week = get_or_create_current_week()
        players = get_all_players()

        # Submit unmatched first
        submit_pick(players[0]["id"], week["id"], "Dublin to win", 2.0, "evens", "win")
        # Submit matched second
        _insert_fixture(2001, "Newcastle", "Everton", "2026-03-07T15:00:00")
        pick, _, _, _ = submit_pick(players[1]["id"], week["id"], "Newcastle to win", 1.8, "4/5", "win")
        _link_pick_to_fixture(pick["id"], 2001)

        picks = get_picks_for_week_by_kickoff(week["id"])
        assert len(picks) == 2
        assert picks[0]["home_team"] == "Newcastle"  # matched first
        assert picks[1]["kickoff"] is None  # unmatched last

    def test_ordered_by_kickoff_time(self):
        """Multiple matched picks are ordered by kickoff time."""
        week = get_or_create_current_week()
        players = get_all_players()

        _insert_fixture(3001, "Late Game", "Away", "2026-03-07T17:30:00")
        _insert_fixture(3002, "Early Game", "Away", "2026-03-07T12:30:00")

        pick1, _, _, _ = submit_pick(players[0]["id"], week["id"], "Late Game to win", 2.0, "evens", "win")
        _link_pick_to_fixture(pick1["id"], 3001)
        pick2, _, _, _ = submit_pick(players[1]["id"], week["id"], "Early Game to win", 1.5, "1/2", "win")
        _link_pick_to_fixture(pick2["id"], 3002)

        picks = get_picks_for_week_by_kickoff(week["id"])
        assert picks[0]["home_team"] == "Early Game"
        assert picks[1]["home_team"] == "Late Game"


class TestAllPicksInKickoffFormat:
    def _make_placer(self):
        return {"formal_name": "Mr Kevin", "emoji": "🃏"}

    def _make_pick(self, formal_name, description, odds, emoji="",
                   kickoff=None, home_team=None, away_team=None):
        return {
            "formal_name": formal_name,
            "description": description,
            "odds_original": odds,
            "emoji": emoji,
            "kickoff": kickoff,
            "home_team": home_team,
            "away_team": away_team,
        }

    def test_mixed_matched_and_unmatched(self):
        """Matched picks appear first with kickoff times, unmatched under 'Kickoff TBC'."""
        placer = self._make_placer()
        picks = [
            self._make_pick("Mr Aidan", "Bournemouth to win", "4/5", "♟️",
                            kickoff="2026-03-07T15:00:00", home_team="Bournemouth", away_team="Sunderland"),
            self._make_pick("Mr Kevin", "Dublin +2", "11/10", "🃏"),
        ]
        result = butler.all_picks_in(placer, picks=picks)

        assert "Saturday" in result
        assert "3:00 PM" in result
        assert "Bournemouth vs Sunderland" in result
        assert "♟️ Mr Aidan" in result
        assert "Kickoff TBC" in result
        assert "🃏 Mr Kevin" in result

    def test_all_unmatched(self):
        """When all picks are unmatched, only 'Kickoff TBC' section appears."""
        placer = self._make_placer()
        picks = [
            self._make_pick("Mr Kevin", "Dublin +2", "11/10", "🃏"),
            self._make_pick("Mr Declan", "Cavan to win", "evens", "🎲"),
        ]
        result = butler.all_picks_in(placer, picks=picks)

        assert "Kickoff TBC" in result
        assert "🃏 Mr Kevin" in result
        assert "🎲 Mr Declan" in result
        # No day headers when nothing is matched
        assert "Saturday" not in result
        assert "Sunday" not in result

    def test_multiple_days(self):
        """Picks across Saturday and Sunday get separate day headers."""
        placer = self._make_placer()
        picks = [
            self._make_pick("Mr Aidan", "Bournemouth to win", "4/5", "♟️",
                            kickoff="2026-03-07T15:00:00", home_team="Bournemouth", away_team="Sunderland"),
            self._make_pick("Mr Niall", "Ipswich to win", "11/20", "🏆",
                            kickoff="2026-03-08T14:00:00", home_team="Ipswich", away_team="Swansea"),
        ]
        result = butler.all_picks_in(placer, picks=picks)

        assert "Saturday" in result
        assert "Sunday" in result
        # Saturday pick before Sunday pick
        sat_pos = result.index("Saturday")
        sun_pos = result.index("Sunday")
        assert sat_pos < sun_pos

    def test_same_day_multiple_kickoffs(self):
        """Multiple kickoffs on the same day share one day header."""
        placer = self._make_placer()
        picks = [
            self._make_pick("Mr Aidan", "Bournemouth to win", "4/5", "♟️",
                            kickoff="2026-03-07T15:00:00", home_team="Bournemouth", away_team="Sunderland"),
            self._make_pick("Mr Ronan", "Man Utd to win", "8/15", "🎯",
                            kickoff="2026-03-07T17:30:00", home_team="Manchester United", away_team="Crystal Palace"),
        ]
        result = butler.all_picks_in(placer, picks=picks)

        assert result.count("Saturday") == 1
        assert "3:00 PM" in result
        assert "5:30 PM" in result

    def test_no_picks(self):
        """With no picks, just returns the header."""
        placer = self._make_placer()
        result = butler.all_picks_in(placer, picks=None)

        assert "All selections have been received" in result
        assert "Mr Kevin" in result
        assert "Kickoff TBC" not in result

    def test_header_always_present(self):
        """Header with placer name is always included."""
        placer = self._make_placer()
        picks = [
            self._make_pick("Mr Aidan", "Arsenal to win", "4/5", "♟️",
                            kickoff="2026-03-07T15:00:00", home_team="Arsenal", away_team="Chelsea"),
        ]
        result = butler.all_picks_in(placer, picks=picks)

        assert result.startswith("All selections have been received.")
        assert "Mr Kevin, you are next in the rotation to place the wager." in result

    def test_utc_kickoff_displayed_in_dublin_time(self):
        """UTC kickoff time is converted to Europe/Dublin for display."""
        placer = self._make_placer()
        # March 7 2026 is during GMT (no DST), so UTC = Dublin time
        picks = [
            self._make_pick("Mr Aidan", "Arsenal to win", "4/5", "♟️",
                            kickoff="2026-03-07T15:00:00", home_team="Arsenal", away_team="Chelsea"),
        ]
        result = butler.all_picks_in(placer, picks=picks)
        assert "3:00 PM" in result

    def test_bst_kickoff_displayed_correctly(self):
        """During BST (summer), UTC+0 kickoff shows as +1 in Dublin time."""
        placer = self._make_placer()
        # June 6 2026 is during BST, so UTC 14:00 = Dublin 15:00
        picks = [
            self._make_pick("Mr Aidan", "Arsenal to win", "4/5", "♟️",
                            kickoff="2026-06-06T14:00:00", home_team="Arsenal", away_team="Chelsea"),
        ]
        result = butler.all_picks_in(placer, picks=picks)
        assert "3:00 PM" in result
