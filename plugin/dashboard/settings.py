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


def _setting_ids(value) -> List[str]:
    """Numeric ids from the ``admins`` plugin setting: a YAML list or a comma-separated string."""
    if isinstance(value, (list, tuple)):
        value = ",".join(str(v) for v in value if not isinstance(v, bool))
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return []
    return list(tg_auth.parse_allowlist(str(value)))


def admin_user_ids() -> List[str]:
    """The plugin-owned admin list: TELEGRAM_OWNER_ID, then the plugin setting ``admins``.

    Only these Telegram users may log in, receive alerts and be messaged by the send box.
    Hermes's own list of who may chat with the bot is never read here: the QR setup fills it
    in, and being allowed to chat must not grant the dashboard (docs/decisions/0007).
    """
    ids: List[str] = []
    for uid in [*tg_auth.parse_allowlist(env("TELEGRAM_OWNER_ID")), *_setting_ids(compat.plugin_setting("admins"))]:
        if uid not in ids:
            ids.append(uid)
    return ids


def max_age() -> int:
    return tg_auth.parse_max_age(env("TELEGRAM_INITDATA_MAX_AGE"))
