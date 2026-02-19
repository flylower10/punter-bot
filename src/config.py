import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID", "")
    _group_ids_raw = os.getenv("GROUP_CHAT_IDS", "")
    GROUP_CHAT_IDS = [g.strip() for g in _group_ids_raw.split(",") if g.strip()] if _group_ids_raw else []
    FLASK_PORT = int(os.getenv("FLASK_PORT", "5001"))
    BRIDGE_URL = os.getenv("BRIDGE_URL", "http://localhost:3000")
    DB_PATH = os.getenv("DB_PATH", "data/punter_bot.db")
    TIMEZONE = os.getenv("TIMEZONE", "Europe/Dublin")
    ADMIN_PHONE = os.getenv("ADMIN_PHONE", "")
    _admin_phones_raw = os.getenv("ADMIN_PHONES", "")
    ADMIN_PHONES = [p.strip() for p in _admin_phones_raw.split(",") if p.strip()] if _admin_phones_raw else []
    _admin_nicks_raw = os.getenv("ADMIN_NICKNAMES", "ed,edmund,aidan")
    ADMIN_NICKNAMES = [n.strip().lower() for n in _admin_nicks_raw.split(",") if n.strip()]
    SUPERADMIN_PHONE = os.getenv("SUPERADMIN_PHONE", "")
    _rotation_order_raw = os.getenv("ROTATION_ORDER", "")
    ROTATION_ORDER = [n.strip() for n in _rotation_order_raw.split(",") if n.strip()] if _rotation_order_raw else []
    TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

    # LLM personality feature
    LLM_ENABLED = os.getenv("LLM_ENABLED", "false").lower() == "true"
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
