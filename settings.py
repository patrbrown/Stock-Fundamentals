"""Local settings (SEC contact identity) stored next to the app in settings.json."""
from __future__ import annotations

import json
import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
SETTINGS_PATH = APP_DIR / "settings.json"
CACHE_DIR = APP_DIR / "cache"


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


def save_settings(data: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def sec_user_agent() -> str | None:
    """SEC asks every caller to identify itself as '<name> <email>'.

    Deployed: set the SEC_USER_AGENT environment variable / secret (e.g. "Pat Brown pat@example.com").
    Local: an admin saves it in the app (stored in settings.json).
    """
    env = os.environ.get("SEC_USER_AGENT", "").strip()
    if env:
        return env
    s = load_settings()
    name, email = (s.get("name") or "").strip(), (s.get("email") or "").strip()
    if not email:
        return None
    return f"{name or 'StockFundamentals'} {email}"
