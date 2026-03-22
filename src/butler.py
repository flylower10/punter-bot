"""
The Betting Butler — message formatting module.

All bot responses are formatted through this module. When LLM is enabled,
responses are generated dynamically via Groq; otherwise falls back to templates.
"""

import logging
import re
from datetime import datetime

import pytz

from src import llm_client

logger = logging.getLogger(__name__)

# Abbreviations to formal names for pick display (case-insensitive)
PICK_ABBREVIATIONS = {
    # Football
    "leics": "Leicester",
    "soton": "Southampton",
    "man utd": "Manchester United",
    "man city": "Manchester City",
    "spurs": "Tottenham",
    "utd": "United",
    "villa": "Aston Villa",
    "wolves": "Wolverhampton",
    "newc": "Newcastle",
    "bha": "Brighton",
    "whu": "West Ham",
    "qpr": "Queens Park Rangers",
    # NFL
    "kc": "Kansas City",
    "sf": "San Francisco",
    "gb": "Green Bay",
    "ne": "New England",
    "tb": "Tampa Bay",
    # NBA
    "sixers": "Philadelphia 76ers",
    "cavs": "Cleveland Cavaliers",
    "mavs": "Dallas Mavericks",
}


def _frame(template, context, scenario=None, player_name=None):
    """
    Wrap template content with LLM opening/closing lines via get_framing().

    This is the live architecture: the LLM adds butler-voiced framing around
    structured template content, but never rewrites the content itself.
    Returns the template unchanged if LLM is disabled or fails.
    """
    full_context = f"{context}\n\nThe template that follows your opening line says: \"{template}\"\nDo not repeat any of this information."
    framing = llm_client.get_framing(full_context, scenario=scenario, player_name=player_name)
    opening = framing.get("opening", "").strip()
    closing = framing.get("closing", "").strip()
    parts = []
    if opening:
        parts.append(opening)
    parts.append(template)
    if closing:
        parts.append(closing)
    return "\n\n".join(parts) if len(parts) > 1 else template


def _formalize_pick(description):
    """Convert abbreviated pick text to formal display format."""
    if not description or not isinstance(description, str):
        return description
    text = description.strip()
    # Expand abbreviations (longest first to avoid partial matches)
    for abbr, full in sorted(PICK_ABBREVIATIONS.items(), key=lambda x: -len(x[0])):
        text = re.sub(r'\b' + re.escape(abbr) + r'\b', full, text, flags=re.IGNORECASE)
    # Replace "/" between team names with " vs " (not fractional odds like 4/6)
    text = re.sub(r"([a-zA-Z][a-zA-Z\s]*)/([a-zA-Z][a-zA-Z\s]*)", r"\1 vs \2", text)
    return text.strip()


def _first_name(player):
    """Extract the first name from formal_name (e.g. 'Mr Edmund' -> 'Edmund')."""
    formal = player.get("formal_name", "")
    return formal.replace("Mr ", "").strip() if formal.startswith("Mr ") else formal


def _strip_odds_for_display(text):
    """Remove odds from pick text so we don't repeat them when showing @ [odds]."""
    if not text:
        return text
    # Strip fractional odds (6/10, 21/20), decimal (2.0, 3.75), evens
    # Negative lookbehind: don't strip decimals preceded by +/- (handicaps like -10.5)
    text = re.sub(r"\b\d+/\d+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<![+-])\b\d+\.\d{1,2}\b", "", text)
    text = re.sub(r"\bevens?\b", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip().rstrip(".,")


def pick_confirmed(player, description, odds, is_update=False, placer=None, previous_description=None, first_of_week=False, last_pick=False, sport_clarification=None, picks_so_far=None):
    """Confirm a pick has been recorded."""
    formal = _formalize_pick(description)

    action = "Updated" if is_update else "Noted and recorded"
    if odds == "placer":
        placer_name = placer["formal_name"] if placer else "Placer"
        body = f"{formal} — {placer_name} to confirm odds when placing the bet."
    else:
        body = f"{_strip_odds_for_display(formal)} @ {odds}."
    if is_update and previous_description:
        previous_display = _strip_odds_for_display(_formalize_pick(previous_description))
        template = f"{action}, {player['formal_name']}.  Replacing {previous_display} with {body}"
    else:
        template = f"{action}, {player['formal_name']}.  {body}"

    # GAA dual-county clarification note
    if sport_clarification:
        template += f"\n(Recorded as {sport_clarification} — reply with your emoji prefix + 'hurling' or 'football' to correct.)"

    # When this is the last pick, skip LLM framing — the all_picks_in block provides context
    if last_pick:
        return template

    scenario = "pick_confirmed_first" if first_of_week and not is_update else "pick_confirmed"
    context = f"{player['formal_name']}'s pick recorded: {_strip_odds_for_display(formal)} @ {odds}."
    if picks_so_far is not None and picks_so_far > 1:
        context += f" Pick {picks_so_far} this week — not the first pick."
    return _frame(template, context, scenario=scenario, player_name=_first_name(player))


def picks_status(submitted, missing):
    """Show who has and hasn't submitted picks."""
    if not missing:
        return ""
    missing_lines = "\n".join(_emoji_name(p) for p in missing)
    return f"Awaiting selection from:\n{missing_lines}"


def _picks_grouped_lines(picks):
    """Build display lines for picks ordered by kickoff time.

    Groups by day and time with fixture names as headers. Unmatched picks appear
    under 'Kickoff TBC'. Result suffixes (✅/❌/Void) are appended when present.
    Returns a list of strings.
    """
    tz = pytz.timezone("Europe/Dublin")
    matched, unmatched = [], []
    for pick in picks:
        (matched if pick.get("kickoff") else unmatched).append(pick)

    # Group matched picks by (day, time) for bundled display
    groups = []  # list of (day_name, time_str, [(fixture, pick), ...])
    for pick in matched:
        ko = pick["kickoff"]
        if isinstance(ko, str):
            try:
                dt = datetime.fromisoformat(ko)
            except ValueError:
                dt = datetime.strptime(ko, "%Y-%m-%dT%H:%M:%S")
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
            dt_local = dt.astimezone(tz)
        else:
            dt_local = ko if ko.tzinfo else pytz.utc.localize(ko).astimezone(tz)

        day_name = dt_local.strftime("%A")
        time_str = dt_local.strftime("%-I:%M %p")
        fixture = f"{pick.get('home_team', '?')} vs {pick.get('away_team', '?')}"

        if groups and groups[-1][0] == day_name and groups[-1][1] == time_str:
            groups[-1][2].append((fixture, pick))
        else:
            groups.append((day_name, time_str, [(fixture, pick)]))

    result_suffix_map = {"win": " \u2705", "loss": " \u274c", "void": " Void"}

    lines = []
    current_day = None
    for day_name, time_str, fixture_picks in groups:
        if day_name != current_day:
            if lines:
                lines.append("")
            current_day = day_name
            lines.append(day_name)
        elif lines:
            lines.append("")

        lines.append(f"\u23f0 {time_str}")
        for fixture, pick in fixture_picks:
            lines.append(fixture)
            suffix = result_suffix_map.get(pick.get("result_outcome"), "")
            lines.append(_format_pick_line(pick) + suffix)

    if unmatched:
        if lines:
            lines.append("")
        lines.append("Kickoff TBC")
        for pick in unmatched:
            suffix = result_suffix_map.get(pick.get("result_outcome"), "")
            lines.append(_format_pick_line(pick) + suffix)

    return lines


def all_picks_in(placer, picks=None):
    """Announce all picks are in, who places the bet, and list all selections.

    When picks include kickoff data (from get_picks_for_week_by_kickoff), orders
    by kickoff time with day headers and fixture names. Unmatched picks appear
    under 'Kickoff TBC'.
    """
    header = (
        f"All selections have been received.  "
        f"{placer['formal_name']}, you are next in the rotation to place the wager."
    )
    if not picks:
        return header

    return header + "\n\n" + "\n".join(_picks_grouped_lines(picks))


def _format_pick_line(pick):
    """Format a single pick line: emoji formal_name — description @ odds."""
    emoji = _primary_emoji(pick.get("emoji", ""))
    prefix = f"{emoji} " if emoji else ""
    formal = _formalize_pick(pick.get("description", ""))
    display = _strip_odds_for_display(formal)
    odds = pick.get("odds_original", "")
    return f"{prefix}{pick['formal_name']} \u2014 {display} @ {odds}"


def pick_removed(player):
    """Confirm a player's pick has been removed."""
    return f"Understood, {player['formal_name']}.  Your pick has been removed — you may resubmit before the Friday deadline."


def bet_slip_received(player):
    """Confirm bet slip screenshot received from the placer."""
    return f"Thank you, {player['formal_name']}.  Bet slip received and recorded."


def result_announced(player, description, odds, outcome, streak=None, acca_lost=False, losers=None):
    """Announce a result."""
    formal = _formalize_pick(description)
    display_text = _strip_odds_for_display(formal) if odds != "placer" else formal

    if outcome == "win":
        emoji = "\u2705"
        scenario = "result_win_acca_lost" if acca_lost else "result_win"
    elif outcome == "loss":
        streak_num = 1
        if streak and streak.endswith("L"):
            streak_num = int(streak[:-1])
        emoji = "\u274c" * streak_num
        if streak_num in (3, 5, 7):
            scenario = f"result_streak_{streak_num}"
        elif acca_lost:
            scenario = "result_loss_acca_lost"
        else:
            scenario = "result_loss"
    else:
        emoji = "Void"
        scenario = "result_loss"

    template = f"{player['formal_name']} {emoji} \u2014 {display_text} @ {odds}"

    streak_ctx = f" ({streak} streak)" if streak else ""
    if acca_lost and losers:
        acca_ctx = f" The accumulator fell on {_join_names(losers)}'s selections."
    else:
        acca_ctx = ""
    context = f"{player['formal_name']}'s pick {outcome}: {display_text} @ {odds}.{streak_ctx}{acca_ctx}"
    return _frame(template, context, scenario=scenario, player_name=_first_name(player))


def penalty_suggested(player, streak_count, penalty_type, amount):
    """Suggest a penalty for Ed to confirm."""
    if penalty_type == "late":
        return (
            f"{player['formal_name']}, your selection was received after the deadline.  "
            f"You will place next week's wager.  Rotation queue updated."
        )
    if penalty_type == "streak_3":
        return (
            f"I regret to inform you that {player['formal_name']} has incurred "
            f"{streak_count} consecutive losses.  The suggested penalty is to pay "
            f"for next week's bet.  Mr Edmund, would you kindly confirm: "
            f"!confirm penalty {player['nickname']}"
        )
    return (
        f"I regret to inform you that {player['formal_name']} has incurred "
        f"{streak_count} consecutive losses.  The suggested penalty is "
        f"\u20ac{amount:.0f} to the vault.  Mr Edmund, would you kindly confirm: "
        f"!confirm penalty {player['nickname']}"
    )


def penalty_confirmed(player, amount, vault_total):
    """Confirm a penalty has been applied."""
    if amount > 0:
        return (
            f"Penalty confirmed.  Vault updated: \u20ac{vault_total:.0f} total.\n"
            f"{player['formal_name']}, please send \u20ac{amount:.0f} to Mr Edmund via Revolut."
        )
    return (
        f"Penalty confirmed.  {player['formal_name']} will place next week's wager."
    )


def week_complete_summary(results, week_number, leaderboard, rotation_next):
    """
    Combined weekend summary and weekly recap, published when the final result is in.
    """
    winners = [r for r in results if r["outcome"] == "win"]
    losers = [r for r in results if r["outcome"] == "loss"]
    won_count = len(winners)
    total = len(results)

    winner_names = [r["formal_name"] for r in winners]
    loser_names = [r["formal_name"] for r in losers]

    lines = [f"Weekend complete \u2014 Week {week_number}."]
    if winner_names:
        lines.append(f"Won: {', '.join(winner_names)}")
    if loser_names:
        lines.append(f"Lost: {', '.join(loser_names)}")
    lines.append(f"Accumulator: {'Won' if won_count == total else 'Lost'} ({won_count} of {total} won)")

    lb_section = _format_leaderboard_section(leaderboard, rotation_next)
    if lb_section:
        lines.extend(["", lb_section])

    return "\n".join(lines)


def _format_leaderboard_section(leaderboard, rotation_next):
    """Format the leaderboard section for the week summary."""
    if not leaderboard or not rotation_next or not rotation_next.get("formal_name"):
        return ""
    lines = [
        "\U0001f3c6 LEADERBOARD",
        "\u2501" * 22,
    ]
    medals = ["\U0001f947", "\U0001f948", "\U0001f949"]
    for i, entry in enumerate(leaderboard):
        medal = medals[i] if i < 3 else "  "
        lines.append(
            f"{medal} {entry['formal_name']}: {entry['win_rate']:.1f}% "
            f"({entry['wins']}/{entry['total']})"
        )
        lines.append(f"   Form: {entry['form']}")
    lines.extend(["", f"Next to place: {rotation_next['formal_name']}"])
    return "\n".join(lines)


def reminder_thursday():
    """Thursday 7PM reminder to all players."""
    template = "Picks are due by 10 PM Friday."
    return _frame(template, "Thursday evening reminder to the group.",
                  scenario="reminder_thursday")


def reminder_friday(missing):
    """Friday 7PM reminder to missing players."""
    names = [p["formal_name"] for p in missing]
    template = (
        f"Pardon the interruption.  {_join_names(names)} \u2014 "
        f"3 hours remain to submit your selections."
    )
    return _frame(template, "Friday evening reminder to missing players.",
                  scenario="reminder_friday")


def reminder_final(missing):
    """Friday 9:30PM final warning."""
    names = [p["formal_name"] for p in missing]
    template = (
        f"I do hope you'll forgive the urgency.  {_join_names(names)} \u2014 "
        f"30 minutes remain.  This is the final reminder."
    )
    return _frame(template, "Final reminder before the deadline.",
                  scenario="reminder_final")


def rotation_display(next_placer, queue, last_placer=None, last_week=None):
    """Format the rotation queue for display."""
    lines = [
        "\U0001f504 ROTATION STATUS",
        "\u2501" * 22,
    ]

    if last_placer and last_week:
        lp_emoji = _primary_emoji(last_placer.get("emoji", ""))
        lp_prefix = f"{lp_emoji} " if lp_emoji else ""
        lines.append(f"Last Placed: {lp_prefix}{last_placer['formal_name']} (Week {last_week})")

    np_emoji = _primary_emoji(next_placer.get("emoji", ""))
    np_prefix = f"{np_emoji} " if np_emoji else ""
    lines.append(f"Next Up: {np_prefix}{next_placer['formal_name']} \U0001f448")
    lines.append("")
    lines.append("Queue:")

    for i, entry in enumerate(queue, 1):
        emoji = _primary_emoji(entry.get("emoji", ""))
        prefix = f"{emoji} " if emoji else ""
        suffix = f" (penalty \u2014 {entry['reason']})" if entry.get("reason") else ""
        lines.append(f"{i}. {prefix}{entry['formal_name']}{suffix}")

    return "\n".join(lines)


def stats_display(player, stats):
    """Format player statistics."""
    lines = [
        f"\U0001f4ca {player['formal_name']}'s Statistics",
        "\u2501" * 22,
        f"Win Rate: {stats['win_rate']:.1f}% ({stats['wins']}/{stats['total']})",
        f"Current Streak: {stats['streak']}",
        f"Form: {stats['form']}",
    ]
    return "\n".join(lines)


def leaderboard_display(entries):
    """Format the leaderboard."""
    lines = [
        "\U0001f3c6 LEADERBOARD",
        "\u2501" * 22,
    ]

    medals = ["\U0001f947", "\U0001f948", "\U0001f949"]
    for i, entry in enumerate(entries):
        medal = medals[i] if i < 3 else "  "
        lines.append(
            f"{medal} {entry['formal_name']}: {entry['win_rate']:.1f}% "
            f"({entry['wins']}/{entry['total']})"
        )
        lines.append(f"   Form: {entry['form']}")
        lines.append("")

    return "\n".join(lines).rstrip()


def vault_display(total):
    """Format vault total."""
    return f"Vault balance: \u20ac{total:.0f}"


def picks_display(picks, week_number=None):
    """Format current week's picks for display. Shows result (✅/❌) when available.

    When picks include kickoff data (from get_picks_for_week_by_kickoff), uses the
    same day/time/fixture grouped format as the all_picks_in announcement.
    """
    if not picks:
        return "No picks recorded for this week yet."
    lines = ["\U0001f4dc RECORDED PICKS", "\u2501" * 22]
    if week_number:
        lines.append(f"Week {week_number}")
        lines.append("")

    if any("kickoff" in p for p in picks):
        lines += _picks_grouped_lines(picks)
    else:
        for p in picks:
            odds = p["odds_original"] if p["odds_original"] != "placer" else "(placer to confirm)"
            formal = _formalize_pick(p["description"])
            display_text = _strip_odds_for_display(formal) if p["odds_original"] != "placer" else formal
            result_suffix = ""
            outcome = p.get("result_outcome")
            if outcome == "win":
                result_suffix = " \u2705"
            elif outcome == "loss":
                result_suffix = " \u274c"
            elif outcome == "void":
                result_suffix = " Void"
            emoji = _primary_emoji(p.get("emoji", ""))
            prefix = f"{emoji} " if emoji else ""
            lines.append(f"{prefix}{p['formal_name']}: {display_text} @ {odds}{result_suffix}")

    return "\n".join(lines)


def banter_reply(sender, body, player=None):
    """
    Generate a banter response when the bot is mentioned or Brian is stirring.

    Returns a string response, or None if the LLM has nothing to say.
    """
    player_name = _first_name(player) if player else sender

    # Determine scenario
    if sender and sender.lower().startswith("brian"):
        scenario = "brian_stirring"
    else:
        scenario = "bot_mentioned"

    context = (
        f'{sender} said in the group chat: "{body}"\n\n'
        f"Respond in character. One sentence."
    )

    response = llm_client.generate(context, scenario=scenario, player_name=player_name)
    return response if response else None


def _primary_emoji(emoji_str):
    """Get the primary emoji from a comma-separated emoji string."""
    if not emoji_str:
        return ""
    return emoji_str.split(",")[0].strip()


def _emoji_name(player):
    """Format as 'emoji Mr Name' e.g. '🍋 Mr Edmund'."""
    emoji = _primary_emoji(player.get("emoji", ""))
    prefix = f"{emoji} " if emoji else ""
    return f"{prefix}{player['formal_name']}"


def _early_kickoff_note(kickoff_str):
    """Return early-kickoff warning if fixture is before Sat 12:30 PM Dublin time, else None."""
    if not kickoff_str:
        return None
    tz = pytz.timezone("Europe/Dublin")
    try:
        dt = datetime.fromisoformat(kickoff_str) if isinstance(kickoff_str, str) else kickoff_str
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    dt_local = dt.astimezone(tz)

    # Any kickoff Wed/Thu/Fri or Sat before 12:30 PM is "early"
    if dt_local.weekday() == 5:
        # Saturday — only early if before 12:30
        cutoff = dt_local.replace(hour=12, minute=30, second=0, microsecond=0)
        if dt_local >= cutoff:
            return None
    elif dt_local.weekday() in (0, 1, 6):
        # Sun/Mon/Tue — not in the pick window, not early
        return None
    # Wed/Thu/Fri or Sat before 12:30 → early

    day_name = dt_local.strftime("%A")
    time_str = dt_local.strftime("%-I:%M %p")
    return f"\u26a0\ufe0f This kicks off {day_name} at {time_str} — all picks and the bet must be in before then."


def earliest_kickoff_warning(picks_with_kickoff):
    """If any pick has an early kickoff, warn about the effective deadline."""
    if not picks_with_kickoff:
        return None
    tz = pytz.timezone("Europe/Dublin")
    earliest_dt = None
    for pick in picks_with_kickoff:
        ko = pick.get("kickoff")
        if not ko:
            continue
        try:
            dt = datetime.fromisoformat(ko) if isinstance(ko, str) else ko
        except (ValueError, TypeError):
            continue
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        dt_local = dt.astimezone(tz)

        # Check if this kickoff counts as "early" (before Sat 12:30 PM)
        is_early = False
        if dt_local.weekday() == 5:
            cutoff = dt_local.replace(hour=12, minute=30, second=0, microsecond=0)
            is_early = dt_local < cutoff
        elif dt_local.weekday() in (2, 3, 4):
            # Wed/Thu/Fri — always early
            is_early = True

        if is_early and (earliest_dt is None or dt_local < earliest_dt):
            earliest_dt = dt_local

    if earliest_dt is None:
        return None

    day_name = earliest_dt.strftime("%A")
    time_str = earliest_dt.strftime("%-I:%M %p")
    return f"\u26a0\ufe0f Earliest kickoff is {day_name} at {time_str} — all picks must be in before then."


def match_event(event_type, home_team, away_team, home_score, away_score, player_name, minute, detail=None):
    """Format a live match event (goal or red card) for posting."""
    score = f"{home_team} {home_score}-{away_score} {away_team}"
    if event_type == "Goal":
        suffix = ""
        if detail and detail != "Normal Goal":
            suffix = f" ({detail})"
        return f"\u26bd {score} \u2014 {player_name} {minute}'{suffix}"
    elif event_type == "RedCard":
        # Find which team the player is on
        return f"\U0001f7e5 {score} \u2014 {player_name} {minute}' (Red Card)"
    return ""


def match_ended(home_team, away_team, home_score, away_score):
    """Format a full-time score line."""
    return f"FT: {home_team} {home_score}-{away_score} {away_team}"


def help_text():
    """Format the help message."""
    return (
        "At your service. Available commands:\n"
        "!stats — Your personal statistics\n"
        "!stats [player] — Stats for a specific player\n"
        "!picks — Recorded picks for this week\n"
        "!leaderboard — Win rate rankings\n"
        "!rotation — Current rotation and queue\n"
        "!vault — Vault total\n"
        "!help — This message\n"
        "!myphone — Your WhatsApp ID (for .env setup)\n"
        "\n"
        "Admin:\n"
        "!confirm penalty [player] — Confirm a pending penalty\n"
        "!override [player] [win/loss] — Change a result\n"
        "!report [week] — Post the 5-week Punter Report\n"
        "!resetweek — Reset the current week\n"
        "!resetseason — Clear all data for fresh start (next week = Week 1)"
    )


def punter_report_display(period_data):
    """
    Format the end-of-5-week Punter Report.
    Pure template — no LLM.
    """
    from src.services.report_service import (
        compute_leaderboard, compute_acca_record, compute_group_pnl,
        compute_singles_pnl, compute_biggest_winner, compute_awards,
        compute_sole_losers, compute_what_could_have_been,
    )

    start_week = period_data["start_week"]
    end_week = period_data["end_week"]
    player_rows = period_data["player_rows"]
    bet_slips = period_data["bet_slips"]
    penalties = period_data["penalties"]

    lines = [
        f"\U0001f4cb *The Punter Report \u2014 Weeks {start_week}\u2013{end_week}*",
        "",
    ]

    # --- Leaderboard ---
    lb = compute_leaderboard(player_rows, start_week, end_week)
    lines.append("\U0001f4ca *Leaderboard*")
    lines.append("")
    # Standard competition ranking: 1,1,3,4,4,6 — tied players share a rank,
    # next rank skips. Ties sorted by avg_odds DESC (already in lb order).
    prev_win_rate = None
    current_rank = 0
    for i, entry in enumerate(lb):
        if entry["win_rate"] != prev_win_rate:
            current_rank = i + 1
            prev_win_rate = entry["win_rate"]
        avg_str = f"  avg @ {entry['avg_odds']:.1f}" if entry["avg_odds"] else ""
        lines.append(
            f"{current_rank}. {entry['formal_name']}   "
            f"({entry['win_rate']:.0f}%)  {entry['form']}{avg_str}"
        )
    lines.append("")

    # --- Acca record ---
    acca_wins, acca_total = compute_acca_record(bet_slips, player_rows)
    lines.append(f"\U0001f3af *Acca record:* {acca_wins}/{acca_total} weeks")
    lines.append("")

    # --- Group P&L ---
    pnl = compute_group_pnl(bet_slips, player_rows)
    if pnl["staked"] > 0:
        net_sign = "+" if pnl["net"] >= 0 else ""
        lines.append(
            f"\U0001f4b0 *Group P&L:* staked \u20ac{pnl['staked']:.0f} \u00b7 "
            f"returned \u20ac{pnl['returned']:.0f} \u00b7 net {net_sign}\u20ac{pnl['net']:.0f}"
        )
        if pnl.get("cashout_cost", 0) > 0:
            lines.append(
                f"\u26a0\ufe0f  Cashout cost: \u2212\u20ac{pnl['cashout_cost']:.0f}"
                f" (left on the table vs full acca)"
            )
        lines.append("")

    # --- What Could Have Been ---
    what_could = compute_what_could_have_been(player_rows, bet_slips)
    if what_could:
        lines.append("\U0001f494 *What Could Have Been*")
        lines.append("")
        for entry in what_could:
            lines.append(
                f"Week {entry['week_number']} \u2014 so close. {entry['formal_name']}'s pick didn't come in "
                f"\u2014 acca would have paid \u20ac{entry['potential_return']:.0f}."
            )
        lines.append("")

    # --- Singles P&L ---
    singles = compute_singles_pnl(player_rows, bet_slips)
    if singles:
        lines.append("\U0001f4c8 *Singles P&L* (if each pick was a \u20ac20 single)")
        lines.append("")
        sorted_singles = sorted(singles.items(), key=lambda x: -x[1]["pnl"])
        for pid, s in sorted_singles:
            sign = "+" if s["pnl"] >= 0 else ""
            lines.append(f"{s['formal_name']}:  {sign}\u20ac{s['pnl']:.2f}")
        lines.append("")

    # --- Awards ---
    awards = compute_awards(player_rows)
    biggest = compute_biggest_winner(player_rows)
    has_awards = biggest or awards["optimist"] or awards["cold_spell"]
    if has_awards:
        lines.append("\U0001f3c5 *Awards*")
        lines.append("")
        if biggest:
            desc = biggest.get("description") or ""
            desc_part = f" ({_strip_odds_for_display(desc)})" if desc else ""
            lines.append(
                f"\U0001f4aa Biggest priced winner: {biggest['formal_name']}{desc_part}"
                f" @ {_decimal_to_fractional(biggest['odds'])} \u2705"
            )
        if awards["optimist"]:
            opt = awards["optimist"]
            lines.append(f"\U0001f52e Optimist: {opt['formal_name']} \u2014 avg odds {opt['avg_odds']:.1f}")
        if awards["cold_spell"]:
            cs = awards["cold_spell"]
            # Increasingly colder emojis: 🌬️ 🧊 ❄️ 🥶 🌨️ ☃️ 🏔️ 🧊🥶 (cap at last)
            _cold_emojis = [
                "\U0001f32c\ufe0f",  # 1 loss: 🌬️
                "\U0001f9ca",        # 2 losses: 🧊
                "\u2744\ufe0f",      # 3 losses: ❄️
                "\U0001f976",        # 4 losses: 🥶
                "\U0001f328\ufe0f",  # 5 losses: 🌨️
                "\u2603\ufe0f",      # 6 losses: ☃️
                "\U0001f3d4\ufe0f",  # 7+ losses: 🏔️ (snowcapped mountain)
            ]
            cold_emoji = _cold_emojis[min(cs["streak"] - 1, len(_cold_emojis) - 1)]
            lines.append(f"{cold_emoji} Cold spell: {cs['formal_name']} \u2014 {cs['streak']} straight losses")
        lines.append("")

    # --- Penalties ---
    # Group DB penalties and sole-loser events together by player
    by_player = {}
    for pen in penalties:
        ptype = pen.get("type", "")
        if ptype == "sole_loser":
            continue  # displayed via compute_sole_losers below
        pid = pen["player_id"]
        if pid not in by_player:
            by_player[pid] = {"formal_name": pen["formal_name"], "items": []}
        amount = float(pen.get("amount") or 0)
        if amount > 0:
            streak_num = ptype.split("_")[1] if ptype.startswith("streak_") else None
            desc = f"\u20ac{amount:.0f} fine"
            if streak_num:
                desc += f" ({streak_num} consecutive losses)"
            by_player[pid]["items"].append(desc)
        elif ptype == "streak_3":
            by_player[pid]["items"].append("placed following week's bet (3 consecutive losses)")
        elif ptype == "late":
            by_player[pid]["items"].append("placed following week's bet (late pick)")
        else:
            by_player[pid]["items"].append("placed following week's bet")

    for sl in compute_sole_losers(player_rows):
        pid = sl["player_id"]
        if pid not in by_player:
            by_player[pid] = {"formal_name": sl["formal_name"], "items": []}
        by_player[pid]["items"].append(f"only loser on the bet (week {sl['week_number']})")

    if by_player:
        lines.append("\U0001f4b8 *Penalties this period*")
        lines.append("")
        for p in by_player.values():
            desc = " + ".join(p["items"])
            lines.append(f"\U0001f4e3 {p['formal_name']}: {desc}")

    return "\n".join(lines).rstrip()


def _decimal_to_fractional(decimal_odds):
    """Convert decimal odds to fractional string (e.g. 3.5 -> '5/2')."""
    if not decimal_odds or decimal_odds <= 1:
        return str(decimal_odds)
    # Common fractional mappings
    _map = {
        1.5: "1/2", 1.25: "1/4", 1.33: "1/3", 1.4: "2/5",
        2.0: "evens", 2.5: "6/4", 3.0: "2/1", 3.5: "5/2",
        4.0: "3/1", 4.5: "7/2", 5.0: "4/1", 6.0: "5/1",
        7.0: "6/1", 8.0: "7/1", 10.0: "9/1", 11.0: "10/1",
    }
    rounded = round(decimal_odds, 2)
    if rounded in _map:
        return _map[rounded]
    # Generic: decimal - 1 as fraction
    from fractions import Fraction
    frac = Fraction(decimal_odds - 1).limit_denominator(20)
    return f"{frac.numerator}/{frac.denominator}"


def _join_names(names):
    """Join names with commas and 'and'."""
    if len(names) == 0:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]
