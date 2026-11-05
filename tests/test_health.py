"""``/health``: how login is reachable, which Hermes is running, and which optional features it has."""

from __future__ import annotations

import sys
import types

from conftest import BOT_TOKEN, PREFIX, SESSION_TOKEN


def _health(plugin) -> dict:
    r = plugin.client.get(f"{PREFIX}/health")
    assert r.status_code == 200
    return r.json()


def _cron_jobs(monkeypatch, **funcs):
    jobs = types.ModuleType("cron.jobs")
    for name, fn in funcs.items():
        setattr(jobs, name, fn)
    cron = types.ModuleType("cron")
    cron.jobs = jobs
    monkeypatch.setitem(sys.modules, "cron", cron)
    monkeypatch.setitem(sys.modules, "cron.jobs", jobs)


def test_auth_mode_is_legacy_public_paths_when_registered(plugin):
    assert _health(plugin)["auth_mode"] == "legacy-public-paths"


def test_auth_mode_unavailable_when_hermes_drops_our_paths(plugin):
    # Read on every request: a Hermes that rebinds the public set without our
    # paths is reported, not hidden behind the value seen at import time.
    plugin.ws._PUBLIC_API_PATHS = frozenset({"/api/status"})
    assert _health(plugin)["auth_mode"] == "unavailable"


def test_auth_mode_unavailable_when_public_set_missing(plugin):
    del plugin.ws._PUBLIC_API_PATHS
    assert _health(plugin)["auth_mode"] == "unavailable"


def test_hermes_version_from_dashboard_app(plugin):
    assert _health(plugin)["hermes_version"] is None  # the stub has no app
    plugin.ws.app = types.SimpleNamespace(version="0.23.0")
    assert _health(plugin)["hermes_version"] == "0.23.0"


def test_capabilities_off_without_cron_module(plugin, monkeypatch):
    monkeypatch.setitem(sys.modules, "cron", None)
    monkeypatch.setitem(sys.modules, "cron.jobs", None)
    assert _health(plugin)["capabilities"] == {"cron_cancel": False, "cron_catch_up": False}


def test_capabilities_follow_cron_functions(plugin, monkeypatch):
    def create_job(prompt, schedule, catch_up=None):
        return {}

    _cron_jobs(monkeypatch, create_job=create_job, cancel_job_run=lambda job_id, reason=None: {})
    assert _health(plugin)["capabilities"] == {"cron_cancel": True, "cron_catch_up": True}


def test_capabilities_older_hermes(plugin, monkeypatch):
    def create_job(prompt, schedule):
        return {}

    _cron_jobs(monkeypatch, create_job=create_job)
    assert _health(plugin)["capabilities"] == {"cron_cancel": False, "cron_catch_up": False}


def test_health_carries_no_secrets(plugin):
    text = plugin.client.get(f"{PREFIX}/health").text
    assert SESSION_TOKEN not in text and BOT_TOKEN not in text
