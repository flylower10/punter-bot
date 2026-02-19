import logging
import os
import re

import requests
from flask import Flask, jsonify, request

from src.config import Config
from src.db import init_db, get_db
from src.parsers.message_parser import parse_message, parse_cumulative_picks
from src.services.player_service import (
    lookup_player, is_admin, is_superadmin, get_emoji_to_player_map,
)
from src.services.week_service import (
    get_or_create_current_week, get_current_week, get_week_for_reset,
    is_within_submission_window, is_past_deadline, complete_week,
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
from src.services.rotation_service import get_next_placer, add_to_penalty_queue, get_rotation_display, advance_rotation
from src.services.stats_service import get_player_stats, get_leaderboard
import src.butler as butler
from src import llm_client

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

    # Only process messages from our group(s)
    allowed = Config.GROUP_CHAT_IDS if Config.GROUP_CHAT_IDS else ([Config.GROUP_CHAT_ID] if Config.GROUP_CHAT_ID else [])
    if allowed and group_id not in allowed:
        logger.info("Ignored: wrong group (expected one of %s, got %s)", allowed, group_id)
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

    # Screenshot or confirmation text from next placer = bet placed (all picks in)
    if not reply and (has_media or _looks_like_bet_placed(body)):
        reply = _handle_placer_bet_confirmation(sender, sender_phone, body)

    # Banter: if no structured reply, try LLM banter (mention or random chance)
    if not reply and body.strip() and Config.LLM_ENABLED:
        reply = _try_banter(body, sender, sender_phone)

    if reply:
        send_message(group_id, reply)

        # Shadow mode: also send LLM-enhanced version to the shadow group
        if Config.SHADOW_GROUP_ID:
            _shadow_message(sender, body, reply, group_id)

        return jsonify({"action": "replied", "reply": reply})

    # No structured reply — still try shadow banter on general chat
    if Config.SHADOW_GROUP_ID and body.strip():
        _shadow_banter(sender, sender_phone, body)

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

    if command == "resetseason":
        return _cmd_resetseason(parsed)

    if command == "status":
        return _cmd_status(parsed)

    if command == "myphone":
        return _cmd_myphone(parsed)

    if command == "ping":
        return "pong"

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
        return f"I have no recorded results for {target['formal_name']} as yet. Once the first week's results are in, statistics will be available."
    return butler.stats_display(target, stats)


def _cmd_picks():
    """!picks — Show recorded picks for the current week."""
    week = get_current_week()
    if not week:
        return "I have no active week at present. The season will commence when picks are collected, Thursday through Friday."
    picks = get_picks_for_week(week["id"])
    return butler.picks_display(picks, week["week_number"])


def _cmd_leaderboard():
    """!leaderboard"""
    entries = get_leaderboard()
    if not entries:
        return "I beg your pardon — no results have been recorded as yet. The leaderboard will appear once the first week's results are in."
    return butler.leaderboard_display(entries)


def _cmd_rotation():
    """!rotation"""
    data = get_rotation_display()
    if not data["next_placer"]:
        return "The rotation has not yet been established. Once the first week is complete, I shall display who is next to place."
    return butler.rotation_display(
        data["next_placer"],
        data["queue"],
        data["last_placer"],
        data["last_week_number"],
    )


def _cmd_confirm(parsed, args):
    """!confirm penalty [player] — Ed only."""
    if not _is_authorized_admin(parsed):
        return "Only an admin may confirm penalties."

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
        return "Only an admin may override results."

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


def _looks_like_bet_placed(text):
    """Check if message text suggests the placer has placed the bet."""
    if not text or not text.strip():
        return False
    t = text.strip().lower()
    keywords = ("placed", "bet slip", "bet placed", "slip", "done", "sorted", "here's the bet")
    return any(kw in t for kw in keywords)


def _handle_placer_bet_confirmation(sender, sender_phone, body=""):
    """
    When all picks are in, if the next placer posts a screenshot or confirmation text,
    record the bet as placed. Admin can also forward the placer's screenshot — we record
    the next placer. Will be enhanced with OCR when screenshot recognition is implemented.
    """
    from src.parsers.message_parser import extract_test_prefix

    if Config.TEST_MODE and body:
        override, _ = extract_test_prefix(body)
        if override:
            sender = override

    week = get_current_week()
    if not week:
        return None

    if not all_picks_in(week["id"]):
        return None

    next_placer = get_next_placer()
    if not next_placer:
        return None

    player = lookup_player(sender_phone=sender_phone, sender_name=sender)
    is_placer = player and next_placer["id"] == player["id"]
    is_admin = _is_authorized_admin({"sender": sender, "sender_phone": sender_phone})

    if not (is_placer or is_admin):
        return None

    advance_rotation(week["id"], next_placer["id"])
    return butler.bet_slip_received(next_placer)


def _cmd_resetweek(parsed):
    """!resetweek — Ed only, emergency reset. Also resets most recent completed week for re-testing."""
    if not _is_authorized_admin(parsed):
        return "Only an admin may reset the week."

    week = get_week_for_reset()
    if not week:
        return "No week to reset. (No open/closed week, and no completed week this season.)"

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
    # Reset week status and placer
    conn.execute(
        "UPDATE weeks SET status = 'open', placer_id = NULL WHERE id = ?",
        (week["id"],),
    )
    conn.commit()
    conn.close()

    return f"Week {week['week_number']} has been reset. All picks and results cleared."


def _cmd_resetseason(parsed):
    """!resetseason — Admin only. Clear all weeks and related data so next week = Week 1."""
    if not _is_authorized_admin(parsed):
        return "Only an admin may reset the season."

    conn = get_db()
    conn.execute("DELETE FROM vault")
    conn.execute("DELETE FROM penalties")
    conn.execute("DELETE FROM results")
    conn.execute("DELETE FROM picks")
    conn.execute("DELETE FROM bet_slips")
    conn.execute("DELETE FROM rotation_queue")
    conn.execute("DELETE FROM weeks")
    conn.commit()
    conn.close()

    return "The season has been reset. All weeks, picks, results, and penalties have been cleared. Players remain. The next week created will be Week 1."


def _cmd_myphone(parsed):
    """!myphone — Show your WhatsApp phone ID and auto-add to .env as SUPERADMIN_PHONE."""
    from pathlib import Path

    phone = parsed.get("sender_phone", "")
    if not phone:
        return "I couldn't determine your phone ID. Try sending from the group (not a forwarded message)."

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        content = env_path.read_text()
        if "SUPERADMIN_PHONE=" in content:
            import re
            content = re.sub(r"SUPERADMIN_PHONE=.*", f"SUPERADMIN_PHONE={phone}", content)
        else:
            content = content.rstrip() + f"\nSUPERADMIN_PHONE={phone}\n"
        env_path.write_text(content)
        return (
            f"Your WhatsApp ID: {phone}\n"
            f"Added to .env as SUPERADMIN_PHONE.  Restart the bot to apply."
        )
    return (
        f"Your WhatsApp ID: {phone}\n"
        f"Add to .env: SUPERADMIN_PHONE={phone}"
    )


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
    """Check if sender is admin (Ed, you, or others in config)."""
    if Config.TEST_MODE:
        return parsed.get("sender", "").lower() in Config.ADMIN_NICKNAMES
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
    When a player appears multiple times, only the LAST occurrence is used (so a
    replacement pick at the end of the thread wins over an earlier line).
    """
    if not Config.TEST_MODE and not is_within_submission_window():
        logger.info("Cumulative picks ignored — outside submission window")
        return None

    # Deduplicate by player: keep last occurrence (replacement pick wins)
    by_player = {}
    for player, data in cumulative:
        by_player[player["id"]] = (player, data)
    cumulative = list(by_player.values())

    week = get_or_create_current_week()
    replies = []

    for player, data in cumulative:
        pick, is_update, changed, previous_description = submit_pick(
            player_id=player["id"],
            week_id=week["id"],
            description=data["description"],
            odds_decimal=data["odds_decimal"],
            odds_original=data["odds_original"],
            bet_type=data["bet_type"],
        )
        # Only confirm new picks or updates where something actually changed
        if changed:
            placer = get_next_placer() if data["odds_original"] == "placer" else None
            replies.append(
                butler.pick_confirmed(
                    player, data["description"], data["odds_original"], is_update,
                    placer=placer, previous_description=previous_description
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
    # Only accept picks during the submission window (bypass in test mode)
    if not Config.TEST_MODE and not is_within_submission_window():
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
    pick, is_update, _, previous_description = submit_pick(
        player_id=player["id"],
        week_id=week["id"],
        description=data["description"],
        odds_decimal=data["odds_decimal"],
        odds_original=data["odds_original"],
        bet_type=data["bet_type"],
    )

    # Build confirmation reply (single-pick always confirms)
    placer = get_next_placer() if data["odds_original"] == "placer" else None
    reply = butler.pick_confirmed(
        player, data["description"], data["odds_original"], is_update,
        placer=placer, previous_description=previous_description
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

    # In test mode, check if the sender name is in ADMIN_NICKNAMES
    if Config.TEST_MODE:
        if parsed["sender"].lower() not in Config.ADMIN_NICKNAMES:
            logger.info("Result ignored — not from admin (test mode, sender: %s)", parsed["sender"])
            return f"I'm afraid only admins may record results. (Your name '{parsed['sender']}' isn't in ADMIN_NICKNAMES.)"
    else:
        if not is_admin(sender_phone):
            logger.info("Result ignored — not from admin")
            return "I'm afraid only admins may record results."

    data = parsed["parsed_data"]

    # Look up the player whose result is being reported
    target_player = lookup_player(sender_name=data["player_nickname"])
    if not target_player:
        logger.info("Result ignored — unknown player: %s", data["player_nickname"])
        return f"I don't recognise that player: {data['player_nickname']}."

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

    # Get streak info for both announcement and penalty check
    streak = get_consecutive_losses(target_player["id"])
    streak_str = f"{streak}L" if streak > 0 and data["outcome"] == "loss" else None

    # Build announcement
    reply = butler.result_announced(
        target_player, pick["description"], pick["odds_original"], data["outcome"],
        streak=streak_str,
    )
    penalty_thresholds = {3: "streak_3", 5: "streak_5", 7: "streak_7", 10: "streak_10"}
    penalty_amounts = {3: 0, 5: 50, 7: 100, 10: 200}

    if streak in penalty_thresholds:
        suggest_penalty(target_player["id"], week["id"], penalty_thresholds[streak])
        reply += "\n\n" + butler.penalty_suggested(
            target_player, streak, penalty_thresholds[streak], penalty_amounts[streak]
        )

    # Check if all results are in — publish combined week summary (no separate Monday recap)
    if all_results_complete(week["id"]):
        results = get_week_results(week["id"])
        complete_week(week["id"])  # Complete first so get_next_placer sees this week
        leaderboard = get_leaderboard()
        next_placer = get_next_placer()
        reply += "\n\n" + butler.week_complete_summary(
            results, week["week_number"], leaderboard or [], next_placer or {}
        )

    return reply


_BANTER_TRIGGERS = re.compile(
    r"\b(butler|bot|betting butler)\b", re.IGNORECASE
)


def _try_banter(body, sender, sender_phone):
    """
    Attempt a banter response to general chat.
    Always responds when the bot is mentioned; otherwise defers to the
    random banter_rate in the personality config.
    """
    mentioned = bool(_BANTER_TRIGGERS.search(body))

    player = lookup_player(sender_phone=sender_phone, sender_name=sender)
    player_name = _first_name_from_player(player) if player else sender

    if mentioned:
        context = (
            f'{sender} said (addressing you directly): "{body}"\n\n'
            f"Respond in character. Keep it to 1-2 sentences."
        )
        response = llm_client.generate(context, player_name=player_name)
        if response:
            return response

    return llm_client.generate_banter(body, sender, player_name=player_name)


def _first_name_from_player(player):
    """Extract first name from player dict for LLM profile lookup."""
    if not player:
        return None
    formal = player.get("formal_name", "")
    return formal.replace("Mr ", "").strip() if formal.startswith("Mr ") else formal


def _shadow_message(sender, body, template_reply, source_group_id):
    """
    Send an LLM-enhanced version of a bot reply to the shadow group.
    Shows what the sender said, the template reply, and the LLM version.
    """
    try:
        # Temporarily force LLM on for the shadow call
        original_enabled = Config.LLM_ENABLED
        Config.LLM_ENABLED = True

        # Re-derive the LLM context from the template reply
        context = (
            f"The bot just sent this template response to the group:\n"
            f'"{template_reply}"\n\n'
            f"Rewrite this response in your character's voice. Keep the same factual "
            f"information but make it entertaining. 1-3 sentences."
        )
        player = lookup_player(sender_name=sender)
        player_name = _first_name_from_player(player) if player else sender

        enhanced = llm_client.generate(context, player_name=player_name)
        Config.LLM_ENABLED = original_enabled

        if enhanced:
            shadow_msg = f"[{sender}]: {body}\n\n🤖 LLM: {enhanced}"
            send_message(Config.SHADOW_GROUP_ID, shadow_msg)
        else:
            shadow_msg = f"[{sender}]: {body}\n\n📋 Template: {template_reply}"
            send_message(Config.SHADOW_GROUP_ID, shadow_msg)
    except Exception as e:
        logger.warning("Shadow message failed: %s", e)


def _shadow_banter(sender, sender_phone, body):
    """Try LLM banter in the shadow group for general chat messages."""
    try:
        original_enabled = Config.LLM_ENABLED
        Config.LLM_ENABLED = True

        player = lookup_player(sender_phone=sender_phone, sender_name=sender)
        player_name = _first_name_from_player(player) if player else sender

        # Always try banter in shadow mode (ignore banter_rate)
        context = (
            f'{sender} said in the group chat: "{body}"\n\n'
            f"Respond in character if you have something witty to say. Keep it to 1-2 sentences."
        )
        response = llm_client.generate(context, player_name=player_name)
        Config.LLM_ENABLED = original_enabled

        if response:
            shadow_msg = f"[{sender}]: {body}\n\n🤖 Banter: {response}"
            send_message(Config.SHADOW_GROUP_ID, shadow_msg)
    except Exception as e:
        logger.warning("Shadow banter failed: %s", e)


def send_message(chat_id, text):
    """Send a message back through the Node.js bridge. Retries on 503 (reconnecting)."""
    import time

    for attempt in range(3):
        try:
            resp = requests.post(
                f"{Config.BRIDGE_URL}/send",
                json={"chat_id": chat_id, "message": text},
                timeout=15,
            )
            if resp.status_code == 200:
                return
            if resp.status_code == 503:
                data = resp.json() if resp.text else {}
                if data.get("retry") and attempt < 2:
                    wait = 5 * (attempt + 1)
                    logger.info("Bridge reconnecting, retry in %ds (attempt %d/3)", wait, attempt + 2)
                    time.sleep(wait)
                    continue
            logger.error("Bridge returned %d: %s", resp.status_code, resp.text[:200] if resp.text else "")
            return
        except requests.RequestException as e:
            logger.error("Failed to send message via bridge: %s", e)
            if attempt < 2:
                time.sleep(3)
            return


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
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=Config.FLASK_PORT, debug=debug)
