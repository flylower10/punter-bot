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
from src.services.result_service import record_result, week_has_loss
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
            "src.services.match_monitor_service.refresh_fixture", lambda x, **kw: None
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
            "src.services.match_monitor_service.refresh_fixture", lambda x, **kw: None
        )
        monkeypatch.setattr(
            "src.services.match_monitor_service.refresh_fixtures_by_date", lambda x: 0
        )

        results = poll_fixtures([55555], 1, lambda *a: None)
        assert results[55555] == "not_started"


# --- Tests: cache bypass in refresh functions ---

class TestRefreshCacheBypass:
    def test_refresh_fixture_bypasses_cache(self, monkeypatch):
        """refresh_fixture should pass cache_ttl_hours=0 to get_fixture_by_id."""
        from src.services.fixture_service import refresh_fixture

        calls = []

        def mock_get_fixture_by_id(fixture_id, cache_ttl_hours=1):
            calls.append({"fixture_id": fixture_id, "cache_ttl_hours": cache_ttl_hours})
            return _make_fixture_data(api_id=fixture_id)

        monkeypatch.setattr("src.services.fixture_service.get_fixture_by_id", mock_get_fixture_by_id)

        _insert_fixture(api_id=77777, status="1H")
        refresh_fixture(77777)

        assert len(calls) == 1
        assert calls[0]["cache_ttl_hours"] == 0

    def test_refresh_fixtures_by_date_bypasses_cache(self, monkeypatch):
        """refresh_fixtures_by_date should pass cache_ttl_hours=0 to get_fixtures_by_date."""
        from src.services.fixture_service import refresh_fixtures_by_date

        calls = []

        def mock_get_fixtures_by_date(date_str, cache_ttl_hours=6):
            calls.append({"date_str": date_str, "cache_ttl_hours": cache_ttl_hours})
            return [_make_fixture_data(api_id=88888)]

        monkeypatch.setattr("src.services.fixture_service.get_fixtures_by_date", mock_get_fixtures_by_date)

        refresh_fixtures_by_date("2026-03-01")

        assert len(calls) == 1
        assert calls[0]["cache_ttl_hours"] == 0


# --- Tests: acca loss suppression ---

class TestAccaLossSuppression:
    """Live events should be suppressed once any pick in the week has lost."""

    def test_week_has_loss_false_when_no_results(self):
        week = get_or_create_current_week()
        assert week_has_loss(week["id"]) is False

    def test_week_has_loss_false_when_only_wins(self):
        week, player, pick = _setup_pick_with_fixture()
        record_result(pick["id"], "win", confirmed_by="auto")
        assert week_has_loss(week["id"]) is False

    def test_week_has_loss_true_when_loss_recorded(self):
        week, player, pick = _setup_pick_with_fixture()
        record_result(pick["id"], "loss", confirmed_by="auto")
        assert week_has_loss(week["id"]) is True

    def test_live_events_post_when_acca_alive(self, monkeypatch):
        """Goals and FT should post when no losses exist."""
        monkeypatch.setattr("src.config.Config.MATCH_MONITOR_ENABLED", True)
        monkeypatch.setattr("src.config.Config.MATCH_MONITOR_GROUP_ID", "test-group")
        monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", "main-group")

        week, player, pick = _setup_pick_with_fixture(
            api_id=60001, fixture_status="FT",
        )

        events = [
            {"type": "Goal", "detail": "Normal Goal", "time": {"elapsed": 15},
             "team": {"name": "Liverpool"}, "player": {"name": "Salah"}},
        ]
        fixture_data = _make_fixture_data(api_id=60001, status="FT", events=events)
        conn = get_db()
        conn.execute(
            "UPDATE fixtures SET home_score = 2, away_score = 1, status = 'FT', "
            "raw_json = ? WHERE api_id = 60001",
            (json.dumps(fixture_data),),
        )
        conn.commit()
        conn.close()

        monkeypatch.setattr(
            "src.services.match_monitor_service.refresh_fixture", lambda x, **kw: None
        )
        monkeypatch.setattr(
            "src.services.match_monitor_service.refresh_fixtures_by_date", lambda x: 0
        )

        messages = []
        def capture_send(chat_id, text):
            messages.append(text)

        poll_fixtures([60001], week["id"], capture_send)

        # Should have goal event + FT + result announcement
        has_goal = any("Salah" in m for m in messages)
        has_ft = any("FT:" in m for m in messages)
        assert has_goal, f"Expected goal event, got: {messages}"
        assert has_ft, f"Expected FT message, got: {messages}"

    def test_live_events_suppressed_when_acca_lost(self, monkeypatch):
        """Goals and FT should NOT post when a loss already exists, but result should."""
        monkeypatch.setattr("src.config.Config.MATCH_MONITOR_ENABLED", True)
        monkeypatch.setattr("src.config.Config.MATCH_MONITOR_GROUP_ID", "test-group")
        monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", "main-group")

        # Create two picks: one already lost, one still pending
        week, player1, pick1 = _setup_pick_with_fixture(
            player_idx=0, api_id=60010, fixture_status="FT",
            home="Chelsea", away="Everton", description="Chelsea to win",
        )
        # Record a loss on the first pick
        record_result(pick1["id"], "loss", confirmed_by="auto")

        # Second pick with a different fixture
        players = get_all_players()
        player2 = players[1]
        _insert_fixture(api_id=60011, status="FT", home="Liverpool", away="Arsenal",
                        home_score=2, away_score=1)
        pick2, _, _, _ = submit_pick(player2["id"], week["id"], "Liverpool to win", 2.0, "evens", "win")
        conn = get_db()
        conn.execute("UPDATE picks SET api_fixture_id = 60011 WHERE id = ?", (pick2["id"],))
        conn.commit()
        conn.close()

        events = [
            {"type": "Goal", "detail": "Normal Goal", "time": {"elapsed": 23},
             "team": {"name": "Liverpool"}, "player": {"name": "Salah"}},
        ]
        fixture_data = _make_fixture_data(api_id=60011, status="FT", events=events,
                                           home="Liverpool", away="Arsenal")
        conn = get_db()
        conn.execute(
            "UPDATE fixtures SET home_score = 2, away_score = 1, status = 'FT', "
            "raw_json = ? WHERE api_id = 60011",
            (json.dumps(fixture_data),),
        )
        conn.commit()
        conn.close()

        monkeypatch.setattr(
            "src.services.match_monitor_service.refresh_fixture", lambda x, **kw: None
        )
        monkeypatch.setattr(
            "src.services.match_monitor_service.refresh_fixtures_by_date", lambda x: 0
        )

        messages = []
        def capture_send(chat_id, text):
            messages.append(text)

        poll_fixtures([60011], week["id"], capture_send)

        # Goal and FT events should be suppressed
        has_goal = any("Salah" in m for m in messages)
        has_ft = any("FT:" in m for m in messages)
        assert not has_goal, f"Goal should be suppressed, got: {messages}"
        assert not has_ft, f"FT should be suppressed, got: {messages}"

    def test_auto_result_still_posts_when_acca_lost(self, monkeypatch):
        """Pick result announcements should still post even when acca is dead."""
        monkeypatch.setattr("src.config.Config.MATCH_MONITOR_ENABLED", True)
        monkeypatch.setattr("src.config.Config.MATCH_MONITOR_GROUP_ID", "test-group")
        monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", "main-group")

        # First pick: already lost
        week, player1, pick1 = _setup_pick_with_fixture(
            player_idx=0, api_id=60020, fixture_status="FT",
            home="Chelsea", away="Everton", description="Chelsea to win",
        )
        record_result(pick1["id"], "loss", confirmed_by="auto")

        # Second pick: linked to fixture about to be auto-resulted
        players = get_all_players()
        player2 = players[1]
        _insert_fixture(api_id=60021, status="FT", home="Liverpool", away="Arsenal",
                        home_score=2, away_score=1)
        pick2, _, _, _ = submit_pick(player2["id"], week["id"], "Liverpool to win", 2.0, "evens", "win")
        conn = get_db()
        conn.execute("UPDATE picks SET api_fixture_id = 60021 WHERE id = ?", (pick2["id"],))
        conn.commit()
        conn.close()

        fixture_data = _make_fixture_data(api_id=60021, status="FT",
                                           home="Liverpool", away="Arsenal")
        conn = get_db()
        conn.execute(
            "UPDATE fixtures SET home_score = 2, away_score = 1, status = 'FT', "
            "raw_json = ? WHERE api_id = 60021",
            (json.dumps(fixture_data),),
        )
        conn.commit()
        conn.close()

        monkeypatch.setattr(
            "src.services.match_monitor_service.refresh_fixture", lambda x, **kw: None
        )
        monkeypatch.setattr(
            "src.services.match_monitor_service.refresh_fixtures_by_date", lambda x: 0
        )

        messages = []
        def capture_send(chat_id, text):
            messages.append(text)

        poll_fixtures([60021], week["id"], capture_send)

        # Auto-result announcement should still be posted
        assert len(messages) >= 1, "Expected at least one auto-result announcement"
