"""Cron routes: Stop (cancel), per-job catch_up and the running flag, with and without Hermes support."""

from __future__ import annotations

import sys
import types
from typing import Optional

import pytest

from conftest import PREFIX


def _install(monkeypatch, *, modern: bool):
    """A fake ``cron.jobs``: ``modern`` mimics v0.23.0 (cancel + catch_up), otherwise v0.22.4."""
    store = {"j1": {"id": "j1", "name": "daily"}}
    calls: dict = {"create": [], "update": [], "cancel": []}
    jobs = types.ModuleType("cron.jobs")

    def get_job(job_id):
        return store.get(job_id)

    def update_job(job_id, updates):
        calls["update"].append((job_id, dict(updates)))
        return {**store[job_id], **updates} if job_id in store else None

    if modern:
        def create_job(prompt, schedule, name=None, catch_up: Optional[bool] = None, **kw):
            calls["create"].append({"prompt": prompt, "schedule": schedule, "catch_up": catch_up, **kw})
            return {"id": "new", "catch_up": catch_up}

        def cancel_job_run(job_id, reason=None):
            calls["cancel"].append((job_id, reason))
            return {"success": True, "cancelled": job_id == "j1", "execution_id": None}

        jobs.cancel_job_run = cancel_job_run
    else:
        def create_job(prompt, schedule, name=None, **kw):
            calls["create"].append({"prompt": prompt, "schedule": schedule, **kw})
            return {"id": "new"}

    jobs.get_job, jobs.update_job, jobs.create_job = get_job, update_job, create_job
    cron = types.ModuleType("cron")
    cron.jobs = jobs
    monkeypatch.setitem(sys.modules, "cron", cron)
    monkeypatch.setitem(sys.modules, "cron.jobs", jobs)
    return jobs, calls


def test_cancel_stops_a_running_job(plugin, monkeypatch):
    _, calls = _install(monkeypatch, modern=True)
    r = plugin.client.post(f"{PREFIX}/cron/j1/cancel")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "id": "j1", "action": "cancelled", "cancelled": True}
    assert calls["cancel"][0][0] == "j1"


def test_cancel_with_nothing_in_flight_is_idle(plugin, monkeypatch):
    jobs, _ = _install(monkeypatch, modern=True)
    jobs.get_job = lambda job_id: {"id": job_id}
    r = plugin.client.post(f"{PREFIX}/cron/other/cancel")
    assert r.status_code == 200
    assert r.json()["action"] == "idle" and r.json()["cancelled"] is False


def test_cancel_unknown_job_is_404(plugin, monkeypatch):
    _, calls = _install(monkeypatch, modern=True)
    assert plugin.client.post(f"{PREFIX}/cron/nope/cancel").status_code == 404
    assert calls["cancel"] == []


def test_cancel_unsupported_is_501_with_code(plugin, monkeypatch):
    _install(monkeypatch, modern=False)
    r = plugin.client.post(f"{PREFIX}/cron/j1/cancel")
    assert r.status_code == 501
    assert r.json()["detail"]["code"] == "unsupported"


def test_cancel_hermes_error_is_500(plugin, monkeypatch):
    jobs, _ = _install(monkeypatch, modern=True)

    def boom(job_id, reason=None):
        raise RuntimeError("db locked")

    jobs.cancel_job_run = boom
    assert plugin.client.post(f"{PREFIX}/cron/j1/cancel").status_code == 500


@pytest.mark.parametrize("value", [True, False])
def test_create_passes_catch_up_when_supported(plugin, monkeypatch, value):
    _, calls = _install(monkeypatch, modern=True)
    r = plugin.client.post(f"{PREFIX}/cron", json={"schedule": "1h", "prompt": "hi", "catch_up": value})
    assert r.status_code == 200, r.text
    assert calls["create"][0]["catch_up"] is value
    assert r.json()["warnings"] == []


def test_create_drops_catch_up_with_warning_when_unsupported(plugin, monkeypatch):
    _, calls = _install(monkeypatch, modern=False)
    r = plugin.client.post(f"{PREFIX}/cron", json={"schedule": "1h", "prompt": "hi", "catch_up": True})
    assert r.status_code == 200, r.text
    assert "catch_up" not in calls["create"][0]
    assert r.json()["warnings"] == ["catch_up_unsupported"]


def test_create_rejects_non_boolean_catch_up(plugin, monkeypatch):
    _install(monkeypatch, modern=True)
    r = plugin.client.post(f"{PREFIX}/cron", json={"schedule": "1h", "prompt": "hi", "catch_up": "sometimes"})
    assert r.status_code == 422


def test_patch_catch_up_null_resets_to_default(plugin, monkeypatch):
    _, calls = _install(monkeypatch, modern=True)
    r = plugin.client.patch(f"{PREFIX}/cron/j1", json={"catch_up": None, "name": None})
    assert r.status_code == 200, r.text
    assert calls["update"] == [("j1", {"catch_up": None})]


def test_patch_only_catch_up_on_old_hermes_returns_job_unchanged(plugin, monkeypatch):
    _, calls = _install(monkeypatch, modern=False)
    r = plugin.client.patch(f"{PREFIX}/cron/j1", json={"catch_up": False})
    assert r.status_code == 200, r.text
    assert calls["update"] == []
    assert r.json()["job"]["id"] == "j1" and r.json()["warnings"] == ["catch_up_unsupported"]
    assert plugin.client.patch(f"{PREFIX}/cron/nope", json={"catch_up": False}).status_code == 404


def test_patch_with_other_fields_on_old_hermes_still_updates(plugin, monkeypatch):
    _, calls = _install(monkeypatch, modern=False)
    r = plugin.client.patch(f"{PREFIX}/cron/j1", json={"catch_up": True, "name": "renamed"})
    assert r.status_code == 200
    assert calls["update"] == [("j1", {"name": "renamed"})]


@pytest.mark.parametrize(
    "job, running",
    [
        ({"id": "a", "live_execution": {"status": "running"}}, True),
        ({"id": "b", "live_execution": None, "latest_execution": {"status": "running"}}, False),
        ({"id": "c", "latest_execution": {"status": "claimed"}}, True),
        ({"id": "d", "latest_execution": {"status": "succeeded"}}, False),
        ({"id": "e", "latest_execution": None}, False),
        ({"id": "f"}, False),
    ],
)
def test_list_marks_running_jobs(plugin, monkeypatch, job, running):
    jobs, _ = _install(monkeypatch, modern=True)
    jobs.list_jobs = lambda include_disabled=False: [dict(job)]
    r = plugin.client.get(f"{PREFIX}/cron")
    assert r.status_code == 200
    assert r.json()["jobs"][0]["running"] is running
