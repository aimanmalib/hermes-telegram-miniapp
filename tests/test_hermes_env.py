"""Credentials come through Hermes (agent.secret_scope.get_secret), never from .env directly."""

from __future__ import annotations

import json
import sys
import time
import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import BOT_TOKEN, OWNER_ID, PLUGIN_DIR, load_module, make_init_data

PREFIX = "/api/plugins/telegram-app"
ENV_NAMES = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_ID", "TELEGRAM_ALLOWED_USERS",
             "TELEGRAM_INITDATA_MAX_AGE", "TELEGRAM_BOT_ID")


@pytest.fixture
def clean(tmp_path, monkeypatch):
    """No credentials in the process env; a HERMES_HOME whose .env holds a token the plugin must not read."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_APP_ALERTS_DISABLED", "1")
    for var in ENV_NAMES:
        monkeypatch.delenv(var, raising=False)
    (tmp_path / ".env").write_text(f"TELEGRAM_BOT_TOKEN={BOT_TOKEN}\nTELEGRAM_OWNER_ID={OWNER_ID}\n")
    for name in list(sys.modules):
        if name.startswith("hermes_tma_"):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.delitem(sys.modules, "agent", raising=False)
    monkeypatch.delitem(sys.modules, "agent.secret_scope", raising=False)
    return tmp_path


def fake_secret_scope(monkeypatch, values: dict, *, raises: Exception | None = None):
    calls: list[str] = []

    def get_secret(name, default=None):
        calls.append(name)
        if raises is not None:
            raise raises
        return values.get(name, default)

    scope = types.ModuleType("agent.secret_scope")
    scope.get_secret = get_secret
    pkg = types.ModuleType("agent")
    pkg.secret_scope = scope
    monkeypatch.setitem(sys.modules, "agent", pkg)
    monkeypatch.setitem(sys.modules, "agent.secret_scope", scope)
    return calls


def app_client(monkeypatch):
    ws = types.ModuleType("hermes_cli.web_server")
    ws._SESSION_TOKEN = "session"
    ws._PUBLIC_API_PATHS = frozenset()
    pkg = types.ModuleType("hermes_cli")
    pkg.web_server = ws
    monkeypatch.setitem(sys.modules, "hermes_cli", pkg)
    monkeypatch.setitem(sys.modules, "hermes_cli.web_server", ws)
    mod = load_module("plugin_api", "hermes_dashboard_plugin_telegram_app_env_test")
    app = FastAPI()
    app.include_router(mod.router, prefix=PREFIX)
    return TestClient(app)


def login(client):
    return client.post(f"{PREFIX}/auth/verify", json={"init_data": make_init_data(auth_date=int(time.time()))})


def test_login_reads_credentials_through_get_secret(clean, monkeypatch):
    calls = fake_secret_scope(monkeypatch, {"TELEGRAM_BOT_TOKEN": BOT_TOKEN, "TELEGRAM_OWNER_ID": str(OWNER_ID)})
    assert login(app_client(monkeypatch)).status_code == 200
    assert "TELEGRAM_BOT_TOKEN" in calls and "TELEGRAM_OWNER_ID" in calls


def test_dotenv_file_is_never_read(clean, monkeypatch):
    # Hermes answers "unset"; the .env in HERMES_HOME holds valid values. Reading it would log in.
    fake_secret_scope(monkeypatch, {})
    assert login(app_client(monkeypatch)).status_code == 503
    alerts = load_module("alerts", "tma_test_alerts_env")
    assert alerts._bot_token_and_chat() is None


def test_unscoped_secret_error_counts_as_unset(clean, monkeypatch):
    class UnscopedSecretError(RuntimeError):
        pass

    fake_secret_scope(monkeypatch, {}, raises=UnscopedSecretError("no scope"))
    assert login(app_client(monkeypatch)).status_code == 503
    alerts = load_module("alerts", "tma_test_alerts_unscoped")
    assert alerts._bot_token_and_chat() is None


def test_alerts_read_through_get_secret(clean, monkeypatch):
    fake_secret_scope(monkeypatch, {"TELEGRAM_BOT_TOKEN": "1:x", "TELEGRAM_ALLOWED_USERS": "abc, 77"})
    alerts = load_module("alerts", "tma_test_alerts_scope")
    assert alerts._bot_token_and_chat() == ("1:x", 77)


def test_without_hermes_the_process_env_is_used(clean, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("TELEGRAM_OWNER_ID", str(OWNER_ID))
    assert login(app_client(monkeypatch)).status_code == 200


def test_versions_agree():
    import re

    root = PLUGIN_DIR.parents[1]
    manifest = json.loads((PLUGIN_DIR / "manifest.json").read_text())["version"]
    plugin_yaml = re.search(r"^version:\s*(\S+)", (root / "plugin" / "plugin.yaml").read_text(), re.M).group(1)
    web = json.loads((root / "web" / "package.json").read_text())["version"]
    citation = re.search(r"^version:\s*(\S+)", (root / "CITATION.cff").read_text(), re.M).group(1)
    assert manifest == plugin_yaml == web == citation
