"""Hermes plugin entry point for the Telegram Mini App.

The routes live in the dashboard extension (``dashboard/manifest.json`` and
``dashboard/plugin_api.py``), which the dashboard loads on its own. ``register``
adds the one thing that extension cannot: the token-auth provider that verifies
Telegram ``initData`` on the login route (docs/decisions/0006).
"""

import importlib.util
import logging
import sys
from pathlib import Path

_log = logging.getLogger("hermes.plugin.telegram-app")
_COMPAT = "hermes_tma_hermes_compat"


def _compat():
    if _COMPAT not in sys.modules:
        spec = importlib.util.spec_from_file_location(_COMPAT, Path(__file__).resolve().parent / "dashboard" / "hermes_compat.py")
        if spec is None or spec.loader is None:
            raise ImportError("cannot load hermes_compat.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[_COMPAT] = mod
        spec.loader.exec_module(mod)
    return sys.modules[_COMPAT]


def register(ctx) -> None:
    compat = _compat()
    compat.bind_plugin_context(ctx)  # plugin settings (the admins list) are read through ctx.get_config
    try:
        tg_token = compat.load_sibling("tg_token")
        provider = tg_token.provider()
    except Exception as exc:  # Hermes without the provider API: login stays closed (401)
        _log.warning("telegram-app: login provider unavailable (%s)", exc)
        return
    ctx.register_dashboard_auth_provider(provider)
    compat.register_token_route(tg_token.LOGIN_PATH, tg_token.SCOPE)
