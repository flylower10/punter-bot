"""Tests for report_service — P&L calculations, awards, and display formatting."""

import pytest

from src.db import get_db
from src.services.report_service import (
    compute_leaderboard,
    compute_acca_record,
    compute_group_pnl,
    compute_singles_pnl,
    compute_biggest_winner,
    compute_awards,
    compute_what_could_have_been,
    get_period_data,
)
import src.butler as butler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rows(*tuples):
    """Build player_rows from (player_id, formal_name, week_number, outcome, odds_decimal[, confirmed_odds[, description]])."""
    return [
        {
            "player_id": t[0],
            "formal_name": t[1],
            "week_number": t[2],
            "outcome": t[3],
            "odds_decimal": t[4],
            "confirmed_odds": t[5] if len(t) > 5 else None,
            "description": t[6] if len(t) > 6 else None,
        }
        for t in tuples
    ]


def _make_slips(*tuples):
    """Build bet_slips from (week_number, stake, potential_return[, cashed_out[, reloaded[, actual_return]]])."""
    return [
        {
            "week_number": t[0],
            "stake": t[1],
            "potential_return": t[2],
            "cashed_out": t[3] if len(t) > 3 else 0,
            "reloaded": t[4] if len(t) > 4 else 0,
            "actual_return": t[5] if len(t) > 5 else None,
        }
        for t in tuples
    ]


# ---------------------------------------------------------------------------
# compute_leaderboard
# ---------------------------------------------------------------------------

class TestComputeLeaderboard:
    def test_sorted_by_win_rate(self):
        rows = _make_rows(
            (1, "Kevin", 1, "win", 2.0),
            (1, "Kevin", 2, "win", 2.0),
            (2, "Dermot", 1, "loss", 3.0),
            (2, "Dermot", 2, "win", 3.0),
        )
        lb = compute_leaderboard(rows, 1, 2)
        assert lb[0]["formal_name"] == "Kevin"
        assert lb[0]["wins"] == 2
        assert lb[0]["win_rate"] == 100.0
        assert lb[1]["formal_name"] == "Dermot"
        assert lb[1]["win_rate"] == 50.0

    def test_form_string_order(self):
        rows = _make_rows(
            (1, "Kevin", 1, "win", 2.0),
            (1, "Kevin", 2, "loss", 2.0),
            (1, "Kevin", 3, "win", 2.0),
        )
        lb = compute_leaderboard(rows, 1, 3)
        assert lb[0]["form"] == "\u2705\u274c\u2705"

    def test_avg_odds_uses_confirmed_odds(self):
        rows = _make_rows(
            (1, "Kevin", 1, "win", 2.0, 3.0),  # confirmed_odds overrides
        )
        lb = compute_leaderboard(rows, 1, 1)
        assert lb[0]["avg_odds"] == pytest.approx(3.0)

    def test_avg_odds_falls_back_to_decimal(self):
        rows = _make_rows(
            (1, "Kevin", 1, "win", 2.5),  # no confirmed_odds
        )
        lb = compute_leaderboard(rows, 1, 1)
        assert lb[0]["avg_odds"] == pytest.approx(2.5)

    def test_tie_broken_by_avg_odds(self):
        # Both 50% win rate — Kevin has higher avg odds so should sort first
        rows = _make_rows(
            (1, "Kevin", 1, "win", 4.0),
            (1, "Kevin", 2, "loss", 4.0),
            (2, "Dermot", 1, "win", 2.0),
            (2, "Dermot", 2, "loss", 2.0),
        )
        lb = compute_leaderboard(rows, 1, 2)
        assert lb[0]["formal_name"] == "Kevin"
        assert lb[1]["formal_name"] == "Dermot"


# ---------------------------------------------------------------------------
# compute_acca_record
# ---------------------------------------------------------------------------

class TestComputeAccaRecord:
    def test_all_wins(self):
        rows = _make_rows(
            (1, "K", 1, "win", 2.0),
            (2, "D", 1, "win", 3.0),
        )
        slips = _make_slips((1, 10, 40))
        wins, total = compute_acca_record(slips, rows)
        assert wins == 1
        assert total == 1

    def test_loss_counts_against_acca(self):
        rows = _make_rows(
            (1, "K", 1, "win", 2.0),
            (2, "D", 1, "loss", 3.0),
        )
        slips = _make_slips((1, 10, 40))
        wins, total = compute_acca_record(slips, rows)
        assert wins == 0
        assert total == 1

    def test_no_slips_returns_zero(self):
        rows = _make_rows((1, "K", 1, "win", 2.0))
        wins, total = compute_acca_record([], rows)
        assert wins == 0
        assert total == 0

    def test_mixed_weeks(self):
        rows = _make_rows(
            (1, "K", 1, "win", 2.0),
            (1, "K", 2, "win", 2.0),
            (1, "K", 3, "loss", 2.0),
        )
        slips = _make_slips((1, 10, 40), (2, 10, 40), (3, 10, 40))
        wins, total = compute_acca_record(slips, rows)
        assert wins == 2
        assert total == 3


# ---------------------------------------------------------------------------
# compute_group_pnl
# ---------------------------------------------------------------------------

class TestComputeGroupPnl:
    def test_full_win(self):
        rows = _make_rows((1, "K", 1, "win", 2.0))
        slips = _make_slips((1, 10, 40))
        pnl = compute_group_pnl(slips, rows)
        assert pnl["staked"] == pytest.approx(10)
        assert pnl["returned"] == pytest.approx(40)
        assert pnl["net"] == pytest.approx(30)

    def test_loss_returns_zero(self):
        rows = _make_rows((1, "K", 1, "loss", 2.0))
        slips = _make_slips((1, 10, 40))
        pnl = compute_group_pnl(slips, rows)
        assert pnl["staked"] == pytest.approx(10)
        assert pnl["returned"] == pytest.approx(0)
        assert pnl["net"] == pytest.approx(-10)

    def test_no_slips(self):
        pnl = compute_group_pnl([], [])
        assert pnl["staked"] == 0
        assert pnl["net"] == 0

    def test_cashout_uses_actual_return(self):
        # Cashed out at 99; potential was 500 → cashout_cost = 401
        rows = _make_rows((1, "K", 1, "win", 2.0))
        slips = _make_slips((1, 10, 500, 1, 0, 99))
        pnl = compute_group_pnl(slips, rows)
        assert pnl["staked"] == pytest.approx(10)
        assert pnl["returned"] == pytest.approx(99)
        assert pnl["net"] == pytest.approx(89)
        assert pnl["cashout_cost"] == pytest.approx(401)

    def test_cashout_with_reload(self):
        # Cashed out + reload, actual_return=158; potential was 1231
        rows = _make_rows((1, "K", 1, "win", 2.0))
        slips = _make_slips((1, 10, 1231, 1, 1, 158))
        pnl = compute_group_pnl(slips, rows)
        assert pnl["returned"] == pytest.approx(158)
        assert pnl["cashout_cost"] == pytest.approx(1073)

    def test_no_cashout_has_zero_cashout_cost(self):
        rows = _make_rows((1, "K", 1, "win", 2.0))
        slips = _make_slips((1, 10, 40))
        pnl = compute_group_pnl(slips, rows)
        assert pnl["cashout_cost"] == pytest.approx(0)

    def test_mixed_cashout_and_normal_weeks(self):
        # Week 1: normal win (potential=40); week 2: cashed out (actual=99, potential=500)
        rows = _make_rows(
            (1, "K", 1, "win", 2.0),
            (1, "K", 2, "win", 5.0),
        )
        slips = _make_slips((1, 10, 40), (2, 10, 500, 1, 0, 99))
        pnl = compute_group_pnl(slips, rows)
        assert pnl["staked"] == pytest.approx(20)
        assert pnl["returned"] == pytest.approx(139)   # 40 + 99
        assert pnl["cashout_cost"] == pytest.approx(401)


# ---------------------------------------------------------------------------
# compute_singles_pnl
# ---------------------------------------------------------------------------

class TestComputeSinglesPnl:
    def test_win_profit(self):
        rows = _make_rows((1, "Kevin", 1, "win", 3.0))
        # No slips → default €20 stake; profit = 20 * (3 - 1) = 40
        result = compute_singles_pnl(rows, [], default_stake=20.0)
        assert result[1]["pnl"] == pytest.approx(40.0)

    def test_loss_deduct(self):
        rows = _make_rows((1, "Kevin", 1, "loss", 2.0))
        result = compute_singles_pnl(rows, [], default_stake=20.0)
        assert result[1]["pnl"] == pytest.approx(-20.0)

    def test_mixed_results(self):
        rows = _make_rows(
            (1, "Kevin", 1, "win", 2.0),   # +20
            (1, "Kevin", 2, "loss", 2.0),  # -20
        )
        result = compute_singles_pnl(rows, [], default_stake=20.0)
        assert result[1]["pnl"] == pytest.approx(0.0)

    def test_uses_confirmed_odds(self):
        rows = _make_rows((1, "Kevin", 1, "win", 2.0, 4.0))  # confirmed=4.0
        result = compute_singles_pnl(rows, [], default_stake=20.0)
        assert result[1]["pnl"] == pytest.approx(60.0)  # 20 * (4 - 1)

    def test_ignores_actual_slip_stake(self):
        # Bet slip stake is irrelevant — always uses default_stake per pick
        rows = _make_rows(
            (1, "Kevin", 1, "win", 3.0),
            (2, "Dermot", 1, "loss", 2.0),
        )
        slips = _make_slips((1, 5, 100))  # slip stake €5 — should have no effect
        result = compute_singles_pnl(rows, slips, default_stake=20.0)
        # Kevin: 20 * (3-1) = 40
        assert result[1]["pnl"] == pytest.approx(40.0)
        # Dermot: -20
        assert result[2]["pnl"] == pytest.approx(-20.0)


# ---------------------------------------------------------------------------
# compute_what_could_have_been
# ---------------------------------------------------------------------------

class TestComputeWhatCouldHaveBeen:
    def test_sole_loser_with_slip(self):
        rows = _make_rows(
            (1, "Kevin", 1, "loss", 2.0),
            (2, "Dermot", 1, "win", 3.0),
        )
        slips = _make_slips((1, 10, 1231))
        result = compute_what_could_have_been(rows, slips)
        assert len(result) == 1
        assert result[0]["formal_name"] == "Kevin"
        assert result[0]["week_number"] == 1
        assert result[0]["potential_return"] == pytest.approx(1231)

    def test_multiple_losers_excluded(self):
        rows = _make_rows(
            (1, "Kevin", 1, "loss", 2.0),
            (2, "Dermot", 1, "loss", 3.0),
        )
        slips = _make_slips((1, 10, 500))
        result = compute_what_could_have_been(rows, slips)
        assert result == []

    def test_no_slip_excluded(self):
        rows = _make_rows(
            (1, "Kevin", 1, "loss", 2.0),
            (2, "Dermot", 1, "win", 3.0),
        )
        result = compute_what_could_have_been(rows, [])
        assert result == []

    def test_multiple_sole_loser_weeks(self):
        rows = _make_rows(
            (1, "Kevin", 1, "loss", 2.0),
            (2, "Dermot", 1, "win", 3.0),
            (1, "Kevin", 2, "win", 2.0),
            (2, "Dermot", 2, "loss", 3.0),
        )
        slips = _make_slips((1, 10, 500), (2, 10, 800))
        result = compute_what_could_have_been(rows, slips)
        assert len(result) == 2
        assert result[0]["week_number"] == 1
        assert result[1]["week_number"] == 2


# ---------------------------------------------------------------------------
# compute_biggest_winner
# ---------------------------------------------------------------------------

class TestComputeBiggestWinner:
    def test_returns_highest_odds_winner(self):
        rows = _make_rows(
            (1, "Kevin", 1, "win", 3.0),
            (2, "Dermot", 1, "win", 5.0),
        )
        result = compute_biggest_winner(rows)
        assert result["formal_name"] == "Dermot"
        assert result["odds"] == pytest.approx(5.0)

    def test_ignores_losses(self):
        rows = _make_rows(
            (1, "Kevin", 1, "loss", 10.0),
            (2, "Dermot", 1, "win", 3.0),
        )
        result = compute_biggest_winner(rows)
        assert result["formal_name"] == "Dermot"

    def test_no_wins_returns_none(self):
        rows = _make_rows((1, "Kevin", 1, "loss", 3.0))
        assert compute_biggest_winner(rows) is None

    def test_uses_confirmed_odds(self):
        rows = _make_rows((1, "Kevin", 1, "win", 2.0, 7.0))
        result = compute_biggest_winner(rows)
        assert result["odds"] == pytest.approx(7.0)

    def test_includes_description(self):
        rows = _make_rows((1, "Kevin", 1, "win", 3.0, None, "Gaelic Warrior to win"))
        result = compute_biggest_winner(rows)
        assert result["description"] == "Gaelic Warrior to win"


# ---------------------------------------------------------------------------
# compute_awards
# ---------------------------------------------------------------------------

class TestComputeAwards:
    def test_optimist_picks_highest_avg_odds(self):
        rows = _make_rows(
            (1, "Kevin", 1, "win", 2.0),
            (2, "Dermot", 1, "win", 5.0),
        )
        awards = compute_awards(rows)
        assert awards["optimist"]["formal_name"] == "Dermot"
        assert awards["optimist"]["avg_odds"] == pytest.approx(5.0)

    def test_cold_spell_finds_longest_streak(self):
        rows = _make_rows(
            (1, "Kevin", 1, "loss", 2.0),
            (1, "Kevin", 2, "loss", 2.0),
            (1, "Kevin", 3, "win", 2.0),
            (2, "Dermot", 1, "loss", 3.0),
            (2, "Dermot", 2, "loss", 3.0),
            (2, "Dermot", 3, "loss", 3.0),
        )
        awards = compute_awards(rows)
        assert awards["cold_spell"]["formal_name"] == "Dermot"
        assert awards["cold_spell"]["streak"] == 3

    def test_cold_spell_tie_broken_by_most_recent(self):
        # Kevin streak of 2 ends at week 2; Ronan streak of 2 ends at week 5
        # Ronan's is more recent so Ronan wins the tie
        rows = _make_rows(
            (1, "Kevin", 1, "loss", 2.0),
            (1, "Kevin", 2, "loss", 2.0),
            (1, "Kevin", 3, "win", 2.0),
            (1, "Kevin", 4, "win", 2.0),
            (1, "Kevin", 5, "win", 2.0),
            (2, "Ronan", 1, "win", 2.0),
            (2, "Ronan", 2, "win", 2.0),
            (2, "Ronan", 3, "win", 2.0),
            (2, "Ronan", 4, "loss", 2.0),
            (2, "Ronan", 5, "loss", 2.0),
        )
        awards = compute_awards(rows)
        assert awards["cold_spell"]["formal_name"] == "Ronan"
        assert awards["cold_spell"]["streak"] == 2

    def test_cold_spell_none_if_all_streaks_below_2(self):
        rows = _make_rows(
            (1, "Kevin", 1, "loss", 2.0),
            (1, "Kevin", 2, "win", 2.0),
        )
        awards = compute_awards(rows)
        assert awards["cold_spell"] is None

    def test_cold_spell_exactly_2(self):
        rows = _make_rows(
            (1, "Kevin", 1, "loss", 2.0),
            (1, "Kevin", 2, "loss", 2.0),
        )
        awards = compute_awards(rows)
        assert awards["cold_spell"] is not None
        assert awards["cold_spell"]["streak"] == 2


# ---------------------------------------------------------------------------
# get_period_data (integration — uses real DB via conftest)
# ---------------------------------------------------------------------------

class TestGetPeriodData:
    def _seed(self, season="2026", group_id="default"):
        conn = get_db()
        # Use the first seeded player
        player_id = conn.execute("SELECT id FROM players LIMIT 1").fetchone()[0]
        # Create weeks 1-5
        week_ids = {}
        for wk in range(1, 6):
            conn.execute(
                "INSERT INTO weeks (week_number, season, deadline, status, group_id) "
                "VALUES (?, ?, '2026-01-01', 'completed', ?)",
                (wk, season, group_id),
            )
            row = conn.execute(
                "SELECT id FROM weeks WHERE week_number = ? AND season = ? AND group_id = ?",
                (wk, season, group_id),
            ).fetchone()
            week_ids[wk] = row[0]
            conn.execute(
                "INSERT INTO picks (week_id, player_id, description, odds_decimal, odds_original) "
                "VALUES (?, ?, 'Test pick', 2.0, 'evens')",
                (week_ids[wk], player_id),
            )
            pick_row = conn.execute(
                "SELECT id FROM picks WHERE week_id = ? AND player_id = ?",
                (week_ids[wk], player_id),
            ).fetchone()
            outcome = "win" if wk % 2 == 1 else "loss"
            conn.execute(
                "INSERT INTO results (pick_id, outcome, confirmed_at) VALUES (?, ?, '2026-01-01')",
                (pick_row[0], outcome),
            )
        conn.commit()
        conn.close()
        return week_ids

    def test_returns_correct_week_range(self):
        self._seed()
        data = get_period_data("2026", 5)
        assert data["start_week"] == 1
        assert data["end_week"] == 5
        assert len(data["player_rows"]) == 5

    def test_excludes_weeks_outside_range(self):
        self._seed()
        # Add a week 6 result
        conn = get_db()
        player_id = conn.execute("SELECT id FROM players LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT INTO weeks (week_number, season, deadline, status, group_id) "
            "VALUES (6, '2026', '2026-01-01', 'completed', 'default')"
        )
        wk6_id = conn.execute(
            "SELECT id FROM weeks WHERE week_number = 6"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO picks (week_id, player_id, description, odds_decimal, odds_original) "
            "VALUES (?, ?, 'Week 6 pick', 2.0, 'evens')", (wk6_id, player_id)
        )
        pick6 = conn.execute(
            "SELECT id FROM picks WHERE week_id = ?", (wk6_id,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO results (pick_id, outcome, confirmed_at) VALUES (?, 'win', '2026-01-07')",
            (pick6,),
        )
        conn.commit()
        conn.close()

        data = get_period_data("2026", 5)
        # Should still only have 5 rows (weeks 1-5)
        assert len(data["player_rows"]) == 5
        assert all(r["week_number"] <= 5 for r in data["player_rows"])

    def test_empty_when_no_data(self):
        data = get_period_data("2099", 5)
        assert data["player_rows"] == []
        assert data["bet_slips"] == []


# ---------------------------------------------------------------------------
# punter_report_display (butler formatting)
# ---------------------------------------------------------------------------

class TestPunterReportDisplay:
    def _minimal_data(self):
        return {
            "season": "2026",
            "start_week": 1,
            "end_week": 5,
            "player_rows": _make_rows(
                (1, "Mr Kevin", 1, "win", 2.0),
                (1, "Mr Kevin", 2, "loss", 2.0),
                (2, "Mr Dermot", 1, "win", 3.0),
                (2, "Mr Dermot", 2, "win", 3.0),
            ),
            "bet_slips": _make_slips((1, 10, 30), (2, 10, 0)),
            "penalties": [],
            "weeks_count": 2,
        }

    def test_contains_header(self):
        text = butler.punter_report_display(self._minimal_data())
        assert "The Punter Report" in text
        assert "Weeks 1" in text

    def test_contains_leaderboard(self):
        text = butler.punter_report_display(self._minimal_data())
        assert "Mr Kevin" in text
        assert "Mr Dermot" in text

    def test_no_bet_slips_skips_pnl(self):
        data = self._minimal_data()
        data["bet_slips"] = []
        text = butler.punter_report_display(data)
        # Group P&L line only appears when staked > 0
        assert "Group P&L" not in text

    def test_no_penalties_skips_section(self):
        # Use data where both players lose week 2 — no sole loser, no DB penalties
        data = self._minimal_data()
        data["penalties"] = []
        data["player_rows"] = _make_rows(
            (1, "Mr Kevin", 1, "win", 2.0),
            (1, "Mr Kevin", 2, "loss", 2.0),
            (2, "Mr Dermot", 1, "win", 3.0),
            (2, "Mr Dermot", 2, "loss", 3.0),
        )
        text = butler.punter_report_display(data)
        assert "Penalties" not in text

    def test_with_cash_penalty(self):
        data = self._minimal_data()
        data["penalties"] = [{"player_id": 1, "formal_name": "Mr Kevin", "amount": 50, "type": "streak_5"}]
        text = butler.punter_report_display(data)
        assert "Penalties" in text
        assert "Mr Kevin" in text
        assert "€50 fine" in text

    def test_with_rotation_penalty(self):
        data = self._minimal_data()
        data["penalties"] = [{"player_id": 1, "formal_name": "Mr Kevin", "amount": 0, "type": "streak_3"}]
        text = butler.punter_report_display(data)
        assert "Penalties" in text
        assert "Mr Kevin" in text
        assert "placed following week's bet" in text
        assert "\u20ac0 fine" not in text

    def test_awards_section(self):
        text = butler.punter_report_display(self._minimal_data())
        assert "Awards" in text

    def test_cashout_cost_shown_when_present(self):
        data = self._minimal_data()
        # Week 1: cashed out at 99, potential was 300
        data["bet_slips"] = _make_slips((1, 10, 300, 1, 0, 99), (2, 10, 0))
        text = butler.punter_report_display(data)
        assert "Cashout cost" in text
        assert "201" in text  # 300 - 99 = 201

    def test_cashout_cost_hidden_when_zero(self):
        data = self._minimal_data()
        # Normal slips, no cashout
        data["bet_slips"] = _make_slips((1, 10, 30), (2, 10, 0))
        text = butler.punter_report_display(data)
        assert "Cashout cost" not in text

    def test_what_could_have_been_shown_for_sole_loser(self):
        # Week 1: sole loser (only Mr Kevin loses); week 2: both lose
        data = self._minimal_data()
        data["player_rows"] = _make_rows(
            (1, "Mr Kevin", 1, "loss", 2.0),
            (2, "Mr Dermot", 1, "win", 3.0),
            (1, "Mr Kevin", 2, "loss", 2.0),
            (2, "Mr Dermot", 2, "loss", 3.0),
        )
        data["bet_slips"] = _make_slips((1, 10, 500), (2, 10, 300))
        text = butler.punter_report_display(data)
        assert "What Could Have Been" in text
        assert "Mr Kevin" in text
        assert "500" in text
        # Week 2 (multiple losers) should not appear
        assert "300" not in text

    def test_what_could_have_been_hidden_when_no_sole_losers(self):
        data = self._minimal_data()
        # Both players lose week 1 — no sole loser
        data["player_rows"] = _make_rows(
            (1, "Mr Kevin", 1, "loss", 2.0),
            (2, "Mr Dermot", 1, "loss", 3.0),
        )
        text = butler.punter_report_display(data)
        assert "What Could Have Been" not in text
