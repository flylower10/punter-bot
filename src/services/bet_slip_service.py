"""
Bet slip image processing service.

Pull-model: Flask calls the bridge's /media endpoint to retrieve the image,
then uses Groq vision to extract per-leg odds, stake, and potential return.

NOTE: The caller (app.py _handle_placer_bet_confirmation) accepts images from
any known group member, not only the designated placer. Delegation is
intentionally supported. The placer credited in the database is always
next_placer from rotation_service, not the image sender.

All operations are best-effort — failures are logged but never propagate to
callers. process_bet_slip() is always safe to call fire-and-forget.
"""

import difflib
import logging

import requests

from src.config import Config
from src.db import get_db
from src import llm_client

logger = logging.getLogger(__name__)


def fetch_image_from_bridge(message_id):
    """
    POST to bridge /media to retrieve the base64-encoded image.
    Returns {"data": "<b64>", "mimetype": "image/jpeg"} or None.
    """
    try:
        resp = requests.post(
            f"{Config.BRIDGE_URL}/media",
            json={"message_id": message_id},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("Bridge /media returned %d for message_id=%s", resp.status_code, message_id)
        return None
    except Exception:
        logger.exception("Failed to fetch image from bridge (message_id=%s)", message_id)
        return None


def match_legs_to_picks(legs, picks):
    """
    Fuzzy-match extracted leg selections to pick descriptions.

    Uses difflib.SequenceMatcher (same approach as pick_service matching).
    Returns list of (pick_id, confirmed_odds) for matches above 0.6 threshold.
    Unmatched legs are logged at WARNING level.
    """
    matched = []
    for leg in legs:
        selection = (leg.get("selection") or "").lower().strip()
        odds = leg.get("odds")
        if not selection:
            continue

        best_ratio = 0.0
        best_pick = None
        for pick in picks:
            desc = (pick.get("description") or "").lower().strip()
            ratio = difflib.SequenceMatcher(None, selection, desc).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_pick = pick

        if best_pick and best_ratio >= 0.6:
            matched.append((best_pick["id"], odds))
            logger.info(
                "Matched leg '%s' → pick %d '%s' (ratio=%.2f, odds=%s)",
                selection, best_pick["id"], best_pick.get("description", ""), best_ratio, odds,
            )
        else:
            logger.warning(
                "Unmatched leg '%s' (best ratio=%.2f, best pick='%s')",
                selection, best_ratio, best_pick.get("description", "") if best_pick else "none",
            )

    return matched


def record_bet_slip(week_id, placer_id, extracted):
    """
    Insert a row into bet_slips with the extracted totals.
    Any of stake, total_odds, potential_return may be None.
    """
    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO bet_slips (week_id, placer_id, total_odds, stake, potential_return)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                week_id,
                placer_id,
                extracted.get("total_odds"),
                extracted.get("stake"),
                extracted.get("potential_return"),
            ),
        )
        conn.commit()
        logger.info(
            "Recorded bet slip for week_id=%d placer_id=%d (stake=%s total_odds=%s return=%s)",
            week_id, placer_id,
            extracted.get("stake"), extracted.get("total_odds"), extracted.get("potential_return"),
        )
    finally:
        conn.close()


def update_confirmed_odds(matched_legs):
    """
    SET confirmed_odds on each matched pick.
    matched_legs: list of (pick_id, confirmed_odds)
    """
    if not matched_legs:
        return
    conn = get_db()
    try:
        for pick_id, odds in matched_legs:
            conn.execute(
                "UPDATE picks SET confirmed_odds = ? WHERE id = ?",
                (odds, pick_id),
            )
        conn.commit()
        logger.info("Updated confirmed_odds for %d pick(s)", len(matched_legs))
    finally:
        conn.close()


def process_bet_slip(week_id, placer_id, message_id, picks):
    """
    Orchestrate: fetch image → extract → match legs → persist.
    Best-effort — never raises. Safe to call fire-and-forget.
    """
    try:
        image = fetch_image_from_bridge(message_id)
        if not image:
            return

        extracted = llm_client.read_bet_slip(image["data"], image.get("mimetype", "image/jpeg"))
        if not extracted:
            return

        record_bet_slip(week_id, placer_id, extracted)

        legs = extracted.get("legs") or []
        if legs and picks:
            matched = match_legs_to_picks(legs, picks)
            if matched:
                update_confirmed_odds(matched)
    except Exception:
        logger.exception("process_bet_slip failed silently (week_id=%d)", week_id)
