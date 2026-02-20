"""
The Betting Butler — message formatting module.

All bot responses are formatted through this module. When LLM is enabled,
responses are generated dynamically via Groq; otherwise falls back to templates.
"""

import logging
import re

from src import llm_client

logger = logging.getLogger(__name__)

# Abbreviations to formal names for pick display (case-insensitive)
PICK_ABBREVIATIONS = {
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
}


def _formalize_pick(description):
    """Convert abbreviated pick text to formal display format."""
    if not description or not isinstance(description, str):
        return description
    text = description.strip()
    # Expand abbreviations (longest first to avoid partial matches)
    for abbr, full in sorted(PICK_ABBREVIATIONS.items(), key=lambda x: -len(x[0])):
        text = re.sub(re.escape(abbr), full, text, flags=re.IGNORECASE)
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
    text = re.sub(r"\b\d+/\d+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+\.\d{1,2}\b", "", text)
    text = re.sub(r"\bevens?\b", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip().rstrip(".,")


def pick_confirmed(player, description, odds, is_update=False, placer=None, previous_description=None):
    """Confirm a pick has been recorded."""
    formal = _formalize_pick(description)
    display_text = _strip_odds_for_display(formal) if odds != "placer" else formal
    odds_display = odds if odds != "placer" else "(placer to confirm)"

    context = (
        f"{'Updated' if is_update else 'New'} pick recorded for {player['formal_name']}: "
        f"{display_text} @ {odds_display}."
    )
    if is_update and previous_description:
        prev = _strip_odds_for_display(_formalize_pick(previous_description))
        context += f" Replacing previous pick: {prev}."

    enhanced = llm_client.generate(context, player_name=_first_name(player))
    if enhanced:
        return enhanced

    # Template fallback
    action = "Updated" if is_update else "Noted and recorded"
    if odds == "placer":
        placer_name = placer["formal_name"] if placer else "Placer"
        body = f"{formal} — {placer_name} to confirm odds when placing the bet."
    else:
        body = f"{_strip_odds_for_display(formal)} @ {odds}."
    if is_update and previous_description:
        previous_display = _strip_odds_for_display(_formalize_pick(previous_description))
        return f"{action}, {player['formal_name']}.  Replacing {previous_display} with {body}"
    return f"{action}, {player['formal_name']}.  {body}"


def picks_status(submitted, missing):
    """Show who has and hasn't submitted picks."""
    if not missing:
        return ""
    missing_names = [p["formal_name"] for p in missing]
    return f"Awaiting selection from {_join_names(missing_names)}."


def all_picks_in(placer):
    """Announce all picks are in and who places the bet."""
    return (
        f"All selections have been received.  "
        f"{placer['formal_name']}, you are next in the rotation to place the wager."
    )


def bet_slip_received(player):
    """Confirm bet slip screenshot received from the placer."""
    return f"Thank you, {player['formal_name']}.  Bet slip received and recorded."


def result_announced(player, description, odds, outcome, streak=None):
    """Announce a result."""
    formal = _formalize_pick(description)
    display_text = _strip_odds_for_display(formal) if odds != "placer" else formal

    scenario = "win" if outcome == "win" else "loss" if outcome == "loss" else None
    if streak and outcome == "loss":
        streak_num = int(streak.rstrip("L")) if streak.endswith("L") else 0
        if streak_num >= 7:
            scenario = "losing_streak_7"
        elif streak_num >= 5:
            scenario = "losing_streak_5"
        elif streak_num >= 3:
            scenario = "losing_streak_3"

    context = (
        f"Result for {player['formal_name']}: {display_text} @ {odds}. "
        f"Outcome: {outcome}."
    )
    if streak:
        context += f" Current streak: {streak}."

    enhanced = llm_client.generate(context, scenario=scenario, player_name=_first_name(player))
    if enhanced:
        return enhanced

    # Template fallback
    if outcome == "win":
        verdict = "\u2705 Winner."
        prefix = "I'm pleased to report"
    elif outcome == "loss":
        verdict = "\u274c Lost."
        prefix = "I'm afraid"
    else:
        verdict = "Void."
        prefix = "I must inform you"

    return (
        f"{prefix} \u2014 {player['formal_name']}'s selection: "
        f"{display_text} @ {odds}.  {verdict}"
    )


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

    context = (
        f"Week {week_number} is complete. "
        f"Winners: {', '.join(winner_names) if winner_names else 'none'}. "
        f"Losers: {', '.join(loser_names) if loser_names else 'none'}. "
        f"Accumulator: {'Won' if won_count == total else 'Lost'} ({won_count} of {total})."
    )
    if rotation_next and rotation_next.get("formal_name"):
        context += f" Next to place: {rotation_next['formal_name']}."

    enhanced = llm_client.generate(context, scenario="week_summary")
    if enhanced:
        # LLM handles the narrative; still append the structured leaderboard
        lb_section = _format_leaderboard_section(leaderboard, rotation_next)
        if lb_section:
            return enhanced + "\n\n" + lb_section
        return enhanced

    # Template fallback
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
    context = (
        "It's Thursday evening. Remind all players that picks are due by 10 PM Friday."
    )
    enhanced = llm_client.generate(context, scenario="reminder")
    if enhanced:
        return enhanced

    return (
        "Good evening, gentlemen.  May I remind you that picks are due "
        "by 10 PM Friday."
    )


def reminder_friday(missing):
    """Friday 5PM reminder to missing players."""
    names = [p["formal_name"] for p in missing]
    context = (
        f"It's Friday 5PM. Still waiting on picks from: {_join_names(names)}. "
        f"5 hours until the deadline. This is the second reminder -- be more impatient."
    )
    enhanced = llm_client.generate(context, scenario="reminder")
    if enhanced:
        return enhanced

    return (
        f"Pardon the interruption.  {_join_names(names)} \u2014 "
        f"5 hours remain to submit your selections."
    )


def reminder_final(missing):
    """Friday 9:30PM final warning."""
    names = [p["formal_name"] for p in missing]
    context = (
        f"FINAL WARNING. 30 minutes until deadline. Still missing picks from: {_join_names(names)}. "
        f"This is the last reminder -- be borderline threatening."
    )
    enhanced = llm_client.generate(context, scenario="reminder")
    if enhanced:
        return enhanced

    return (
        f"I do hope you'll forgive the urgency.  {_join_names(names)} \u2014 "
        f"30 minutes remain.  This is the final reminder."
    )


def rotation_display(next_placer, queue, last_placer=None, last_week=None):
    """Format the rotation queue for display."""
    lines = [
        "\U0001f504 ROTATION STATUS",
        "\u2501" * 22,
    ]

    if last_placer and last_week:
        lines.append(f"Last Placed: {last_placer['formal_name']} (Week {last_week})")

    lines.append(f"Next Up: {next_placer['formal_name']} \U0001f448")
    lines.append("")
    lines.append("Queue:")

    for i, entry in enumerate(queue, 1):
        suffix = f" (penalty \u2014 {entry['reason']})" if entry.get("reason") else ""
        lines.append(f"{i}. {entry['formal_name']}{suffix}")

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
    """Format current week's picks for display. Shows result (✅/❌) when available."""
    if not picks:
        return "No picks recorded for this week yet."
    lines = ["\U0001f4dc RECORDED PICKS", "\u2501" * 22]
    if week_number:
        lines.append(f"Week {week_number}")
        lines.append("")
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


def _primary_emoji(emoji_str):
    """Get the primary emoji from a comma-separated emoji string."""
    if not emoji_str:
        return ""
    return emoji_str.split(",")[0].strip()


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
        "!resetweek — Reset the current week\n"
        "!resetseason — Clear all data for fresh start (next week = Week 1)"
    )


def _join_names(names):
    """Join names with commas and 'and'."""
    if len(names) == 0:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]
