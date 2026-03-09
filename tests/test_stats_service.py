"""Tests for stats_service."""

from src.services.stats_service import get_player_stats, get_leaderboard
from src.services.pick_service import submit_pick
from src.services.result_service import record_result
from src.services.player_service import get_all_players
from src.services.week_service import get_or_create_current_week


class TestPlayerStats:
    def test_no_results(self):
        players = get_all_players()
        stats = get_player_stats(players[0]["id"])
        assert stats["total"] == 0
        assert stats["win_rate"] == 0.0
        assert stats["streak"] == "-"
        assert stats["form"] == "-"

    def test_with_results(self):
        week = get_or_create_current_week()
        players = get_all_players()
        player = players[0]

        pick, _, _, _ = submit_pick(player["id"], week["id"], "Test", 2.0, "evens", "win")
        record_result(pick["id"], "win")

        stats = get_player_stats(player["id"])
        assert stats["wins"] == 1
        assert stats["losses"] == 0
        assert stats["total"] == 1
        assert stats["win_rate"] == 100.0
        assert stats["streak"] == "\u2705"
        assert stats["form"] == "\u2705"

    def test_mixed_results(self):
        week = get_or_create_current_week()
        players = get_all_players()
        player = players[0]

        # Create multiple weeks with picks/results
        from src.db import get_db
        conn = get_db()
        outcomes = ["win", "loss", "win", "win", "loss"]
        for i, outcome in enumerate(outcomes):
            wk_num = 30 + i
            conn.execute(
                "INSERT INTO weeks (week_number, season, deadline, status) VALUES (?, '2026', '2026-01-01', 'completed')",
                (wk_num,),
            )
            wk_id = conn.execute("SELECT id FROM weeks WHERE week_number = ?", (wk_num,)).fetchone()[0]
            conn.execute(
                "INSERT INTO picks (week_id, player_id, description, odds_decimal, odds_original) VALUES (?, ?, 'test', 2.0, 'evens')",
                (wk_id, player["id"]),
            )
            pick_id = conn.execute(
                "SELECT id FROM picks WHERE week_id = ? AND player_id = ?",
                (wk_id, player["id"]),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO results (pick_id, outcome, confirmed_at) VALUES (?, ?, datetime('now', ? || ' minutes'))",
                (pick_id, outcome, str(i)),
            )
        conn.commit()
        conn.close()

        stats = get_player_stats(player["id"])
        assert stats["wins"] == 3
        assert stats["losses"] == 2
        assert stats["total"] == 5
        assert stats["win_rate"] == 60.0


class TestLeaderboard:
    def test_empty_leaderboard(self):
        entries = get_leaderboard()
        assert entries == []

    def test_leaderboard_with_results(self):
        week = get_or_create_current_week()
        players = get_all_players()

        # Player 0: 1 win
        pick, _, _, _ = submit_pick(players[0]["id"], week["id"], "P1", 2.0, "evens", "win")
        record_result(pick["id"], "win")

        # Player 1: 1 loss
        pick, _, _, _ = submit_pick(players[1]["id"], week["id"], "P2", 3.0, "2/1", "win")
        record_result(pick["id"], "loss")

        entries = get_leaderboard()
        assert len(entries) == 2
        # Winner should be first (higher win rate)
        assert entries[0]["win_rate"] == 100.0
        assert entries[1]["win_rate"] == 0.0
