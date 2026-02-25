"""Tests for match monitoring: event extraction, dedup, auto-resulting, and butler templates."""

import json

from src.db import get_db
from src.services.fixture_service import extract_events, get_fixture_by_api_id
from src.services.match_monitor_service import (
    poll_fixtures,
    get_unresulted_picks_for_week,
    _record_event_if_new,
)
from src.services.auto_result_service import auto_result_fixture, COMPLETED_STATUSES
from src.services.pick_service import submit_pick
from src.services.player_service import get_all_players
from src.services.week_service import get_or_create_current_week
from src.services.result_service import record_result
import src.butler as butler


# --- Sample API-Football fixture data ---

def _make_fixture_data(api_id=12345, status="FT", home="Liverpool", away="Arsenal",
                        home_score=2, away_score=1, ht_home=1, ht_away=0, events=None):
    """Build a realistic API-Football fixture response dict."""
    return {
        "fixture": {
            "id": api_id,
            "date": "2026-02-28T15:00:00+00:00",
            "status": {"short": status, "long": "Match Finished"},
        },
        "league": {"id": 39, "name": "Premier League"},
        "teams": {
            "home": {"name": home},
            "away": {"name": away},
        },
        "goals": {"home": home_score, "away": away_score},
        "score": {
            "halftime": {"home": ht_home, "away": ht_away},
        },
        "events": events or [],
    }


def _insert_fixture(api_id=12345, status="NS", home="Liverpool", away="Arsenal",
                     home_score=None, away_score=None, kickoff="2026-02-28T15:00:00+00:00",
                     raw_json=None):
    """Insert a fixture directly into the DB."""
    conn = get_db()
    conn.execute(
        """INSERT OR REPLACE INTO fixtures
           (api_id, sport, competition, competition_id, home_team, away_team,
            kickoff, status, home_score, away_score, raw_json)
           VALUES (?, 'football', 'Premier League', 39, ?, ?, ?, ?, ?, ?, ?)""",
        (api_id, home, away, kickoff, status, home_score, away_score,
         json.dumps(raw_json) if raw_json else None),
    )
    conn.commit()
    conn.close()


def _setup_pick_with_fixture(player_idx=0, api_id=12345, fixture_status="NS",
                              home="Liverpool", away="Arsenal",
                              description="Liverpool to win", kickoff="2026-02-28T15:00:00+00:00"):
    """Create a week, fixture, and matched pick."""
    week = get_or_create_current_week()
    players = get_all_players()
    player = players[player_idx]

    _insert_fixture(api_id=api_id, status=fixture_status, home=home, away=away, kickoff=kickoff)

    # Submit pick and manually set api_fixture_id
    pick, _, _, _ = submit_pick(player["id"], week["id"], description, 2.0, "evens", "win")
    conn = get_db()
    conn.execute("UPDATE picks SET api_fixture_id = ? WHERE id = ?", (api_id, pick["id"]))
    conn.commit()
    conn.close()

    return week, player, pick


# --- Tests: extract_events ---

class TestExtractEvents:
    def test_extract_goals(self):
        events = [
            {"type": "Goal", "detail": "Normal Goal", "time": {"elapsed": 23},
             "team": {"name": "Liverpool"}, "player": {"name": "Salah"}},
            {"type": "Goal", "detail": "Penalty", "time": {"elapsed": 47},
             "team": {"name": "Arsenal"}, "player": {"name": "Saka"}},
        ]
        data = _make_fixture_data(events=events)
        result = extract_events(data)

        assert len(result) == 2
        assert result[0]["event_key"] == "Goal_23_Salah"
        assert result[0]["event_type"] == "Goal"
        assert result[0]["player"] == "Salah"
        assert result[0]["minute"] == 23
        assert result[1]["detail"] == "Penalty"

    def test_extract_red_card(self):
        events = [
            {"type": "Card", "detail": "Red Card", "time": {"elapsed": 68},
             "team": {"name": "Arsenal"}, "player": {"name": "Rice"}},
        ]
        data = _make_fixture_data(events=events)
        result = extract_events(data)

        assert len(result) == 1
        assert result[0]["event_key"] == "RedCard_68_Rice"
        assert result[0]["event_type"] == "RedCard"

    def test_ignore_yellow_cards(self):
        events = [
            {"type": "Card", "detail": "Yellow Card", "time": {"elapsed": 30},
             "team": {"name": "Liverpool"}, "player": {"name": "Robertson"}},
        ]
        data = _make_fixture_data(events=events)
        result = extract_events(data)

        assert len(result) == 0

    def test_ignore_substitutions(self):
        events = [
            {"type": "subst", "detail": "Substitution 1", "time": {"elapsed": 60},
             "team": {"name": "Liverpool"}, "player": {"name": "Jota"}},
        ]
        data = _make_fixture_data(events=events)
        result = extract_events(data)
        assert len(result) == 0

    def test_empty_events(self):
        data = _make_fixture_data(events=[])
        result = extract_events(data)
        assert result == []

    def test_no_events_key(self):
        data = {"fixture": {}, "goals": {}, "teams": {}}
        result = extract_events(data)
        assert result == []

    def test_extract_from_json_string(self):
        events = [
            {"type": "Goal", "detail": "Own Goal", "time": {"elapsed": 55},
             "team": {"name": "Arsenal"}, "player": {"name": "Gabriel"}},
        ]
        data = _make_fixture_data(events=events)
        result = extract_events(json.dumps(data))
        assert len(result) == 1
        assert result[0]["detail"] == "Own Goal"

    def test_own_goal_extracted(self):
        events = [
            {"type": "Goal", "detail": "Own Goal", "time": {"elapsed": 33},
             "team": {"name": "Liverpool"}, "player": {"name": "Gabriel"}},
        ]
        data = _make_fixture_data(events=events)
        result = extract_events(data)
        assert len(result) == 1
        assert result[0]["event_type"] == "Goal"
        assert result[0]["detail"] == "Own Goal"


# --- Tests: event dedup ---

class TestEventDedup:
    def test_record_new_event(self):
        assert _record_event_if_new(99999, "Goal_23_Salah", "Goal", "Normal Goal") is True

    def test_duplicate_event_rejected(self):
        _record_event_if_new(99998, "Goal_10_Saka", "Goal", "Normal Goal")
        assert _record_event_if_new(99998, "Goal_10_Saka", "Goal", "Normal Goal") is False


# --- Tests: auto_result_fixture ---

class TestAutoResultFixture:
    def test_auto_result_completed_fixture(self):
        week, player, pick = _setup_pick_with_fixture(
            description="Liverpool to win", fixture_status="FT",
        )
        # Update fixture with scores
        conn = get_db()
        conn.execute(
            "UPDATE fixtures SET home_score = 2, away_score = 1, status = 'FT' WHERE api_id = 12345"
        )
        conn.commit()
        conn.close()

        announcements = auto_result_fixture(12345, week["id"])
        assert len(announcements) >= 1
        assert "Liverpool" in announcements[0] or "Mr" in announcements[0]

    def test_skip_already_resulted(self):
        week, player, pick = _setup_pick_with_fixture(
            description="Liverpool to win", fixture_status="FT",
        )
        conn = get_db()
        conn.execute(
            "UPDATE fixtures SET home_score = 2, away_score = 1, status = 'FT' WHERE api_id = 12345"
        )
        conn.commit()
        conn.close()

        record_result(pick["id"], "win", confirmed_by="Ed")
        announcements = auto_result_fixture(12345, week["id"])
        assert announcements == []

    def test_skip_not_finished(self):
        week, player, pick = _setup_pick_with_fixture(
            description="Liverpool to win", fixture_status="1H",
        )
        announcements = auto_result_fixture(12345, week["id"])
        assert announcements == []


# --- Tests: butler templates ---

class TestButlerMatchTemplates:
    def test_match_event_goal(self):
        msg = butler.match_event("Goal", "Liverpool", "Arsenal", 1, 0, "Salah", 23)
        assert "Salah" in msg
        assert "23'" in msg
        assert "Liverpool 1-0 Arsenal" in msg

    def test_match_event_penalty_goal(self):
        msg = butler.match_event("Goal", "Liverpool", "Arsenal", 1, 1, "Saka", 47, detail="Penalty")
        assert "Penalty" in msg
        assert "Saka" in msg

    def test_match_event_red_card(self):
        msg = butler.match_event("RedCard", "Liverpool", "Arsenal", 1, 1, "Rice", 68)
        assert "Red Card" in msg
        assert "Rice" in msg

    def test_match_ended(self):
        msg = butler.match_ended("Liverpool", "Arsenal", 2, 1)
        assert msg == "FT: Liverpool 2-1 Arsenal"


# --- Tests: get_unresulted_picks_for_week ---

class TestUnresultedPicks:
    def test_returns_matched_unresulted(self):
        week, player, pick = _setup_pick_with_fixture()
        picks = get_unresulted_picks_for_week(week["id"])
        assert len(picks) == 1
        assert picks[0]["api_fixture_id"] == 12345

    def test_excludes_resulted_picks(self):
        week, player, pick = _setup_pick_with_fixture()
        record_result(pick["id"], "win", confirmed_by="Ed")
        picks = get_unresulted_picks_for_week(week["id"])
        assert len(picks) == 0

    def test_excludes_unmatched_picks(self):
        week = get_or_create_current_week()
        players = get_all_players()
        submit_pick(players[0]["id"], week["id"], "Some pick", 2.0, "evens", "win")
        picks = get_unresulted_picks_for_week(week["id"])
        assert len(picks) == 0


# --- Tests: poll_fixtures (integration) ---

class TestPollFixtures:
    def test_poll_disabled_returns_skipped(self, monkeypatch):
        monkeypatch.setattr("src.config.Config.MATCH_MONITOR_ENABLED", False)
        results = poll_fixtures([12345], 1, lambda *a: None)
        assert results[12345] == "skipped"

    def test_poll_completed_fixture(self, monkeypatch):
        monkeypatch.setattr("src.config.Config.MATCH_MONITOR_ENABLED", True)
        monkeypatch.setattr("src.config.Config.MATCH_MONITOR_GROUP_ID", "test-group")
        monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", "main-group")

        week, player, pick = _setup_pick_with_fixture(fixture_status="FT")

        # Update with scores and raw_json containing events
        events = [
            {"type": "Goal", "detail": "Normal Goal", "time": {"elapsed": 23},
             "team": {"name": "Liverpool"}, "player": {"name": "Salah"}},
        ]
        fixture_data = _make_fixture_data(api_id=12345, status="FT", events=events)
        conn = get_db()
        conn.execute(
            "UPDATE fixtures SET home_score = 2, away_score = 1, status = 'FT', "
            "raw_json = ? WHERE api_id = 12345",
            (json.dumps(fixture_data),),
        )
        conn.commit()
        conn.close()

        # Disable actual API refresh (we've already set the data)
        monkeypatch.setattr(
            "src.services.match_monitor_service.refresh_fixture", lambda x: None
        )
        monkeypatch.setattr(
            "src.services.match_monitor_service.refresh_fixtures_by_date", lambda x: 0
        )

        messages = []
        def capture_send(chat_id, text):
            messages.append((chat_id, text))

        results = poll_fixtures([12345], week["id"], capture_send)
        assert results[12345] == "completed"
        # Should have posted events + FT + result announcement
        assert len(messages) >= 1

    def test_poll_not_started(self, monkeypatch):
        monkeypatch.setattr("src.config.Config.MATCH_MONITOR_ENABLED", True)
        monkeypatch.setattr("src.config.Config.MATCH_MONITOR_GROUP_ID", "test-group")

        _insert_fixture(api_id=55555, status="NS")

        monkeypatch.setattr(
            "src.services.match_monitor_service.refresh_fixture", lambda x: None
        )
        monkeypatch.setattr(
            "src.services.match_monitor_service.refresh_fixtures_by_date", lambda x: 0
        )

        results = poll_fixtures([55555], 1, lambda *a: None)
        assert results[55555] == "not_started"
