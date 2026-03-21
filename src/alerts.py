"""
Telegram alert helper.

Sends operational notifications to the configured ALERTS_CHAT_ID.
Non-blocking — failures are logged but never propagate to callers.
"""

import logging

import requests

from src.config import Config

logger = logging.getLogger(__name__)


def send_alert(message: str) -> None:
    """Send a message to the Punter Bot Alerts Telegram channel."""
    if not Config.TELEGRAM_BOT_TOKEN or not Config.ALERTS_CHAT_ID:
        logger.debug("Telegram alerts not configured — skipping")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": Config.ALERTS_CHAT_ID, "text": message},
            timeout=10,
        )
    except Exception as e:
        logger.warning("Telegram alert failed (non-blocking): %s", e)
