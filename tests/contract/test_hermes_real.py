"""The plugin inside a real Hermes dashboard, called the way the Mini App calls it.

Unit tests stub ``hermes_cli.web_server``; these do not. They catch a Hermes
release that renames or moves something ``plugin/dashboard/hermes_compat.py``
relies on (the public-path set, the session token, the credential route, the
Hermes home) or that changes how dashboard plugins are discovered and mounted.

The Hermes releases under test are listed in ``compat/hermes-versions.json``.

Hermes builds its FastAPI app and mounts dashboard plugins when
``hermes_cli.web_server`` is first imported, so the ``hermes`` fixture prepares a throwaway
Hermes home (plugin installed and enabled, synthetic credentials) *before* that
import, once per test session.

These tests are skipped when Hermes is not installed, so the ordinary unit run
is unchanged. CI sets ``HERMES_CONTRACT_REQUIRED=1`` so a broken Hermes install
fails the job instead of skipping it, and ``HERMES_EXPECT_VERSION`` so the job
proves which release it tested.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import time
import types
from pathlib import Path

import pytest

PREFIX = "/api/plugins/telegram-app"
REPO = Path(__file__).resolve().parents[2]
PLUGIN_NAME = "telegram-app"


def helpers():
    """``tests/conftest.py`` (initData signing, synthetic credentials), loaded by path.

    Both files are called ``conftest``, so a plain import would be ambiguous.
    """
    name = "tma_contract_unit_helpers"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, REPO / "tests" / "conftest.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


def _hermes_installed() -> bool:
    mod = sys.modules.get("hermes_cli")
    if mod is not None and not getattr(mod, "__file__", None):
        return False  # a unit-test stub, not Hermes
    try:
        return importlib.util.find_spec("hermes_cli.web_server") is not None
    except (ImportError, ValueError):
        return False


if not _hermes_installed() and os.environ.get("HERMES_CONTRACT_REQUIRED") == "1":
    raise RuntimeError("HERMES_CONTRACT_REQUIRED=1 but hermes_cli.web_server is not importable")


@pytest.fixture(scope="session")
def hermes(tmp_path_factory):
    """The real dashboard app with this plugin installed, plus what the tests need to call it."""
    if not _hermes_installed():
        pytest.skip("Hermes Agent is not installed (see compat/README.md)")
    h = helpers()
    home = tmp_path_factory.mktemp("hermes-home")
    shutil.copytree(
        REPO / "plugin",
        home / "plugins" / PLUGIN_NAME,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (home / "config.yaml").write_text(f"plugins:\n  enabled:\n    - {PLUGIN_NAME}\n", encoding="utf-8")
    (home / "logs").mkdir()
    (home / "logs" / "agent.log").write_text(
        "2026-01-01 00:00:00,000 INFO contract-test: marker line\n", encoding="utf-8"
    )

    env = {
        "HERMES_HOME": str(home),
        "TELEGRAM_BOT_TOKEN": h.BOT_TOKEN,
        "TELEGRAM_OWNER_ID": str(h.OWNER_ID),
        "TELEGRAM_APP_ALERTS_DISABLED": "1",
    }
    with pytest.MonkeyPatch.context() as mp:
        for key in ("TELEGRAM_ALLOWED_USERS", "TELEGRAM_INITDATA_MAX_AGE", "TELEGRAM_BOT_ID"):
            mp.delenv(key, raising=False)
        for key, value in env.items():
            mp.setenv(key, value)
        # Drop anything a unit test left behind: plugin modules loaded against a stub dashboard.
        for name in list(sys.modules):
            if name.startswith("hermes_tma_") or name.startswith("hermes_dashboard_plugin_telegram_app"):
                mp.delitem(sys.modules, name)

        import hermes_cli.web_server as ws
        from fastapi.testclient import TestClient

        # No ``with``: the app's lifespan starts Hermes background workers this test does not need.
        client = TestClient(ws.app)
        compat = sys.modules.get("hermes_tma_hermes_compat")
        yield types.SimpleNamespace(ws=ws, client=client, home=home, compat=compat, h=h)


def _login(hermes) -> str:
    init_data = hermes.h.make_init_data(auth_date=int(time.time()))
    r = hermes.client.post(f"{PREFIX}/auth/verify", json={"init_data": init_data})
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def _auth(hermes) -> dict:
    return {"X-Hermes-Session-Token": _login(hermes)}


def test_expected_hermes_release(hermes):
    want = os.environ.get("HERMES_EXPECT_VERSION", "").lstrip("v")
    if want:
        assert hermes.ws.app.version == want


def test_tested_releases_include_the_declared_minimum():
    versions = json.loads((REPO / "compat" / "hermes-versions.json").read_text(encoding="utf-8"))
    assert versions["minimum"] in versions["uji"]
    manifest = (REPO / "plugin" / "plugin.yaml").read_text(encoding="utf-8")
    assert f'requires_hermes: ">={versions["minimum"].lstrip("v")}"' in manifest


def test_plugin_is_mounted_by_the_dashboard(hermes):
    paths = set(hermes.ws.app.openapi()["paths"])
    for route in ("/health", "/auth/verify", "/status", "/sessions", "/cron", "/logs"):
        assert f"{PREFIX}{route}" in paths


def test_compat_touches_resolve_against_hermes(hermes):
    compat = hermes.compat
    assert compat is not None, "hermes_compat.py was not loaded by the dashboard"
    assert {f"{PREFIX}/health", f"{PREFIX}/auth/verify"} <= set(hermes.ws._PUBLIC_API_PATHS)
    token = compat.get_session_token()
    assert token and token == hermes.ws._SESSION_TOKEN
    assert compat.hermes_home().resolve() == hermes.home.resolve()
    # Hermes's own credential route, not the environment fallback.
    from agent.secret_scope import get_secret  # noqa: F401

    assert compat.secret("TELEGRAM_BOT_TOKEN") == hermes.h.BOT_TOKEN


def test_health_is_public(hermes):
    r = hermes.client.get(f"{PREFIX}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["plugin"] == "telegram-app"


def _release(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.lstrip("v").split("+")[0].split(".")[:3])


def test_health_reports_login_path_release_and_features(hermes):
    body = hermes.client.get(f"{PREFIX}/health").json()
    # The token seam (v0.23.0+) is not used; login stays on the public-path set (docs/decisions/0005).
    assert body["auth_mode"] == "legacy-public-paths"
    assert body["hermes_version"] == hermes.ws.app.version
    import cron.jobs as jobs

    caps = body["capabilities"]
    assert caps["cron_cancel"] == hasattr(jobs, "cancel_job_run")
    if _release(hermes.ws.app.version) >= (0, 23, 0):
        # Both features shipped in v0.23.0; a release without them is a regression to look at.
        assert caps == {"cron_cancel": True, "cron_catch_up": True}


def test_other_routes_need_the_dashboard_token(hermes):
    for route in ("/status", "/sessions", "/cron", "/logs"):
        assert hermes.client.get(f"{PREFIX}{route}").status_code == 401, route


def test_login_returns_the_dashboard_token_uncached(hermes):
    init_data = hermes.h.make_init_data(auth_date=int(time.time()))
    r = hermes.client.post(f"{PREFIX}/auth/verify", json={"init_data": init_data})
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    assert r.json()["session_token"] == hermes.ws._SESSION_TOKEN


def test_login_rejects_forged_and_unlisted_users(hermes):
    now = int(time.time())
    forged = hermes.h.make_init_data(auth_date=now, bot_token="999:not-the-bot")
    stranger = hermes.h.make_init_data(auth_date=now, user={"id": 1, "first_name": "Eve"})
    for init_data in (forged, stranger):
        r = hermes.client.post(f"{PREFIX}/auth/verify", json={"init_data": init_data})
        assert r.status_code == 403
        assert "session_token" not in r.text


def test_status(hermes):
    r = hermes.client.get(f"{PREFIX}/status", headers=_auth(hermes))
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("cpu_pct", "mem_pct", "disk_pct", "sessions_count", "cron_count", "uptime_sec"):
        assert key in body


def test_sessions(hermes):
    r = hermes.client.get(f"{PREFIX}/sessions", headers=_auth(hermes))
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["sessions"], list)


def test_cron_create_then_list(hermes):
    headers = _auth(hermes)
    r = hermes.client.post(
        f"{PREFIX}/cron",
        headers=headers,
        json={"prompt": "contract test job", "schedule": "every 1h", "name": "contract-test"},
    )
    assert r.status_code == 200, r.text
    r = hermes.client.get(f"{PREFIX}/cron", headers=headers)
    assert r.status_code == 200, r.text
    jobs = r.json()["jobs"]
    assert any(job.get("name") == "contract-test" for job in jobs), jobs
    assert all(isinstance(job.get("running"), bool) for job in jobs), jobs


def test_cron_stop_and_catch_up(hermes):
    headers = _auth(hermes)
    caps = hermes.client.get(f"{PREFIX}/health").json()["capabilities"]
    r = hermes.client.post(
        f"{PREFIX}/cron",
        headers=headers,
        json={"prompt": "contract stop test", "schedule": "every 1h", "name": "contract-stop", "catch_up": False},
    )
    assert r.status_code == 200, r.text
    job = r.json()["job"]
    if caps["cron_catch_up"]:
        assert r.json()["warnings"] == [] and job.get("catch_up") is False, job
    else:
        assert r.json()["warnings"] == ["catch_up_unsupported"]

    r = hermes.client.patch(f"{PREFIX}/cron/{job['id']}", headers=headers, json={"catch_up": None})
    assert r.status_code == 200, r.text

    r = hermes.client.post(f"{PREFIX}/cron/{job['id']}/cancel", headers=headers)
    if caps["cron_cancel"]:
        # Nothing is in flight in a fresh HERMES_HOME: a real call that stops nothing.
        assert r.status_code == 200, r.text
        assert r.json()["action"] == "idle"
        assert hermes.client.post(f"{PREFIX}/cron/does-not-exist/cancel", headers=headers).status_code == 404
    else:
        assert r.status_code == 501 and r.json()["detail"]["code"] == "unsupported"
    assert hermes.client.post(f"{PREFIX}/cron/{job['id']}/cancel").status_code == 401


def test_logs_read_from_the_hermes_home(hermes):
    r = hermes.client.get(f"{PREFIX}/logs", params={"file": "agent"}, headers=_auth(hermes))
    assert r.status_code == 200, r.text
    assert "contract-test: marker line" in json.dumps(r.json())
