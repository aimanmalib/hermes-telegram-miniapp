"""Every place the plugin touches Hermes internals, in one module.

Hermes has no stable plugin API for some of what this plugin needs, so it reaches
into the dashboard module and a few helpers directly. Keeping all of those
touches here means a Hermes upgrade that renames one of them breaks exactly one
file (and the contract tests that exercise it):

* ``hermes_cli.web_server._PUBLIC_API_PATHS`` — the paths the dashboard's auth
  middleware lets through without a session token;
* ``hermes_cli.web_server._SESSION_TOKEN`` — the token the Mini App receives
  after a verified Telegram login;
* ``hermes_cli.web_server.app.version`` — the running Hermes release;
* ``cron.jobs`` — probed for optional features (``capabilities``);
* ``agent.secret_scope.get_secret`` — Hermes's credential route;
* ``hermes_constants.get_hermes_home`` — the Hermes home directory.

The module has no import-time side effects; ``plugin_api.py`` calls
``allow_public`` once.

It also holds ``load_sibling``: Hermes imports ``plugin_api.py`` with
``spec_from_file_location`` (not as a package), so ``from . import x`` does not
work, and putting this directory on ``sys.path`` would let a generic name like
``alerts`` collide with any other module of that name.
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
import os
import sys
from pathlib import Path
from typing import Iterable

_HERE = Path(__file__).resolve().parent
MODULE_PREFIX = "hermes_tma_"

_log = logging.getLogger("hermes.plugin.telegram-app")


def load_sibling(name: str):
    """Import ``<name>.py`` beside this file once, under a plugin-unique module name."""
    mod_name = f"{MODULE_PREFIX}{name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, _HERE / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
    return mod


def hermes_home() -> Path:
    """Hermes home directory: Hermes' own resolver when available, else $HERMES_HOME or ~/.hermes."""
    try:
        from hermes_constants import get_hermes_home  # type: ignore

        return Path(get_hermes_home())
    except Exception:
        env = os.environ.get("HERMES_HOME", "").strip()
        return Path(env).expanduser() if env else Path.home() / ".hermes"


# ---------------------------------------------------------------------------
# Public paths. Hermes has no plugin API for declaring unauthenticated routes,
# so we add ours to ``hermes_cli.web_server._PUBLIC_API_PATHS`` at import time.
# The loopback auth middleware looks that module global up on every request.
# The OAuth-gated mode (``auth_required``) uses a separate list and cookie
# auth, and is not supported by this plugin.
#
# Hermes v0.23.0 added a bearer-token seam (``register_token_route``). It is not
# used: it matches exact paths only (``/sessions/{id}/messages`` cannot be
# registered) and makes a route token-authable, not public, so the login route
# would still need this list. See docs/decisions/0005.
# ---------------------------------------------------------------------------
AUTH_MODE_LEGACY = "legacy-public-paths"
AUTH_MODE_UNAVAILABLE = "unavailable"

_public_paths: tuple[str, ...] = ()


def allow_public(paths: Iterable[str]) -> None:
    global _public_paths
    paths = tuple(paths)
    _public_paths = paths
    try:
        import hermes_cli.web_server as ws  # type: ignore

        existing = set(getattr(ws, "_PUBLIC_API_PATHS", frozenset()))
        existing.update(paths)
        ws._PUBLIC_API_PATHS = frozenset(existing)
        _log.info("telegram-app: registered public paths %s", list(paths))
    except Exception as exc:
        _log.warning("telegram-app: could not register public paths: %s", exc)


def auth_mode() -> str:
    """How the login route is reachable, checked against the live dashboard on every call.

    ``legacy-public-paths`` while every path given to ``allow_public`` is still
    in the dashboard's public set; ``unavailable`` otherwise (login then fails
    closed with the dashboard's own 401).
    """
    if not _public_paths:
        return AUTH_MODE_UNAVAILABLE
    try:
        import hermes_cli.web_server as ws  # type: ignore

        current = set(getattr(ws, "_PUBLIC_API_PATHS", ()))
    except Exception:
        return AUTH_MODE_UNAVAILABLE
    return AUTH_MODE_LEGACY if set(_public_paths) <= current else AUTH_MODE_UNAVAILABLE


def hermes_version() -> str | None:
    """The running Hermes release (the dashboard app's ``version``), or None outside Hermes."""
    try:
        import hermes_cli.web_server as ws  # type: ignore

        version = getattr(getattr(ws, "app", None), "version", None)
    except Exception:
        return None
    return str(version) if version else None


def capabilities() -> dict[str, bool]:
    """Optional Hermes features, detected by probing rather than by version number.

    ``cron_cancel``: ``cron.jobs.cancel_job_run`` exists (stop a running job).
    ``cron_catch_up``: ``cron.jobs.create_job`` takes ``catch_up`` (per-job missed-run policy).
    """
    caps = {"cron_cancel": False, "cron_catch_up": False}
    try:
        import cron.jobs as jobs  # type: ignore
    except Exception:
        return caps
    caps["cron_cancel"] = callable(getattr(jobs, "cancel_job_run", None))
    create = getattr(jobs, "create_job", None)
    try:
        caps["cron_catch_up"] = callable(create) and "catch_up" in inspect.signature(create).parameters
    except (TypeError, ValueError):
        pass
    return caps


def get_session_token() -> str:
    """The running dashboard's session token (``hermes_cli.web_server._SESSION_TOKEN``).

    Read at request time: Hermes may rebind it (desktop/SSH launches).
    """
    try:
        import hermes_cli.web_server as ws  # type: ignore

        return getattr(ws, "_SESSION_TOKEN", "") or ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Credentials and settings, read through Hermes's own route.
#
# Hermes resolves credentials with ``agent.secret_scope.get_secret``: it honours
# the active profile when one dashboard serves several, and it is the only route
# the plugin catalog allows (admission rule 11 — a plugin never reads ``.env``
# itself). Outside Hermes (unit tests, a bare checkout) ``agent`` is not
# importable, and the process environment is used instead.
# ---------------------------------------------------------------------------
def secret(name: str, default: str = "") -> str:
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
