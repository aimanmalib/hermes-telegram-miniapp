"""Plugin settings and process facts shared by the route modules.

Every credential goes through ``hermes_compat.secret`` (Hermes's credential route).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import List

compat = sys.modules["hermes_tma_hermes_compat"]  # loaded first by plugin_api.py
tg_auth = compat.load_sibling("tg_auth")

START_TIME = time.time()


def _plugin_version() -> str:
    try:
        manifest = Path(__file__).resolve().parent / "manifest.json"
        return str(json.loads(manifest.read_text("utf-8")).get("version", "0.0.0"))
    except Exception:
        return "0.0.0"


VERSION = _plugin_version()


def uptime_sec() -> int:
    return int(time.time() - START_TIME)


def env(name: str, default: str = "") -> str:
    return compat.secret(name, default)


def bot_token() -> str:
    return env("TELEGRAM_BOT_TOKEN")


def allowed_user_ids() -> List[str]:
    """Union of TELEGRAM_OWNER_ID and TELEGRAM_ALLOWED_USERS (numeric ids, owner first)."""
    ids: List[str] = []
    for raw in (env("TELEGRAM_OWNER_ID"), env("TELEGRAM_ALLOWED_USERS")):
        for uid in tg_auth.parse_allowlist(raw):
            if uid not in ids:
                ids.append(uid)
    return ids


def max_age() -> int:
    return tg_auth.parse_max_age(env("TELEGRAM_INITDATA_MAX_AGE"))
