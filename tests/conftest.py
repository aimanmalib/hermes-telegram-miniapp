"""Shared helpers. The plugin is loaded from files, the way Hermes loads it."""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import sys
import types
import urllib.parse
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugin" / "dashboard"

BOT_TOKEN = "123456789:AAE-known-answer-test-token"
OWNER_ID = 424242
USER = {"id": OWNER_ID, "first_name": "Ada", "username": "ada_test", "language_code": "en"}
USER_JSON = json.dumps(USER, separators=(",", ":"))
SESSION_TOKEN = "dashboard-session-token-for-tests"
PREFIX = "/api/plugins/telegram-app"


def load_module(name: str, alias: str):
    sys.modules.pop(alias, None)
    spec = importlib.util.spec_from_file_location(alias, PLUGIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


def spec_hash(fields: dict, bot_token: str) -> str:
    """Independent re-statement of the spec (deliberately not using tg_auth)."""
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields) if k != "hash")
    return hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()


def encode(fields: dict, *, plus_spaces: bool = False) -> str:
    quote = urllib.parse.quote_plus if plus_spaces else urllib.parse.quote
    return "&".join(f"{k}={quote(str(v), safe='')}" for k, v in fields.items())


def make_init_data(
    *,
    auth_date: int,
    user: dict | None = None,
    bot_token: str = BOT_TOKEN,
    extra: dict | None = None,
    ed_key=None,
    ed_bot_id: str | None = None,
    plus_spaces: bool = False,
) -> str:
    fields = {
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(user or USER, separators=(",", ":")),
        "auth_date": str(auth_date),
    }
    fields.update(extra or {})
    if ed_key is not None:
        body = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
        message = f"{ed_bot_id}:WebAppData\n{body}".encode()
        fields["signature"] = base64.urlsafe_b64encode(ed_key.sign(message)).rstrip(b"=").decode()
    fields["hash"] = spec_hash(fields, bot_token)
    return encode(fields, plus_spaces=plus_spaces)


@pytest.fixture
def tg_auth():
    return load_module("tg_auth", "tma_test_tg_auth")


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:AAE-known-answer-test-token")
    monkeypatch.setenv("TELEGRAM_OWNER_ID", str(OWNER_ID))
    for var in ("TELEGRAM_ALLOWED_USERS", "TELEGRAM_INITDATA_MAX_AGE", "TELEGRAM_BOT_ID", "TELEGRAM_APP_ALERTS_DISABLED"):
        monkeypatch.delenv(var, raising=False)

    ws = types.ModuleType("hermes_cli.web_server")
    ws._SESSION_TOKEN = SESSION_TOKEN
    pkg = types.ModuleType("hermes_cli")
    pkg.web_server = ws
    da, token_auth = stub_dashboard_auth()
    pkg.dashboard_auth = da
    monkeypatch.setitem(sys.modules, "hermes_cli", pkg)
    monkeypatch.setitem(sys.modules, "hermes_cli.web_server", ws)
    monkeypatch.setitem(sys.modules, "hermes_cli.dashboard_auth", da)
    monkeypatch.setitem(sys.modules, "hermes_cli.dashboard_auth.token_auth", token_auth)
    for name in list(sys.modules):
        if name.startswith("hermes_tma_"):
            monkeypatch.delitem(sys.modules, name)

    entry = load_entry()
    # plugins.entries.telegram-app.settings, read through ctx.get_config as in Hermes.
    # No alerts watcher thread in unit tests.
    config: dict = {"alerts_enabled": False}
    ctx = types.SimpleNamespace(register_dashboard_auth_provider=da.providers.append, get_config=config.get)
    entry.register(ctx)
    mod = load_module("plugin_api", "hermes_dashboard_plugin_telegram_app_test")
    app = FastAPI()
    app.include_router(mod.router, prefix=PREFIX)
    return types.SimpleNamespace(mod=mod, ws=ws, da=da, token_auth=token_auth, config=config, client=TestClient(app))


def stub_dashboard_auth():
    """The slice of ``hermes_cli.dashboard_auth`` (v0.23.0) the plugin uses."""
    import dataclasses

    da = types.ModuleType("hermes_cli.dashboard_auth")

    @dataclasses.dataclass(frozen=True)
    class TokenPrincipal:
        principal: str
        provider: str
        scopes: tuple = ()

    class DashboardAuthProvider:
        supports_token = False

    class ProviderError(Exception):
        pass

    da.ProviderError = ProviderError
    da.TokenPrincipal = TokenPrincipal
    da.DashboardAuthProvider = DashboardAuthProvider
    da.providers = []
    da.list_token_providers = lambda: [p for p in da.providers if p.supports_token]

    token_auth = types.ModuleType("hermes_cli.dashboard_auth.token_auth")
    token_auth.routes = set()
    token_auth.register_token_route = token_auth.routes.add
    token_auth.is_token_route = lambda path: path in token_auth.routes
    da.token_auth = token_auth
    return da, token_auth


def load_entry():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "plugin" / "__init__.py"
    spec = importlib.util.spec_from_file_location("hermes_tma_test_entry", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
