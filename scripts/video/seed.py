#!/usr/bin/env python3
"""Give the demo rig real data: agent sessions and cron jobs, made by Hermes itself.

Run after ``scripts/video/rig.sh up``. Nothing here is mocked:

* each prompt in ``seed.json`` "sessions" is one ``hermes -z`` turn against the configured model;
* each "cron" entry is created through the plugin's own ``POST /cron`` (what the Mini App calls),
  entries with ``run_now`` are triggered and ``hermes cron tick`` runs them once.

Then it reads the result back through the plugin API and writes a summary JSON
(``RIG_SUMMARY``, default ``$OUT_DIR/rig.json``) that the recording step checks.

Environment: ``HERMES_BIN``, ``HERMES_HOME``, ``OUT_DIR`` (as for rig.sh), optional
``DASHBOARD_PORT`` (default 9119), ``SEED_FILE`` (default: seed.json next to this file),
``SEED_SKIP_SESSIONS=1`` to only (re)create cron jobs. Re-running does not duplicate cron jobs
(matched by name); sessions are added again.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
API_PREFIX = "/api/plugins/telegram-app"
TURN_TIMEOUT = int(os.environ.get("SEED_TURN_TIMEOUT", "300"))


def env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        sys.exit(f"seed: {name} is not set (see scripts/video/README.md)")
    return value


class Plugin:
    def __init__(self, port: str, token: str) -> None:
        self.base = f"http://127.0.0.1:{port}{API_PREFIX}"
        self.token = token

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("X-Hermes-Session-Token", self.token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            sys.exit(f"seed: {method} {path} -> HTTP {exc.code}: {exc.read()[:300]!r}")


def hermes(args: list[str], home: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [env("HERMES_BIN"), *args],
        env={**os.environ, "HERMES_HOME": home},
        cwd=env("OUT_DIR"),
        capture_output=True,
        text=True,
        timeout=TURN_TIMEOUT,
    )


def seed_sessions(prompts: list[str], home: str) -> None:
    for i, prompt in enumerate(prompts, 1):
        started = time.monotonic()
        res = hermes(["-z", prompt], home)
        status = "ok" if res.returncode == 0 else f"exit {res.returncode}"
        print(f"seed: session {i}/{len(prompts)} {status} in {time.monotonic() - started:.0f}s")


def seed_cron(specs: list[dict], api: Plugin, home: str) -> None:
    existing = {j.get("name"): j for j in api.call("GET", "/cron")["jobs"]}
    to_run = []
    for spec in specs:
        job = existing.get(spec["name"])
        if job is None:
            body = {k: spec[k] for k in ("name", "schedule", "prompt", "deliver", "model") if k in spec}
            job = api.call("POST", "/cron", body)["job"]
            print(f"seed: cron created: {spec['name']}")
        if spec.get("run_now"):
            to_run.append(job["id"])
    for job_id in to_run:
        api.call("POST", f"/cron/{job_id}/trigger")
    if to_run:
        res = hermes(["cron", "tick"], home)
        print(f"seed: cron tick exit {res.returncode}")


def failed(job: dict) -> bool:
    if job.get("last_status") in ("error", "failed"):
        return True
    latest = job.get("latest_execution")
    return isinstance(latest, dict) and latest.get("status") in ("error", "failed")


def summary(api: Plugin) -> dict:
    health = api.call("GET", "/health")
    sessions = api.call("GET", "/sessions")
    items = sessions.get("sessions", sessions if isinstance(sessions, list) else [])
    jobs = api.call("GET", "/cron")["jobs"]
    return {
        "hermes_version": health.get("hermes_version"),
        "plugin_version": health.get("version"),
        # live: the numbers below come from a running Hermes, not from the demo build.
        "live": bool(health.get("ok")) and bool(health.get("hermes_version")) and len(items) > 0,
        "sessions": len(items),
        "cron": len(jobs),
        "cron_failed": sum(1 for j in jobs if failed(j)),
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main() -> None:
    home = env("HERMES_HOME")
    out_dir = Path(env("OUT_DIR"))
    seed = json.loads(Path(os.environ.get("SEED_FILE", HERE / "seed.json")).read_text(encoding="utf-8"))
    api = Plugin(os.environ.get("DASHBOARD_PORT", "9119"), (out_dir / "dashboard-token").read_text().strip())
    api.call("GET", "/health")  # fail early when the rig is down

    if os.environ.get("SEED_SKIP_SESSIONS") != "1":
        seed_sessions(seed["sessions"], home)
    seed_cron(seed["cron"], api, home)

    result = summary(api)
    target = Path(os.environ.get("RIG_SUMMARY", out_dir / "rig.json"))
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
