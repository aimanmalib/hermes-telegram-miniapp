"""HTTP behaviour of plugin_api.py with a stand-in for the Hermes dashboard module."""

from __future__ import annotations

import sys
import time
import types

from conftest import OWNER_ID, PREFIX, SESSION_TOKEN, make_init_data


def _login(client, init_data):
    return client.post(f"{PREFIX}/auth/verify", json={"init_data": init_data})


def test_login_route_is_a_token_route_and_nothing_is_made_public(plugin):
    assert plugin.token_auth.routes == {f"{PREFIX}/auth/verify"}
    assert not hasattr(plugin.ws, "_PUBLIC_API_PATHS")  # never created or rebound
    assert [p.name for p in plugin.da.providers] == ["telegram-app-initdata"]


def _provider(plugin):
    return plugin.da.providers[0]


def test_provider_vouches_for_valid_owner_init_data(plugin):
    principal = _provider(plugin).verify_token(token=make_init_data(auth_date=int(time.time())))
    assert principal.principal == f"telegram:{OWNER_ID}"
    assert principal.provider == "telegram-app-initdata"
    assert principal.scopes == ("telegram-app",)


def test_provider_ignores_other_bearers(plugin):
    p = _provider(plugin)
    assert p.verify_token(token=SESSION_TOKEN) is None  # not initData: other providers decide
    assert p.verify_token(token="") is None
    assert p.verify_token(token="hash=" + "a" * 64) is None


def test_provider_rejects_stale_forged_or_stranger_init_data(plugin):
    p = _provider(plugin)
    assert p.verify_token(token=make_init_data(auth_date=int(time.time()) - 86400)) is None
    assert p.verify_token(token=make_init_data(auth_date=int(time.time()), bot_token="1:other")) is None
    stranger = {"id": 42, "first_name": "X"}
    assert p.verify_token(token=make_init_data(auth_date=int(time.time()), user=stranger)) is None


def test_provider_unconfigured_is_a_provider_error_not_a_refusal(plugin, monkeypatch):
    # Hermes answers ProviderError with 503, so "not configured" is told apart from "not allowed".
    import pytest

    monkeypatch.delenv("TELEGRAM_OWNER_ID")
    with pytest.raises(plugin.da.ProviderError):
        _provider(plugin).verify_token(token=make_init_data(auth_date=int(time.time())))


def test_health_reports_manifest_version(plugin):
    import json
    from conftest import PLUGIN_DIR

    version = json.loads((PLUGIN_DIR / "manifest.json").read_text())["version"]
    body = plugin.client.get(f"{PREFIX}/health").json()
    assert body["ok"] is True and body["version"] == version


def test_valid_login_returns_session_token(plugin):
    r = _login(plugin.client, make_init_data(auth_date=int(time.time())))
    assert r.status_code == 200
    assert r.json()["session_token"] == SESSION_TOKEN
    assert r.json()["user"]["id"] == OWNER_ID
    assert r.headers["cache-control"] == "no-store"


def test_session_token_read_at_request_time(plugin):
    plugin.ws._SESSION_TOKEN = "rotated"
    r = _login(plugin.client, make_init_data(auth_date=int(time.time())))
    assert r.json()["session_token"] == "rotated"


def test_invalid_login_is_generic_403(plugin):
    stale = make_init_data(auth_date=int(time.time()) - 7200)
    other = make_init_data(auth_date=int(time.time()), user={"id": 1})
    for payload in (stale, other, "garbage"):
        r = _login(plugin.client, payload)
        assert r.status_code == 403
        assert r.json() == {"detail": "Invalid Telegram initData"}
        assert SESSION_TOKEN not in r.text


def test_freshness_window_configurable(plugin, monkeypatch):
    monkeypatch.setenv("TELEGRAM_INITDATA_MAX_AGE", "86400")
    r = _login(plugin.client, make_init_data(auth_date=int(time.time()) - 7200))
    assert r.status_code == 200


def test_allowed_users_union_with_owner(plugin, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "1001,1002")
    r = _login(plugin.client, make_init_data(auth_date=int(time.time()), user={"id": 1002}))
    assert r.status_code == 200


def test_unconfigured_allowlist_refuses(plugin, monkeypatch):
    monkeypatch.delenv("TELEGRAM_OWNER_ID")
    r = _login(plugin.client, make_init_data(auth_date=int(time.time())))
    assert r.status_code == 503
    assert SESSION_TOKEN not in r.text


def test_rate_limited_after_repeated_failures(plugin):
    for _ in range(10):
        assert _login(plugin.client, "garbage").status_code == 403
    r = _login(plugin.client, make_init_data(auth_date=int(time.time())))
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0


def test_oversized_and_missing_body(plugin):
    assert _login(plugin.client, "a=" + "x" * 9000).status_code == 422
    assert plugin.client.post(f"{PREFIX}/auth/verify", json={}).status_code == 422
    assert plugin.client.post(f"{PREFIX}/auth/verify", content=b"{not json").status_code == 422


def test_get_verify_removed(plugin):
    assert plugin.client.get(f"{PREFIX}/auth/verify").status_code == 405


def test_initdata_never_logged(plugin, caplog):
    secret_marker = "zz-unique-marker-zz"
    payload = make_init_data(auth_date=int(time.time()), user={"id": 9, "first_name": secret_marker})
    with caplog.at_level("DEBUG"):
        _login(plugin.client, payload)
    assert secret_marker not in caplog.text
    assert "AAE-known-answer-test-token" not in caplog.text


def test_command_refuses_non_allowlisted_chat(plugin):
    r = plugin.client.post(f"{PREFIX}/command", json={"text": "hi", "chat_id": 999})
    assert r.status_code == 403


def test_command_rejects_empty_and_huge_text(plugin):
    assert plugin.client.post(f"{PREFIX}/command", json={"text": ""}).status_code == 422
    assert plugin.client.post(f"{PREFIX}/command", json={"text": "x" * 5000}).status_code == 422


def test_cron_action_unknown_job_is_404(plugin, monkeypatch):
    jobs = types.ModuleType("cron.jobs")
    jobs.pause_job = lambda job_id: None
    jobs.trigger_job = lambda job_id: (_ for _ in ()).throw(ValueError("terminal"))
    cron = types.ModuleType("cron")
    cron.jobs = jobs
    monkeypatch.setitem(sys.modules, "cron", cron)
    monkeypatch.setitem(sys.modules, "cron.jobs", jobs)
    assert plugin.client.post(f"{PREFIX}/cron/nope/pause").status_code == 404
    assert plugin.client.post(f"{PREFIX}/cron/x/trigger").status_code == 400


def test_logs_rejects_unknown_file(plugin):
    assert plugin.client.get(f"{PREFIX}/logs?file=../../etc/passwd").status_code == 400


def test_skill_path_traversal_refused(plugin):
    assert plugin.client.get(f"{PREFIX}/skills/../../.env").status_code == 404


def test_cron_create_refuses_script_jobs(plugin, monkeypatch):
    created = []
    jobs = types.ModuleType("cron.jobs")
    jobs.create_job = lambda **kw: created.append(kw) or {"id": "new", **kw}
    cron = types.ModuleType("cron")
    cron.jobs = jobs
    monkeypatch.setitem(sys.modules, "cron", cron)
    monkeypatch.setitem(sys.modules, "cron.jobs", jobs)
    bad = {"schedule": "1h", "prompt": "x", "no_agent": True, "script": "rm -rf ~"}
    assert plugin.client.post(f"{PREFIX}/cron", json=bad).status_code == 422
    assert plugin.client.post(f"{PREFIX}/cron", json={"schedule": "1h", "prompt": "x", "workdir": "/"}).status_code == 422
    assert plugin.client.post(f"{PREFIX}/cron", json={"schedule": "1h"}).status_code == 422
    ok = plugin.client.post(f"{PREFIX}/cron", json={"schedule": "1h", "prompt": "hi", "deliver": "telegram"})
    assert ok.status_code == 200
    assert created == [{"schedule": "1h", "prompt": "hi", "deliver": "telegram"}]


def test_login_route_demands_our_scope_where_hermes_supports_it(plugin, monkeypatch):
    # A seam with per-route scopes (NousResearch/hermes-agent#146551) gets ours; the probe reads the signature.
    scoped = {}

    def register_token_route(path, *, scope=None):
        scoped[path] = scope

    monkeypatch.setattr(plugin.token_auth, "register_token_route", register_token_route)
    compat = sys.modules["hermes_tma_hermes_compat"]
    assert compat.token_route_scopes_supported()
    assert compat.register_token_route(f"{PREFIX}/auth/verify", "telegram-app")
    assert scoped == {f"{PREFIX}/auth/verify": "telegram-app"}


def test_old_seam_gets_the_path_alone(plugin):
    compat = sys.modules["hermes_tma_hermes_compat"]
    assert not compat.token_route_scopes_supported()  # the stub's register is set.add
