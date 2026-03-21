"""Tests for bet_slip_service."""

import pytest

from src.db import get_db
from src.services.bet_slip_service import (
    fetch_image_from_bridge,
    match_legs_to_picks,
    record_bet_slip,
    update_confirmed_odds,
    process_bet_slip,
)
from src.services.pick_service import submit_pick, get_picks_for_week
from src.services.player_service import get_all_players
from src.services.week_service import get_or_create_current_week


# ---------------------------------------------------------------------------
# match_legs_to_picks
# ---------------------------------------------------------------------------

class TestMatchLegsToPickss:
    def _make_pick(self, pid, description):
        return {"id": pid, "description": description}

    def test_matches_high_similarity(self):
        picks = [
            self._make_pick(1, "Liverpool to win"),
            self._make_pick(2, "Man City to win"),
        ]
        legs = [{"selection": "Liverpool to win", "odds": 1.8}]
        matched = match_legs_to_picks(legs, picks)
        assert len(matched) == 1
        assert matched[0] == (1, 1.8)

    def test_matches_partial_similarity(self):
        picks = [self._make_pick(10, "Arsenal to beat Chelsea")]
        legs = [{"selection": "Arsenal to beat Chelsea", "odds": 2.0}]
        matched = match_legs_to_picks(legs, picks)
        assert matched[0][0] == 10

    def test_skips_low_similarity_legs(self):
        picks = [self._make_pick(1, "Liverpool to win")]
        legs = [{"selection": "completely unrelated text xyz", "odds": 3.0}]
        matched = match_legs_to_picks(legs, picks)
        assert matched == []

    def test_skips_legs_with_empty_selection(self):
        picks = [self._make_pick(1, "Liverpool to win")]
        legs = [{"selection": "", "odds": 2.0}, {"selection": None, "odds": 1.5}]
        matched = match_legs_to_picks(legs, picks)
        assert matched == []

    def test_empty_picks_returns_empty(self):
        legs = [{"selection": "Liverpool", "odds": 1.8}]
        matched = match_legs_to_picks(legs, [])
        assert matched == []

    def test_multiple_legs_multiple_matches(self):
        picks = [
            self._make_pick(1, "Liverpool to win"),
            self._make_pick(2, "Man City to win"),
        ]
        legs = [
            {"selection": "Liverpool to win", "odds": 1.8},
            {"selection": "Man City to win", "odds": 2.1},
        ]
        matched = match_legs_to_picks(legs, picks)
        assert len(matched) == 2
        pick_ids = {m[0] for m in matched}
        assert pick_ids == {1, 2}

    def test_odds_none_is_stored(self):
        picks = [self._make_pick(5, "Chelsea to win")]
        legs = [{"selection": "Chelsea to win", "odds": None}]
        matched = match_legs_to_picks(legs, picks)
        assert matched == [(5, None)]


# ---------------------------------------------------------------------------
# record_bet_slip
# ---------------------------------------------------------------------------

class TestRecordBetSlip:
    def test_inserts_row(self):
        week = get_or_create_current_week()
        players = get_all_players()
        player = players[0]

        extracted = {"stake": 5.0, "total_odds": 10.5, "potential_return": 52.5}
        record_bet_slip(week["id"], player["id"], extracted)

        conn = get_db()
        row = conn.execute(
            "SELECT * FROM bet_slips WHERE week_id = ? AND placer_id = ?",
            (week["id"], player["id"]),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["stake"] == 5.0
        assert row["total_odds"] == 10.5
        assert row["potential_return"] == 52.5

    def test_inserts_with_nulls(self):
        week = get_or_create_current_week()
        players = get_all_players()
        player = players[0]

        record_bet_slip(week["id"], player["id"], {})

        conn = get_db()
        row = conn.execute(
            "SELECT * FROM bet_slips WHERE week_id = ? AND placer_id = ?",
            (week["id"], player["id"]),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["stake"] is None
        assert row["total_odds"] is None


# ---------------------------------------------------------------------------
# update_confirmed_odds
# ---------------------------------------------------------------------------

class TestUpdateConfirmedOdds:
    def test_sets_confirmed_odds(self):
        week = get_or_create_current_week()
        players = get_all_players()
        pick, _, _, _ = submit_pick(
            players[0]["id"], week["id"], "Liverpool to win", 2.0, "evens", "win"
        )

        update_confirmed_odds([(pick["id"], 1.95)])

        conn = get_db()
        row = conn.execute("SELECT confirmed_odds FROM picks WHERE id = ?", (pick["id"],)).fetchone()
        conn.close()

        assert row["confirmed_odds"] == 1.95

    def test_no_op_on_empty_list(self):
        # Should not raise
        update_confirmed_odds([])

    def test_updates_multiple_picks(self):
        week = get_or_create_current_week()
        players = get_all_players()
        pick1, _, _, _ = submit_pick(players[0]["id"], week["id"], "Pick A", 2.0, "evens", "win")
        pick2, _, _, _ = submit_pick(players[1]["id"], week["id"], "Pick B", 3.0, "2/1", "win")

        update_confirmed_odds([(pick1["id"], 1.9), (pick2["id"], 2.8)])

        conn = get_db()
        rows = {
            r["id"]: r["confirmed_odds"]
            for r in conn.execute(
                "SELECT id, confirmed_odds FROM picks WHERE id IN (?, ?)",
                (pick1["id"], pick2["id"]),
            ).fetchall()
        }
        conn.close()

        assert rows[pick1["id"]] == 1.9
        assert rows[pick2["id"]] == 2.8


# ---------------------------------------------------------------------------
# process_bet_slip — integration with mocks
# ---------------------------------------------------------------------------

class TestProcessBetSlip:
    def _submit_picks(self, week, players):
        picks = []
        for i, p in enumerate(players[:2]):
            pick, _, _, _ = submit_pick(
                p["id"], week["id"], f"Team {i} to win", 2.0, "evens", "win"
            )
            picks.append(pick)
        return picks

    def test_writes_db_rows_on_success(self, monkeypatch):
        week = get_or_create_current_week()
        players = get_all_players()
        picks = self._submit_picks(week, players)

        monkeypatch.setattr(
            "src.services.bet_slip_service.fetch_image_from_bridge",
            lambda mid: {"data": "fakebase64", "mimetype": "image/jpeg"},
        )
        monkeypatch.setattr(
            "src.services.bet_slip_service.llm_client.read_bet_slip",
            lambda b64, mime: {
                "stake": 5.0,
                "total_odds": 8.0,
                "potential_return": 40.0,
                "legs": [
                    {"selection": "Team 0 to win", "odds": 2.0},
                    {"selection": "Team 1 to win", "odds": 4.0},
                ],
            },
        )

        process_bet_slip(week["id"], players[0]["id"], "msg123", picks)

        conn = get_db()
        slip = conn.execute(
            "SELECT * FROM bet_slips WHERE week_id = ?", (week["id"],)
        ).fetchone()
        assert slip is not None
        assert slip["stake"] == 5.0

        # confirmed_odds should be set on matched picks
        for pick in picks:
            row = conn.execute(
                "SELECT confirmed_odds FROM picks WHERE id = ?", (pick["id"],)
            ).fetchone()
            assert row["confirmed_odds"] is not None
        conn.close()

    def test_no_writes_when_bridge_returns_404(self, monkeypatch):
        week = get_or_create_current_week()
        players = get_all_players()
        picks = self._submit_picks(week, players)

        monkeypatch.setattr(
            "src.services.bet_slip_service.fetch_image_from_bridge",
            lambda mid: None,
        )
        # read_bet_slip should never be called
        called = []
        monkeypatch.setattr(
            "src.services.bet_slip_service.llm_client.read_bet_slip",
            lambda *a, **kw: called.append(1) or {},
        )

        process_bet_slip(week["id"], players[0]["id"], "msg404", picks)

        assert called == []
        conn = get_db()
        slip = conn.execute("SELECT * FROM bet_slips WHERE week_id = ?", (week["id"],)).fetchone()
        assert slip is None
        conn.close()

    def test_no_writes_when_groq_fails(self, monkeypatch):
        week = get_or_create_current_week()
        players = get_all_players()
        picks = self._submit_picks(week, players)

        monkeypatch.setattr(
            "src.services.bet_slip_service.fetch_image_from_bridge",
            lambda mid: {"data": "fakebase64", "mimetype": "image/jpeg"},
        )
        monkeypatch.setattr(
            "src.services.bet_slip_service.llm_client.read_bet_slip",
            lambda *a, **kw: None,
        )

        process_bet_slip(week["id"], players[0]["id"], "msgfail", picks)

        conn = get_db()
        slip = conn.execute("SELECT * FROM bet_slips WHERE week_id = ?", (week["id"],)).fetchone()
        assert slip is None
        conn.close()

    def test_silent_on_unexpected_exception(self, monkeypatch):
        """process_bet_slip never raises even on unexpected errors."""
        week = get_or_create_current_week()

        monkeypatch.setattr(
            "src.services.bet_slip_service.fetch_image_from_bridge",
            lambda mid: (_ for _ in ()).throw(RuntimeError("unexpected")),
        )

        # Should not raise
        process_bet_slip(week["id"], 1, "msgboom", [])
