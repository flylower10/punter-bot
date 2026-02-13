import logging

import requests
from flask import Flask, jsonify, request

from src.config import Config
from src.db import init_db, get_db
from src.parsers.message_parser import parse_message, parse_cumulative_picks
from src.services.player_service import (
    lookup_player, is_admin, is_superadmin, get_emoji_to_player_map,
)
from src.services.week_service import (
    get_or_create_current_week, get_current_week, is_within_submission_window,
    is_past_deadline, complete_week,
)
from src.services.pick_service import (
    submit_pick, get_missing_players, all_picks_in, get_player_pick, get_picks_for_week,
)
from src.services.result_service import (
    record_result, get_consecutive_losses, all_results_in as all_results_complete,
    get_week_results, override_result,
)
from src.services.penalty_service import (
    suggest_penalty, confirm_penalty, get_pending_penalties,
    get_pending_penalty_for_player, get_vault_total,
)
from src.services.rotation_service import get_next_placer, add_to_penalty_queue, get_rotation_display
from src.services.stats_service import get_player_stats, get_leaderboard
import src.butler as butler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.before_request
def log_request():
    if request.path != "/health":
        logger.info("%s %s", request.method, request.path)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive messages from the Node.js WhatsApp bridge."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "no data"}), 400

    sender = data.get("sender", "")
    sender_phone = data.get("sender_phone", "")
    body = data.get("body", "")
    group_id = data.get("group_id", "")
    has_media = data.get("has_media", False)

    # Only process messages from our group
    if Config.GROUP_CHAT_ID and group_id != Config.GROUP_CHAT_ID:
        return jsonify({"action": "ignored", "reason": "wrong group"})

    logger.info("Message from %s: %s", sender, body[:100])

    reply = None

    # Commands always use single-message parsing
    if body.strip().startswith("!"):
        parsed = parse_message(body, sender, sender_phone)
        if parsed["type"] == "command":
            reply = handle_command(parsed)
        elif parsed["type"] == "result":
            reply = handle_result(parsed)
        elif parsed["type"] == "pick":
            reply = handle_pick(parsed)
    else:
        # Try cumulative format first (emoji + pick per line)
        emoji_map = get_emoji_to_player_map()
        cumulative = parse_cumulative_picks(body, emoji_map)

        if len(cumulative) >= 1:
            reply = handle_cumulative_picks(cumulative)
        else:
            # Fall back to single-message parsing
            parsed = parse_message(body, sender, sender_phone)
            logger.info("Parsed as: %s (sender: %s)", parsed["type"], parsed["sender"])
            if parsed["type"] == "command":
                reply = handle_command(parsed)
            elif parsed["type"] == "pick":
                reply = handle_pick(parsed)
            elif parsed["type"] == "result":
                reply = handle_result(parsed)

    if reply:
        send_message(group_id, reply)
        return jsonify({"action": "replied", "reply": reply})

    return jsonify({"action": "no_reply"})


def handle_command(parsed):
    """Route commands to the appropriate handler."""
    command = parsed["parsed_data"].get("command", "")
    args = parsed["parsed_data"].get("args", [])

    if command == "help":
        return butler.help_text()

    if command == "stats":
        return _cmd_stats(parsed, args)

    if command == "picks":
        return _cmd_picks()

    if command == "leaderboard":
        return _cmd_leaderboard()

    if command == "rotation":
        return _cmd_rotation()

    if command == "vault":
        return butler.vault_display(get_vault_total())

    if command == "confirm":
        return _cmd_confirm(parsed, args)

    if command == "override":
        return _cmd_override(parsed, args)

    if command == "resetweek":
        return _cmd_resetweek(parsed)

    if command == "status":
        return _cmd_status(parsed)

    return f"My apologies, I don't recognise the command !{command}. Try !help."


def _cmd_stats(parsed, args):
    """!stats or !stats [player]"""
    if args:
        # Stats for a specific player
        target = lookup_player(sender_name=args[0])
        if not target:
            return f"I'm afraid I don't recognise the player '{args[0]}'."
    else:
        # Stats for the sender
        target = lookup_player(
            sender_phone=parsed.get("sender_phone", ""),
            sender_name=parsed["sender"],
        )
        if not target:
            return _cmd_leaderboard()

    stats = get_player_stats(target["id"])
    if stats["total"] == 0:
        return f"{target['formal_name']} has no recorded results yet."
    return butler.stats_display(target, stats)


def _cmd_picks():
    """!picks — Show recorded picks for the current week."""
    week = get_current_week()
    if not week:
        return "No active week."
    picks = get_picks_for_week(week["id"])
    return butler.picks_display(picks, week["week_number"])


def _cmd_leaderboard():
    """!leaderboard"""
    entries = get_leaderboard()
    if not entries:
        return "No results have been recorded yet."
    return butler.leaderboard_display(entries)


def _cmd_rotation():
    """!rotation"""
    data = get_rotation_display()
    if not data["next_placer"]:
        return "No players found in the rotation."
    return butler.rotation_display(
        data["next_placer"],
        data["queue"],
        data["last_placer"],
        data["last_week_number"],
    )


def _cmd_confirm(parsed, args):
    """!confirm penalty [player] — Ed only."""
    if not _is_authorized_admin(parsed):
        return "Only Mr Edmund may confirm penalties."

    if not args or args[0].lower() != "penalty":
        return "Usage: !confirm penalty [player]"

    if len(args) < 2:
        # Show pending penalties
        pending = get_pending_penalties()
        if not pending:
            return "No penalties awaiting confirmation."
        lines = ["Pending penalties:"]
        for p in pending:
            lines.append(f"- {p['formal_name']}: {p['type']} — !confirm penalty {p['nickname']}")
        return "\n".join(lines)

    # Confirm a specific player's penalty
    nickname = args[1]
    penalty = get_pending_penalty_for_player(nickname)
    if not penalty:
        return f"No pending penalty found for '{nickname}'."

    result = confirm_penalty(penalty["id"], confirmed_by=parsed["sender"])
    if not result:
        return "Penalty could not be confirmed."

    confirmed, vault_total = result
    player = lookup_player(sender_name=nickname)
    if not player:
        player = {"formal_name": nickname}

    # If it's a streak_3 penalty, add to rotation queue
    if confirmed["type"] == "streak_3":
        add_to_penalty_queue(confirmed["player_id"], "3 consecutive losses", confirmed["week_id"])

    return butler.penalty_confirmed(player, confirmed["amount"], vault_total)


def _cmd_override(parsed, args):
    """!override [player] [win/loss] — Ed only."""
    if not _is_authorized_admin(parsed):
        return "Only Mr Edmund may override results."

    if len(args) < 2:
        return "Usage: !override [player] [win/loss]"

    nickname = args[0]
    outcome = args[1].lower()
    if outcome not in ("win", "loss", "void"):
        return "Outcome must be win, loss, or void."

    target = lookup_player(sender_name=nickname)
    if not target:
        return f"I'm afraid I don't recognise the player '{nickname}'."

    week = get_current_week()
    if not week:
        return "No active week found."

    result = override_result(target["id"], week["id"], outcome, confirmed_by=parsed["sender"])
    if not result:
        return f"{target['formal_name']} has no pick recorded for this week."

    return f"Result overridden. {target['formal_name']}: {outcome}."


def _cmd_resetweek(parsed):
    """!resetweek — Ed only, emergency reset."""
    if not _is_authorized_admin(parsed):
        return "Only Mr Edmund may reset the week."

    week = get_current_week()
    if not week:
        return "No active week to reset."

    conn = get_db()
    # Delete results for this week's picks
    conn.execute(
        "DELETE FROM results WHERE pick_id IN (SELECT id FROM picks WHERE week_id = ?)",
        (week["id"],),
    )
    # Delete picks for this week
    conn.execute("DELETE FROM picks WHERE week_id = ?", (week["id"],))
    # Delete penalties for this week
    conn.execute("DELETE FROM penalties WHERE week_id = ?", (week["id"],))
    # Reset week status to open
    conn.execute("UPDATE weeks SET status = 'open' WHERE id = ?", (week["id"],))
    conn.commit()
    conn.close()

    return f"Week {week['week_number']} has been reset. All picks and results cleared."


def _cmd_status(parsed):
    """!status — Superadmin only, system health check."""
    if not _is_authorized_superadmin(parsed):
        return "This command is restricted."

    week = get_current_week()
    week_info = f"Week {week['week_number']} ({week['status']})" if week else "No active week"
    picks_count = len(get_picks_for_week(week["id"])) if week else 0
    pending = get_pending_penalties()

    return (
        f"System Status\n"
        f"Week: {week_info}\n"
        f"Picks submitted: {picks_count}\n"
        f"Pending penalties: {len(pending)}\n"
        f"Vault: \u20ac{get_vault_total():.0f}"
    )


def _is_authorized_admin(parsed):
    """Check if sender is admin (Ed)."""
    if Config.TEST_MODE:
        return parsed["sender"].lower() in ("ed", "edmund")
    return is_admin(parsed.get("sender_phone", ""))


def _is_authorized_superadmin(parsed):
    """Check if sender is superadmin."""
    if Config.TEST_MODE:
        return True  # Allow in test mode
    return is_superadmin(parsed.get("sender_phone", ""))


def handle_cumulative_picks(cumulative):
    """
    Process multiple picks from a cumulative message (emoji + pick per line).
    Returns combined reply for all successfully submitted picks.
    """
    if not is_within_submission_window():
        logger.info("Cumulative picks ignored — outside submission window")
        return None

    week = get_or_create_current_week()
    replies = []

    for player, data in cumulative:
        pick, is_update = submit_pick(
            player_id=player["id"],
            week_id=week["id"],
            description=data["description"],
            odds_decimal=data["odds_decimal"],
            odds_original=data["odds_original"],
            bet_type=data["bet_type"],
        )
        # Only acknowledge new picks — skip re-submissions already in the thread
        if not is_update:
            replies.append(
                butler.pick_confirmed(
                    player, data["description"], data["odds_original"], is_update
                )
            )

    # Add status for missing players
    missing = get_missing_players(week["id"])
    if missing:
        replies.append(butler.picks_status(None, missing))
    elif all_picks_in(week["id"]):
        placer = get_next_placer()
        if placer:
            replies.append(butler.all_picks_in(placer))
        else:
            replies.append("All selections have been received.")

    return "\n".join(replies)


def handle_pick(parsed):
    """Process a pick submission."""
    # Only accept picks during the submission window
    if not is_within_submission_window():
        logger.info("Pick ignored — outside submission window")
        return None

    # Look up the player
    player = lookup_player(
        sender_phone=parsed.get("sender_phone", ""),
        sender_name=parsed["sender"],
    )
    if not player:
        logger.info("Pick ignored — unknown player: %s", parsed["sender"])
        return None

    # Get or create the current week
    week = get_or_create_current_week()

    data = parsed["parsed_data"]
    pick, is_update = submit_pick(
        player_id=player["id"],
        week_id=week["id"],
        description=data["description"],
        odds_decimal=data["odds_decimal"],
        odds_original=data["odds_original"],
        bet_type=data["bet_type"],
    )

    # Build confirmation reply
    reply = butler.pick_confirmed(
        player, data["description"], data["odds_original"], is_update
    )

    # Check who's still missing
    missing = get_missing_players(week["id"])
    if missing:
        reply += "\n" + butler.picks_status(None, missing)
    elif all_picks_in(week["id"]):
        # All picks are in — announce the placer
        placer = get_next_placer()
        if placer:
            reply += "\n" + butler.all_picks_in(placer)
        else:
            reply += "\nAll selections have been received."

    return reply


def handle_result(parsed):
    """Process a result message. Only accepted from Ed (admin)."""
    sender_phone = parsed.get("sender_phone", "")

    # In test mode, check if the sender name is Ed
    if Config.TEST_MODE:
        if parsed["sender"].lower() not in ("ed", "edmund"):
            logger.info("Result ignored — not from Ed (test mode, sender: %s)", parsed["sender"])
            return None
    else:
        if not is_admin(sender_phone):
            logger.info("Result ignored — not from admin")
            return None

    data = parsed["parsed_data"]

    # Look up the player whose result is being reported
    target_player = lookup_player(sender_name=data["player_nickname"])
    if not target_player:
        logger.info("Result ignored — unknown player: %s", data["player_nickname"])
        return None

    # Get the current week
    week = get_current_week()
    if not week:
        return "My apologies, but there is no active week to record results against."

    # Get the player's pick for this week
    pick = get_player_pick(week["id"], target_player["id"])
    if not pick:
        return f"I beg your pardon, but {target_player['formal_name']} has no pick recorded for this week."

    # Record the result
    result = record_result(pick["id"], data["outcome"], confirmed_by=parsed["sender"])

    # Build announcement
    reply = butler.result_announced(
        target_player, pick["description"], pick["odds_original"], data["outcome"]
    )

    # Check for streak penalties
    streak = get_consecutive_losses(target_player["id"])
    penalty_thresholds = {3: "streak_3", 5: "streak_5", 7: "streak_7", 10: "streak_10"}
    penalty_amounts = {3: 0, 5: 50, 7: 100, 10: 200}

    if streak in penalty_thresholds:
        suggest_penalty(target_player["id"], week["id"], penalty_thresholds[streak])
        reply += "\n\n" + butler.penalty_suggested(
            target_player, streak, penalty_thresholds[streak], penalty_amounts[streak]
        )

    # Check if all results are in
    if all_results_complete(week["id"]):
        results = get_week_results(week["id"])
        reply += "\n\n" + butler.weekend_summary(results, week["week_number"])
        complete_week(week["id"])

    return reply


def send_message(chat_id, text):
    """Send a message back through the Node.js bridge."""
    try:
        requests.post(
            f"{Config.BRIDGE_URL}/send",
            json={"chat_id": chat_id, "message": text},
            timeout=10,
        )
    except requests.RequestException as e:
        logger.error("Failed to send message via bridge: %s", e)


def create_app():
    """Initialize the database and return the Flask app."""
    init_db()
    logger.info("Database initialized")

    from src.services.scheduler import init_scheduler
    init_scheduler(send_message)
    logger.info("Scheduler initialized")

    return app


if __name__ == "__main__":
    create_app()
    app.run(host="0.0.0.0", port=Config.FLASK_PORT, debug=True)
