"""Credentials and settings, read through Hermes's own route.

Hermes resolves credentials with ``agent.secret_scope.get_secret``: it honours the
active profile when one dashboard serves several, and it is the only route the
plugin catalog allows (admission rule 11 — a plugin never reads ``.env`` itself).

Outside Hermes (unit tests, a bare checkout) ``agent`` is not importable, and the
process environment is used instead.
"""

from __future__ import annotations

import logging
import os

_log = logging.getLogger("hermes.plugin.telegram-app")


def get(name: str, default: str = "") -> str:
    try:
        from agent.secret_scope import get_secret  # type: ignore
    except ImportError:
        return os.environ.get(name, "").strip() or default
    try:
        value = get_secret(name, None)
    except Exception as exc:
        # UnscopedSecretError: multiplexing is on and no profile scope is active
        # (a background thread, for example). Treat the value as unset rather than
        # guess another profile's.
        _log.warning("telegram-app: cannot read %s here (%s); treating it as unset", name, type(exc).__name__)
        return default
    return (value or "").strip() or default
