"""
Punter Report service — end-of-5-week statistical summary.

Queries picks, results, bet_slips, and penalties for a 5-week period and
publishes a formatted report to the group.  Best-effort; never raises.
"""

import logging
from datetime import datetime, timedelta

from src.db import get_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data query
# ---------------------------------------------------------------------------

def get_period_data(season, end_week, group_id="default"):
    """
    Query all picks, results, bet_slips, and penalties for weeks
    (end_week - 4) through end_week in the given season and group.

    Returns a dict with keys:
      season, end_week, start_week, group_id,
      player_rows   — list of {player_id, formal_name, week_number,
                               outcome, odds_decimal, confirmed_odds, description}
      bet_slips     — list of {week_number, stake, potential_return}
      penalties     — list of {player_id, formal_name, amount, type}
      weeks_count   — number of distinct weeks in the period with any results
    """
    start_week = end_week - 4
    conn = get_db()

    player_rows = conn.execute(
        """
        SELECT p.player_id, pl.formal_name, r.outcome,
               p.odds_decimal, p.confirmed_odds, w.week_number, p.description
        FROM picks p
        JOIN players pl ON p.player_id = pl.id
        JOIN weeks w ON p.week_id = w.id
        LEFT JOIN results r ON r.pick_id = p.id
        WHERE w.season = ? AND w.week_number BETWEEN ? AND ?
          AND w.group_id = ? AND r.outcome IN ('win', 'loss')
        ORDER BY w.week_number, p.player_id
        """,
        (season, start_week, end_week, group_id),
    ).fetchall()

    bet_slips = conn.execute(
        """
        SELECT bs.stake, bs.potential_return, bs.cashed_out, bs.reloaded, bs.actual_return,
               w.week_number
        FROM bet_slips bs
        JOIN weeks w ON bs.week_id = w.id
        WHERE w.season = ? AND w.week_number BETWEEN ? AND ?
          AND w.group_id = ?
        """,
        (season, start_week, end_week, group_id),
    ).fetchall()

    # Return individual penalty records (not aggregated) so we can
    # distinguish cash fines from rotation-queue placements.
    penalties = conn.execute(
        """
        SELECT pen.player_id, pl.formal_name, pen.amount, pen.type
        FROM penalties pen
        JOIN weeks w ON pen.week_id = w.id
        JOIN players pl ON pen.player_id = pl.id
        WHERE w.season = ? AND w.week_number BETWEEN ? AND ?
          AND w.group_id = ?
          AND pen.status IN ('confirmed', 'paid')
        ORDER BY pen.player_id
        """,
        (season, start_week, end_week, group_id),
    ).fetchall()

    # Count distinct completed weeks in the period
    weeks_count_row = conn.execute(
        """
        SELECT COUNT(DISTINCT week_number) FROM weeks
        WHERE season = ? AND week_number BETWEEN ? AND ?
          AND group_id = ? AND status = 'completed'
        """,
        (season, start_week, end_week, group_id),
    ).fetchone()
    conn.close()

    return {
        "season": season,
        "end_week": end_week,
        "start_week": start_week,
        "group_id": group_id,
        "player_rows": [dict(r) for r in player_rows],
        "bet_slips": [dict(r) for r in bet_slips],
        "penalties": [dict(r) for r in penalties],
        "weeks_count": weeks_count_row[0] if weeks_count_row else 0,
    }


# ---------------------------------------------------------------------------
# Stat computations
# ---------------------------------------------------------------------------

def compute_leaderboard(player_rows, start_week, end_week):
    """
    Returns a list of dicts sorted by win_rate DESC, then avg_odds DESC (tie-breaker):
      {player_id, formal_name, wins, losses, total, win_rate, form, avg_odds}

    form — one emoji per week (earliest left) indicating win/loss for that week.
    avg_odds — average of COALESCE(confirmed_odds, odds_decimal) across picks.
    """
    by_player = {}
    player_week_outcomes = {}  # player_id -> {week_number -> outcome}

    for row in player_rows:
        pid = row["player_id"]
        if pid not in by_player:
            by_player[pid] = {
                "player_id": pid,
                "formal_name": row["formal_name"],
                "wins": 0,
                "losses": 0,
                "total": 0,
                "odds_sum": 0.0,
                "odds_count": 0,
            }
            player_week_outcomes[pid] = {}

        outcome = row["outcome"]
        week_num = row["week_number"]
        player_week_outcomes[pid][week_num] = outcome

        p = by_player[pid]
        if outcome == "win":
            p["wins"] += 1
        elif outcome == "loss":
            p["losses"] += 1
        p["total"] += 1

        eff_odds = row["confirmed_odds"] or row["odds_decimal"]
        if eff_odds:
            p["odds_sum"] += float(eff_odds)
            p["odds_count"] += 1

    result = []
    for pid, p in by_player.items():
        win_rate = (p["wins"] / p["total"] * 100) if p["total"] > 0 else 0.0
        avg_odds = (p["odds_sum"] / p["odds_count"]) if p["odds_count"] > 0 else None

        # Form string: one emoji per week in chronological order
        form_chars = []
        for wk in range(start_week, end_week + 1):
            outcome = player_week_outcomes[pid].get(wk)
            if outcome == "win":
                form_chars.append("\u2705")
            elif outcome == "loss":
                form_chars.append("\u274c")
        form = "".join(form_chars) if form_chars else "-"

        result.append({
            "player_id": pid,
            "formal_name": p["formal_name"],
            "wins": p["wins"],
            "losses": p["losses"],
            "total": p["total"],
            "win_rate": win_rate,
            "form": form,
            "avg_odds": avg_odds,
        })

    # Sort by win_rate DESC, then avg_odds DESC as tie-breaker
    result.sort(key=lambda x: (-x["win_rate"], -(x["avg_odds"] or 0)))
    return result


def compute_sole_losers(player_rows):
    """
    For each week in the period, find weeks where exactly one player lost
    (i.e. they were solely responsible for killing the acca).

    Returns list of {player_id, formal_name, week_number}, sorted by week.
    """
    from collections import defaultdict
    week_outcomes = defaultdict(dict)  # week_number -> {player_id: outcome}
    player_names = {}
    for row in player_rows:
        week_outcomes[row["week_number"]][row["player_id"]] = row["outcome"]
        player_names[row["player_id"]] = row["formal_name"]

    sole_losers = []
    for week_num in sorted(week_outcomes):
        outcomes = week_outcomes[week_num]
        losers = [pid for pid, outcome in outcomes.items() if outcome == "loss"]
        if len(losers) == 1:
            pid = losers[0]
            sole_losers.append({
                "player_id": pid,
                "formal_name": player_names[pid],
                "week_number": week_num,
            })
    return sole_losers


def compute_acca_record(bet_slips, player_rows):
    """
    Returns (wins, total_with_slip) — count of weeks where all picks won
    among the weeks that have a bet slip.
    """
    if not bet_slips:
        return 0, 0

    slipped_weeks = {bs["week_number"] for bs in bet_slips}
    loss_weeks = {row["week_number"] for row in player_rows if row["outcome"] == "loss"}

    acca_wins = sum(1 for wk in slipped_weeks if wk not in loss_weeks)
    return acca_wins, len(slipped_weeks)


def compute_group_pnl(bet_slips, player_rows):
    """
    Returns {staked, returned, net, cashout_cost}.

    For cashed-out weeks: returned += actual_return; cashout_cost += potential_return - actual_return.
    For normal win weeks: returned += potential_return.
    Loss weeks (non-cashout) contribute nothing to returned.
    """
    if not bet_slips:
        return {"staked": 0.0, "returned": 0.0, "net": 0.0, "cashout_cost": 0.0}

    loss_weeks = {row["week_number"] for row in player_rows if row["outcome"] == "loss"}
    cashout_cost = 0.0
    staked = sum(float(bs["stake"] or 0) for bs in bet_slips)
    returned = 0.0
    for bs in bet_slips:
        if bs.get("cashed_out"):
            actual = float(bs["actual_return"] or 0)
            returned += actual
            cashout_cost += float(bs["potential_return"] or 0) - actual
        elif bs["week_number"] not in loss_weeks:
            returned += float(bs["potential_return"] or 0)
    return {"staked": staked, "returned": returned, "net": returned - staked, "cashout_cost": cashout_cost}


def compute_what_could_have_been(player_rows, bet_slips):
    """
    For weeks with exactly one loser, return the acca payout that was missed.

    Returns list of {player_id, formal_name, week_number, potential_return},
    sorted by week, only for sole-loser weeks that have a bet slip with a
    potential_return value.
    """
    sole_losers = compute_sole_losers(player_rows)
    if not sole_losers:
        return []

    slip_by_week = {bs["week_number"]: bs for bs in bet_slips}

    result = []
    for sl in sole_losers:
        bs = slip_by_week.get(sl["week_number"])
        if bs and bs.get("potential_return"):
            result.append({
                "player_id": sl["player_id"],
                "formal_name": sl["formal_name"],
                "week_number": sl["week_number"],
                "potential_return": float(bs["potential_return"]),
            })
    return result


def compute_singles_pnl(player_rows, bet_slips, default_stake=20.0):
    """
    Hypothetical P&L per player if each pick were a standalone single at default_stake.

    For a winning pick at odds X with stake S:  profit = S × (X − 1)
    For a losing pick:                          profit = −S

    A fixed stake (default_stake) is used for every pick — this is a
    hypothetical "what if each pick was a €20 bet on its own" calculation,
    independent of the actual acca stake.

    Returns dict: player_id -> {formal_name, pnl}.
    """
    by_player = {}
    for row in player_rows:
        pid = row["player_id"]
        if pid not in by_player:
            by_player[pid] = {"formal_name": row["formal_name"], "pnl": 0.0}

        eff_odds = float(row["confirmed_odds"] or row["odds_decimal"] or 2.0)
        if row["outcome"] == "win":
            by_player[pid]["pnl"] += default_stake * (eff_odds - 1)
        elif row["outcome"] == "loss":
            by_player[pid]["pnl"] -= default_stake

    return by_player


def compute_biggest_winner(player_rows):
    """
    Returns dict {player_id, formal_name, description, odds} for the pick with
    the highest effective odds that resulted in a win.
    Returns None if no wins.
    """
    best = None
    best_odds = 0.0
    for row in player_rows:
        if row["outcome"] != "win":
            continue
        eff_odds = float(row["confirmed_odds"] or row["odds_decimal"] or 0)
        if eff_odds > best_odds:
            best_odds = eff_odds
            best = row

    if not best:
        return None
    return {
        "player_id": best["player_id"],
        "formal_name": best["formal_name"],
        "description": best.get("description"),
        "odds": best_odds,
    }


def compute_awards(player_rows):
    """
    Returns:
      optimist:   {player_id, formal_name, avg_odds}  — highest avg odds player
      cold_spell: {player_id, formal_name, streak}    — longest consec loss streak,
                  tie-broken by most recent (highest end-week); None if all streaks < 2
    """
    # Average odds per player
    odds_sum = {}
    odds_count = {}
    for row in player_rows:
        pid = row["player_id"]
        eff = float(row["confirmed_odds"] or row["odds_decimal"] or 0)
        if eff > 0:
            odds_sum[pid] = odds_sum.get(pid, 0.0) + eff
            odds_count[pid] = odds_count.get(pid, 0) + 1

    names = {row["player_id"]: row["formal_name"] for row in player_rows}

    optimist = None
    best_avg = 0.0
    for pid, total in odds_sum.items():
        avg = total / odds_count[pid]
        if avg > best_avg:
            best_avg = avg
            optimist = {"player_id": pid, "formal_name": names[pid], "avg_odds": avg}

    # Cold spell: find longest consecutive loss streak; tie-break by most recent end week
    cold_spell = None
    by_player_ordered = {}
    for row in sorted(player_rows, key=lambda r: r["week_number"]):
        pid = row["player_id"]
        by_player_ordered.setdefault(pid, []).append((row["week_number"], row["outcome"]))

    worst_streak = 1
    worst_streak_end_week = -1
    for pid, week_outcomes in by_player_ordered.items():
        streak = 0
        max_streak = 0
        max_streak_end_week = -1
        for week_num, outcome in week_outcomes:
            if outcome == "loss":
                streak += 1
                if streak > max_streak:
                    max_streak = streak
                    max_streak_end_week = week_num
            else:
                streak = 0

        # Update if longer streak, or equal streak ending more recently
        if max_streak > worst_streak or (
            max_streak == worst_streak and max_streak_end_week > worst_streak_end_week
        ):
            worst_streak = max_streak
            worst_streak_end_week = max_streak_end_week
            cold_spell = {"player_id": pid, "formal_name": names[pid], "streak": max_streak}

    if cold_spell and cold_spell["streak"] < 2:
        cold_spell = None

    return {"optimist": optimist, "cold_spell": cold_spell}


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

def schedule_report(season, end_week, group_id="default"):
    """
    Schedule a one-shot APScheduler job to publish the report 24 hours from now.
    """
    try:
        from src.services.scheduler import _scheduler
        if _scheduler is None:
            logger.warning("Scheduler not available, skipping report scheduling")
            return

        run_date = datetime.utcnow() + timedelta(hours=24)
        job_id = f"punter_report_{season}_{end_week}_{group_id}"

        existing = _scheduler.get_job(job_id)
        if existing:
            existing.remove()

        _scheduler.add_job(
            publish_report,
            "date",
            run_date=run_date,
            args=[season, end_week, group_id],
            id=job_id,
            misfire_grace_time=300,
        )
        logger.info("Punter Report scheduled for %s (season %s week %s)", run_date, season, end_week)
    except Exception:
        logger.exception("Failed to schedule Punter Report")


def publish_report(season, end_week, group_id="default"):
    """
    Orchestrate: query data → compute stats → format → send to group.
    Best-effort — logs and silently returns on any failure.
    """
    try:
        from src.config import Config
        from src.services.scheduler import _send_fn

        data = get_period_data(season, end_week, group_id)
        if not data["player_rows"]:
            logger.info("No data for Punter Report (season %s week %s)", season, end_week)
            return

        import src.butler as butler
        text = butler.punter_report_display(data)

        chat_id = group_id if group_id != "default" else (
            Config.GROUP_CHAT_ID or (Config.GROUP_CHAT_IDS[0] if Config.GROUP_CHAT_IDS else None)
        )
        if chat_id and _send_fn:
            _send_fn(chat_id, text)
            logger.info("Punter Report posted for season %s weeks %s-%s",
                        season, data["start_week"], end_week)
        else:
            logger.warning("Cannot post Punter Report — no chat_id or send_fn")
    except Exception:
        logger.exception("Error publishing Punter Report")
