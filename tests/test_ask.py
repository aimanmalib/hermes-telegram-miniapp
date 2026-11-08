"""Ask Hermes: a one-shot agent cron job delivered to an admin's Telegram chat, within configured limits."""

from __future__ import annotations

import sys
import types
from datetime import datetime

import pytest

from conftest import OWNER_ID, PREFIX


@pytest.fixture
def cron(monkeypatch):
    """A fake ``cron.jobs`` that stores what ``create_job`` was given."""
    store: list = []
    jobs = types.ModuleType("cron.jobs")

    def create_job(prompt, schedule, name=None, **kw):
        job = {"id": f"j{len(store)}", "prompt": prompt, "schedule": schedule, "name": name,
               "enabled": True, "state": "scheduled", **kw}
        store.append(job)
        return job

    jobs.create_job = create_job
    jobs.list_jobs = lambda include_disabled=False: list(store)
    pkg = types.ModuleType("cron")
    pkg.jobs = jobs
    monkeypatch.setitem(sys.modules, "cron", pkg)
    monkeypatch.setitem(sys.modules, "cron.jobs", jobs)
    return store


def test_ask_creates_a_one_shot_agent_job_for_the_first_admin(plugin, cron):
    r = plugin.client.post(f"{PREFIX}/ask", json={"prompt": "  How full is the disk?  "})
    assert r.status_code == 200, r.text
    (job,) = cron
    assert job["prompt"] == "How full is the disk?"
    assert job["repeat"] == 1
    assert job["deliver"] == f"telegram:{OWNER_ID}"
    assert job["name"] == "Ask: How full is the disk?"
    assert datetime.fromisoformat(job["schedule"]).tzinfo is not None
    # Agent prompt only: nothing that runs commands or picks a model.
    assert not {"script", "workdir", "no_agent", "model", "provider", "enabled_toolsets"} & job.keys()
    assert r.json()["job"]["id"] == "j0"


def test_ask_names_long_prompts_short(plugin, cron):
    plugin.client.post(f"{PREFIX}/ask", json={"prompt": "word " * 40})
    name = cron[0]["name"]
    assert name.startswith("Ask: word") and name.endswith("…") and len(name) <= len("Ask: ") + 48


@pytest.mark.parametrize("extra", ["script", "workdir", "model", "provider", "enabled_toolsets", "deliver", "schedule"])
def test_ask_refuses_fields_beyond_the_prompt(plugin, cron, extra):
    r = plugin.client.post(f"{PREFIX}/ask", json={"prompt": "hi", extra: "x"})
    assert r.status_code == 422
    assert cron == []


def test_ask_length_limit_comes_from_the_plugin_setting(plugin, cron):
    assert plugin.client.post(f"{PREFIX}/ask", json={"prompt": "x" * 2000}).status_code == 200
    cron.clear()
    r = plugin.client.post(f"{PREFIX}/ask", json={"prompt": "x" * 2001})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "too_long"
    plugin.config["ask_max_chars"] = 10
    r = plugin.client.post(f"{PREFIX}/ask", json={"prompt": "x" * 11})
    assert r.json()["detail"] == {"code": "too_long", "message": "Questions are limited to 10 characters", "limit": 10}
    assert plugin.client.post(f"{PREFIX}/ask", json={"prompt": "   "}).status_code == 422
    assert cron == []


@pytest.mark.parametrize("bad", [0, -5, 999_999, "lots", True, None])
def test_ask_bad_length_setting_falls_back_to_the_default(plugin, cron, bad):
    plugin.config["ask_max_chars"] = bad
    assert plugin.client.post(f"{PREFIX}/ask", json={"prompt": "x" * 2000}).status_code == 200
    assert plugin.client.post(f"{PREFIX}/ask", json={"prompt": "x" * 2001}).status_code == 422


def test_ask_answers_only_go_to_admins(plugin, cron, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "1002")  # may chat with the bot, is not an admin
    r = plugin.client.post(f"{PREFIX}/ask", json={"prompt": "hi", "chat_id": 1002})
    assert r.status_code == 403
    plugin.config["admins"] = [1003]
    r = plugin.client.post(f"{PREFIX}/ask", json={"prompt": "hi", "chat_id": 1003})
    assert r.status_code == 200 and cron[0]["deliver"] == "telegram:1003"
    monkeypatch.delenv("TELEGRAM_OWNER_ID")
    plugin.config["admins"] = []
    assert plugin.client.post(f"{PREFIX}/ask", json={"prompt": "hi"}).status_code == 400
    assert len(cron) == 1


def test_one_ask_at_a_time_by_default(plugin, cron):
    assert plugin.client.post(f"{PREFIX}/ask", json={"prompt": "first"}).status_code == 200
    r = plugin.client.post(f"{PREFIX}/ask", json={"prompt": "second"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "busy"
    # Hermes marks the one-shot job completed once it has run.
    cron[0].update(state="completed", enabled=False)
    assert plugin.client.post(f"{PREFIX}/ask", json={"prompt": "second"}).status_code == 200


def test_running_ask_counts_and_other_jobs_do_not(plugin, cron):
    cron.append({"id": "daily", "name": "Daily digest", "enabled": True, "state": "scheduled"})
    cron.append({"id": "old", "name": "Ask: old", "enabled": False, "state": "completed", "live_execution": {"id": "e"}})
    r = plugin.client.post(f"{PREFIX}/ask", json={"prompt": "hi"})
    assert r.status_code == 409  # the completed-looking Ask still has a run in flight
    cron[1]["live_execution"] = None
    assert plugin.client.post(f"{PREFIX}/ask", json={"prompt": "hi"}).status_code == 200


def test_pending_limit_comes_from_the_plugin_setting(plugin, cron):
    plugin.config["ask_max_pending"] = 2
    for prompt in ("a", "b"):
        assert plugin.client.post(f"{PREFIX}/ask", json={"prompt": prompt}).status_code == 200
    r = plugin.client.post(f"{PREFIX}/ask", json={"prompt": "c"})
    assert r.status_code == 409 and r.json()["detail"]["limit"] == 2


def test_hermes_refusal_is_a_bad_request(plugin, cron):
    def refuse(**kw):
        raise ValueError("schedule is in the past")

    sys.modules["cron.jobs"].create_job = refuse
    r = plugin.client.post(f"{PREFIX}/ask", json={"prompt": "hi"})
    assert r.status_code == 400 and "past" in r.text
