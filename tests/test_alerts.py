"""Alert watcher logic, with Hermes modules and Telegram replaced by fakes."""

from __future__ import annotations

import sys
import time
import types

import pytest

from conftest import load_module


@pytest.fixture
def alerts(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delitem(sys.modules, "hermes_constants", raising=False)
    mod = load_module("alerts", "tma_test_alerts")
    sent: list = []
    monkeypatch.setattr(mod, "_send_telegram", lambda text: sent.append(text) or True)
    mod.sent = sent
    return mod


def _fake_cron(monkeypatch, jobs):
    m = types.ModuleType("cron.jobs")
    m.list_jobs = lambda include_disabled=False: list(jobs)
    pkg = types.ModuleType("cron")
    pkg.jobs = m
    monkeypatch.setitem(sys.modules, "cron", pkg)
    monkeypatch.setitem(sys.modules, "cron.jobs", m)


def test_run_timestamp_handles_current_and_legacy_shapes(alerts):
    assert alerts.run_timestamp({"last_run_at": "2026-10-22T09:00:00+00:00"}) == 1792659600.0
    assert alerts.run_timestamp({"last_run_at": "2026-10-22T09:00:00Z"}) == 1792659600.0
    assert alerts.run_timestamp({"last_run": 1700000000}) == 1700000000.0
    assert alerts.run_timestamp({"last_run_at": "not a date"}) == 0.0
    assert alerts.run_timestamp({}) == 0.0


@pytest.mark.parametrize(
    "status,failed",
    [("error", True), ("delivery_failed", True), ("blocked_config", True),
     ("ok", False), (None, False), ("", False)],
)
def test_is_failed_status(alerts, status, failed):
    assert alerts.is_failed_status(status) is failed


def test_schedule_label_prefers_display(alerts):
    assert alerts.schedule_label({"schedule_display": "every 30m"}) == "every 30m"
    assert alerts.schedule_label({"schedule": {"kind": "cron", "expr": "0 9 * * *"}}) == "0 9 * * *"
    assert alerts.schedule_label({"schedule": "1h"}) == "1h"


def test_cron_failure_alerts_once_per_run(alerts, monkeypatch):
    job = {"id": "j1", "name": "Briefing", "last_status": "error",
           "last_run_at": "2026-10-22T09:00:00+00:00", "last_error": "boom",
           "schedule": {"kind": "cron", "expr": "0 9 * * *"}, "schedule_display": "0 9 * * *"}
    _fake_cron(monkeypatch, [job, {"id": "j2", "last_status": "ok", "last_run_at": "2026-10-22T09:00:00Z"}])
    state = {"cron_last_alert_per_job": {}}
    alerts._check_cron_failures(state)
    alerts._check_cron_failures(state)
    assert len(alerts.sent) == 1
    assert "Briefing" in alerts.sent[0] and "0 9 * * *" in alerts.sent[0] and "boom" in alerts.sent[0]
    job["last_run_at"] = "2026-10-22T10:00:00+00:00"
    alerts._check_cron_failures(state)
    assert len(alerts.sent) == 2


def test_cost_threshold_fires_once_per_day(alerts, monkeypatch):
    now = time.time()

    class FakeDB:
        def list_sessions_rich(self, **kw):
            return [{"last_active": now, "estimated_cost_usd": 3.0},
                    {"last_active": now, "estimated_cost_usd": 2.5},
                    {"last_active": now - 10 * 86400, "estimated_cost_usd": 100.0}]

    hs = types.ModuleType("hermes_state")
    hs.SessionDB = FakeDB
    monkeypatch.setitem(sys.modules, "hermes_state", hs)
    state: dict = {}
    alerts._check_cost_threshold(state, {"cost_daily_usd": 5.0})
    alerts._check_cost_threshold(state, {"cost_daily_usd": 5.0})
    assert len(alerts.sent) == 1 and "$5.50" in alerts.sent[0]


def test_cost_below_threshold_is_quiet(alerts, monkeypatch):
    class FakeDB:
        def list_sessions_rich(self, **kw):
            return [{"last_active": time.time(), "estimated_cost_usd": 1.0}]

    hs = types.ModuleType("hermes_state")
    hs.SessionDB = FakeDB
    monkeypatch.setitem(sys.modules, "hermes_state", hs)
    alerts._check_cost_threshold({}, {"cost_daily_usd": 5.0})
    assert alerts.sent == []


def test_error_log_alert_and_throttle(alerts, tmp_path):
    log = tmp_path / "logs" / "errors.log"
    log.parent.mkdir(parents=True)
    log.write_text("2026-10-22 INFO fine\n")
    state = {"errors_last_size": log.stat().st_size}
    settings = {"error_throttle_sec": 300}
    with log.open("a") as fh:
        fh.write("2026-10-22 ERROR first failure\n2026-10-22 ERROR second failure\n")
    alerts._check_error_log(state, settings)
    assert len(alerts.sent) == 1
    assert "second failure" in alerts.sent[0] and "+1 more" in alerts.sent[0]
    with log.open("a") as fh:
        fh.write("2026-10-22 ERROR third failure\n")
    alerts._check_error_log(state, settings)
    assert len(alerts.sent) == 1  # throttled


def test_update_settings_clamps_and_ignores_unknown(alerts):
    out = alerts.update_settings({"poll_interval_sec": 1, "cost_daily_usd": -4,
                                  "error_log": 1, "evil": "x"})
    assert out["poll_interval_sec"] == 15
    assert out["cost_daily_usd"] == 0.0
    assert out["error_log"] is True
    assert "evil" not in out
    assert alerts.get_settings()["poll_interval_sec"] == 15


def test_bot_chat_uses_owner_then_allowed(alerts, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:x")
    monkeypatch.delenv("TELEGRAM_OWNER_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "abc, 77")
    assert alerts._bot_token_and_chat() == ("1:x", 77)
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "55")
    assert alerts._bot_token_and_chat() == ("1:x", 55)


def test_no_files_written_at_import(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    load_module("alerts", "tma_test_alerts_import")
    assert not (tmp_path / "home").exists()
