"""The demo rig's summary helpers (scripts/video/seed.py) — no Hermes needed."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SEED = Path(__file__).resolve().parent.parent / "scripts" / "video" / "seed.py"


@pytest.fixture(scope="module")
def seed():
    spec = importlib.util.spec_from_file_location("video_seed", SEED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeApi:
    def __init__(self, jobs):
        self.jobs = jobs

    def call(self, method, path, body=None):
        return {
            "/health": {"ok": True, "hermes_version": "0.23.0", "version": "0.6.0"},
            "/sessions": {"sessions": [{"id": "a"}, {"id": "b"}]},
            "/cron": {"jobs": self.jobs},
        }[path]


def test_summary_counts_failed_jobs_from_either_field(seed):
    jobs = [{"last_status": "ok"}, {"last_status": "error"}, {"latest_execution": {"status": "failed"}}]
    result = seed.summary(FakeApi(jobs))
    assert result["live"] is True
    assert (result["sessions"], result["cron"], result["cron_failed"]) == (2, 3, 2)


def test_aliases_copy_keys_and_keep_originals(seed):
    out = seed.with_aliases({"cron_failed": 1, "cron": 3}, " cron_failed=failed_jobs , cron=jobs ")
    assert out == {"cron_failed": 1, "cron": 3, "failed_jobs": 1, "jobs": 3}


def test_no_aliases_is_identity(seed):
    assert seed.with_aliases({"cron": 3}, "") == {"cron": 3}


@pytest.mark.parametrize("spec", ["cron_failed", "missing=x", "=x", "cron="])
def test_bad_alias_spec_exits(seed, spec):
    with pytest.raises(SystemExit):
        seed.with_aliases({"cron": 3, "cron_failed": 1}, spec)
