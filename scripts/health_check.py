#!/usr/bin/env python3
"""
Health check script for Punter Bot.

Pings the Flask /health and Bridge /health endpoints every 5 minutes.
On failure, sends a Telegram alert. Sends a recovery alert when service
comes back up.

Run standalone: python scripts/health_check.py
Or via PM2: pm2 start ecosystem.config.js (includes health-check)
"""

import logging
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

import requests

# Config
FLASK_URL = os.getenv("FLASK_URL", "http://127.0.0.1:5001")
BRIDGE_URL = os.getenv("BRIDGE_URL", "http://127.0.0.1:3000")
INTERVAL_SECONDS = int(os.getenv("HEALTH_CHECK_INTERVAL", "300"))
LOG_PATH = PROJECT_ROOT / "logs" / "health-check.log"
TIMEOUT_SECONDS = 10

# Telegram config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Logging
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

_previous_status = {"flask": True, "bridge": True}


def notify_telegram(message: str) -> None:
    """Send alert via Telegram bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured — skipping alert")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            timeout=10,
        )
    except Exception as e:
        logger.warning("Telegram notification failed: %s", e)


def check_endpoint(url: str, name: str, require_whatsapp: bool = False) -> bool:
    """Ping a /health endpoint. Return True if OK.

    If require_whatsapp=True, also checks that whatsapp=="connected" in the
    response body (used for the bridge, which always returns status=ok even
    when the WhatsApp client is disconnected or crash-looping).
    """
    try:
        resp = requests.get(url, timeout=TIMEOUT_SECONDS)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok":
                if require_whatsapp and data.get("whatsapp") != "connected":
                    logger.warning("%s health check: WhatsApp disconnected (state=%s)", name, data.get("whatsapp"))
                    return False
                return True
        logger.warning("%s health check failed: status=%d body=%s", name, resp.status_code, resp.text[:200])
        return False
    except requests.RequestException as e:
        logger.warning("%s health check failed: %s", name, e)
        return False


def main() -> None:
    logger.info(
        "Health check started (interval=%ds, flask=%s, bridge=%s, telegram=%s)",
        INTERVAL_SECONDS,
        FLASK_URL,
        BRIDGE_URL,
        "configured" if TELEGRAM_BOT_TOKEN else "not configured",
    )

    consecutive_failures = {"flask": 0, "bridge": 0}

    while True:
        flask_ok = check_endpoint(f"{FLASK_URL}/health", "Flask")
        bridge_ok = check_endpoint(f"{BRIDGE_URL}/health", "Bridge", require_whatsapp=True)

        alerts = []

        for name, ok in [("flask", flask_ok), ("bridge", bridge_ok)]:
            if not ok:
                consecutive_failures[name] += 1
                if consecutive_failures[name] == 1:
                    label = "Flask (backend)" if name == "flask" else "Bridge (WhatsApp)"
                    alerts.append(f"{label} is DOWN")
                if _previous_status[name]:
                    _previous_status[name] = False
            else:
                if not _previous_status[name]:
                    label = "Flask (backend)" if name == "flask" else "Bridge (WhatsApp)"
                    alerts.append(f"{label} has RECOVERED")
                    _previous_status[name] = True
                consecutive_failures[name] = 0

        if alerts:
            message = "\U0001f6a8 Punter Bot Alert\n" + "\n".join(alerts)
            logger.error(message)
            notify_telegram(message)

        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
