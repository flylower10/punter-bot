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
    text = re.sub(r"\b\d+/\d+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+\.\d{1,2}\b", "", text)
    text = re.sub(r"\bevens?\b", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip().rstrip(".,")


def pick_confirmed(player, description, odds, is_update=False, placer=None, previous_description=None, first_of_week=False):
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

    scenario = "pick_confirmed_first" if first_of_week and not is_update else "pick_confirmed"
    context = f"{player['formal_name']}'s pick recorded: {_strip_odds_for_display(formal)} @ {odds}."
    return _frame(template, context, scenario=scenario, player_name=_first_name(player))


def picks_status(submitted, missing):
    """Show who has and hasn't submitted picks."""
    if not missing:
        return ""
    missing_lines = "\n".join(_emoji_name(p) for p in missing)
    return f"Awaiting selection from:\n{missing_lines}"


def all_picks_in(placer, picks=None):
    """Announce all picks are in, who places the bet, and list all selections."""
    header = (
        f"All selections have been received.  "
        f"{placer['formal_name']}, you are next in the rotation to place the wager."
    )
    if not picks:
        return header
    lines = []
    for pick in picks:
        emoji = _primary_emoji(pick.get("emoji", ""))
        prefix = f"{emoji} " if emoji else ""
        formal = _formalize_pick(pick.get("description", ""))
        display = _strip_odds_for_display(formal)
        odds = pick.get("odds_original", "")
        lines.append(f"{prefix}{pick['formal_name']} — {display} @ {odds}")
    return header + "\n\n" + "\n".join(lines)


def bet_slip_received(player):
    """Confirm bet slip screenshot received from the placer."""
    return f"Thank you, {player['formal_name']}.  Bet slip received and recorded."


def result_announced(player, description, odds, outcome, streak=None):
    """Announce a result."""
    formal = _formalize_pick(description)
    display_text = _strip_odds_for_display(formal) if odds != "placer" else formal

    if outcome == "win":
        verdict = "\u2705 Winner."
        prefix = "I'm pleased to report"
        scenario = "result_win"
    elif outcome == "loss":
        verdict = "\u274c Lost."
        prefix = "I'm afraid"
        if streak and streak.endswith("L"):
            streak_num = int(streak[:-1])
            scenario = f"result_streak_{streak_num}" if streak_num in (3, 5, 7) else "result_loss"
        else:
            scenario = "result_loss"
    else:
        verdict = "Void."
        prefix = "I must inform you"
        scenario = "result_loss"

    template = (
        f"{prefix} \u2014 {player['formal_name']}'s selection: "
        f"{display_text} @ {odds}.  {verdict}"
    )

    streak_ctx = f" ({streak} streak)" if streak else ""
    context = f"{player['formal_name']}'s pick {outcome}: {display_text} @ {odds}.{streak_ctx}"
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
    template = (
        "Good evening, gentlemen.  May I remind you that picks are due "
        "by 10 PM Friday."
    )
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
    """Format current week's picks for display. Shows result (✅/❌) when available."""
    if not picks:
        return "No picks recorded for this week yet."
    lines = ["\U0001f4dc RECORDED PICKS", "\u2501" * 22]
    if week_number:
        lines.append(f"Week {week_number}")
        lines.append("")
    pick_summaries = []
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
        pick_summaries.append(f"{p['formal_name']}: {display_text} @ {odds}")

    body = "\n".join(lines)

    kicker = _picks_kicker(pick_summaries)
    if kicker:
        body += f"\n\n{kicker}"

    return body


def _picks_kicker(pick_summaries):
    """Generate a short one-liner comment on the week's picks. Reserved for shadow/LLM testing."""
    return None


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
