"""Telegram Mini App plugin — backend API routes.

Mounted by the Hermes dashboard plugin loader at ``/api/plugins/telegram-app/``.

Auth model
----------
Hermes gates every ``/api/*`` route with the dashboard session token
(``X-Hermes-Session-Token``). This plugin lets two paths through *without*
that token by adding them to the dashboard's public-path set:

  /api/plugins/telegram-app/health        — liveness, no secrets
  /api/plugins/telegram-app/auth/verify   — accepts Telegram initData and
                                            returns the dashboard session token

The Mini App then:

  1. Reads ``window.Telegram.WebApp.initData``.
  2. POSTs it to ``/auth/verify``. The plugin verifies the signature (HMAC-SHA256
     keyed by the bot token; Ed25519 against Telegram's public key as a
     fallback), rejects stale ``auth_date`` values and checks the user against
     an explicit allowlist (see ``tg_auth.py``).
  3. Receives the dashboard session token and sends it as
     ``X-Hermes-Session-Token`` on every later call, so the dashboard's own
     auth middleware does the rest.

Every other route relies on that upstream middleware.

Layout
------
This file only assembles the router. ``hermes_compat.py`` holds every touch of
Hermes internals; ``settings.py`` holds credentials and process facts; each
``routes_*.py`` holds one tab's endpoints.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi import APIRouter


def _bootstrap_compat():
    """Load ``hermes_compat.py`` — which provides ``load_sibling`` for everything else."""
    name = "hermes_tma_hermes_compat"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / "hermes_compat.py")
        if spec is None or spec.loader is None:
            raise ImportError("cannot load hermes_compat.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


compat = _bootstrap_compat()

# Order is the order routes are matched in; each module owns disjoint paths.
_ROUTE_MODULES = (
    "routes_auth",
    "routes_status",
    "routes_sessions",
    "routes_cron",
    "routes_knowledge",
    "routes_logs",
    "routes_send",
    "routes_ask",
    "routes_alerts",
)

router = APIRouter()
for _name in _ROUTE_MODULES:
    router.include_router(compat.load_sibling(_name).router)
