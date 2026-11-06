"""Module layout: Hermes internals are touched in one place, and every route stays mounted."""

from __future__ import annotations

import re

from fastapi import FastAPI

from conftest import PLUGIN_DIR

HERMES_INTERNALS = ("dashboard_auth", "_PUBLIC_API_PATHS", "_SESSION_TOKEN", "get_secret", "get_hermes_home")

EXPECTED_ROUTES = {
    ("GET", "/health"), ("POST", "/auth/verify"),
    ("GET", "/status"), ("GET", "/usage"),
    ("GET", "/sessions"), ("GET", "/sessions/{session_id}/messages"),
    ("GET", "/cron"), ("POST", "/cron"), ("PATCH", "/cron/{job_id}"), ("DELETE", "/cron/{job_id}"),
    ("POST", "/cron/{job_id}/pause"), ("POST", "/cron/{job_id}/resume"), ("POST", "/cron/{job_id}/trigger"),
    ("POST", "/cron/{job_id}/cancel"),
    ("GET", "/skills"), ("GET", "/skills/{skill_id}"), ("GET", "/memory"),
    ("GET", "/logs"), ("POST", "/command"),
    ("GET", "/alerts"), ("PATCH", "/alerts"), ("POST", "/alerts/test"),
}


def test_hermes_internals_only_in_compat_module():
    offenders = []
    for path in sorted(PLUGIN_DIR.glob("*.py")):
        if path.name == "hermes_compat.py":
            continue
        text = path.read_text("utf-8")
        offenders += [f"{path.name}: {name}" for name in HERMES_INTERNALS if re.search(rf"\b{name}\b", text)]
    assert offenders == []


def test_every_route_is_mounted(plugin):
    app = FastAPI()
    app.include_router(plugin.mod.router)
    mounted = {(m.upper(), p) for p, ops in app.openapi()["paths"].items() for m in ops}
    assert mounted == EXPECTED_ROUTES
