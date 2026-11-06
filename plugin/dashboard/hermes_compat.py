"""Every place the plugin touches Hermes internals, in one module.

Hermes has no stable plugin API for some of what this plugin needs, so it reaches
into the dashboard module and a few helpers directly. Keeping all of those
touches here means a Hermes upgrade that renames one of them breaks exactly one
file (and the contract tests that exercise it):

* ``hermes_cli.dashboard_auth`` — the token-auth seam that verifies the
  login route's bearer (Telegram ``initData``) through our provider;
* ``hermes_cli.web_server._SESSION_TOKEN`` — the token the Mini App receives
  after a verified Telegram login;
* ``hermes_cli.web_server.app.version`` — the running Hermes release;
* ``cron.jobs`` — probed for optional features (``capabilities``);
* ``agent.secret_scope.get_secret`` — Hermes's credential route;
* ``hermes_constants.get_hermes_home`` — the Hermes home directory.

The module has no import-time side effects; ``plugin/__init__.py`` registers
the login provider and route once.

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
from typing import Callable, Optional

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
# Login route. The Mini App sends its Telegram ``initData`` as the bearer token
# on ``POST /auth/verify``. Hermes's token-auth seam (v0.23.0+) asks the
# provider registered in ``plugin/__init__.py`` to verify it, so the route never
# has to be public and no Hermes module attribute is rebound. The seam matches
# exact paths, which is fine: only the login route uses it, every other route
# takes the dashboard session token the login returns. See docs/decisions/0006.
# ---------------------------------------------------------------------------
AUTH_MODE_TOKEN_SEAM = "token-seam"
AUTH_MODE_UNAVAILABLE = "unavailable"


def register_token_route(path: str) -> bool:
    """Opt ``path`` in to bearer-token auth. False when this Hermes has no seam (older than v0.23.0)."""
    try:
        from hermes_cli.dashboard_auth.token_auth import register_token_route as _register  # type: ignore
    except Exception as exc:
        _log.warning("telegram-app: Hermes has no token-auth seam (%s); login is unavailable", exc)
        return False
    _register(path)
    return True


def token_provider(name: str, display_name: str, verify: Callable[[str], Optional[str]]):
    """A token-only ``DashboardAuthProvider``: ``verify(token)`` returns a principal id or None.

    No browser login and no cookie session; the interactive methods refuse. Raises ImportError on a
    Hermes without the dashboard-auth provider API.
    """
    from hermes_cli.dashboard_auth import DashboardAuthProvider, TokenPrincipal  # type: ignore

    class _Provider(DashboardAuthProvider):
        supports_token = True
        supports_session = False
        interactive_login = False

        def verify_token(self, *, token: str):
            principal = verify(token)
            return TokenPrincipal(principal=principal, provider=name) if principal else None

        def start_login(self, *, redirect_uri: str):
            raise NotImplementedError(f"{display_name} has no browser login flow")

        def complete_login(self, *, code: str, state: str, code_verifier: str, redirect_uri: str):
            raise NotImplementedError(f"{display_name} has no browser login flow")

        def verify_session(self, *, access_token: str):
            return None

        def refresh_session(self, *, refresh_token: str):
            raise NotImplementedError(f"{display_name} has no sessions")

        def revoke_session(self, *, refresh_token: str) -> None:
            return None

    _Provider.name = name
    _Provider.display_name = display_name
    return _Provider()


def auth_mode(path: str, provider_name: str) -> str:
    """``token-seam`` while ``path`` is token-authable and our provider is registered, else ``unavailable``.

    Checked against the live dashboard on every call; when it is ``unavailable`` the login fails
    closed with the dashboard's own 401.
    """
    try:
        from hermes_cli.dashboard_auth import list_token_providers  # type: ignore
        from hermes_cli.dashboard_auth.token_auth import is_token_route  # type: ignore

        ours = any(getattr(p, "name", "") == provider_name for p in list_token_providers())
        return AUTH_MODE_TOKEN_SEAM if ours and is_token_route(path) else AUTH_MODE_UNAVAILABLE
    except Exception:
        return AUTH_MODE_UNAVAILABLE


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
