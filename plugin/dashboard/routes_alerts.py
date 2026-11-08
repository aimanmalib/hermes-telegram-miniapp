"""Push alerts — settings, status and a manual test."""

from __future__ import annotations

import logging
import sys
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

compat = sys.modules["hermes_tma_hermes_compat"]  # loaded first by plugin_api.py
settings = compat.load_sibling("settings")
router = APIRouter()
_log = logging.getLogger("hermes.plugin.telegram-app")

# Background thread that DMs the first admin about cron failures, error-log
# bursts and daily spend. Decided once, when the dashboard mounts this route:
# ``hermes dashboard`` runs plugin discovery (``register`` binds the plugin
# settings) before it imports the web server, so ``alerts_enabled`` is read here.
try:
    _alerts = compat.load_sibling("alerts")
except Exception as _exc:  # pragma: no cover - defensive
    _alerts = None
    _log.warning("telegram-app: alerts module unavailable: %s", _exc)

if _alerts is not None and settings.alerts_enabled():
    try:
        _alerts.ensure_started()
    except Exception as _exc:
        _log.warning("telegram-app: alerts ensure_started failed: %s", _exc)


class _AlertsSettingsBody(BaseModel):
    cron_failures: Optional[bool] = None
    error_log: Optional[bool] = None
    cost_threshold: Optional[bool] = None
    cost_daily_usd: Optional[float] = None
    error_throttle_sec: Optional[int] = None
    poll_interval_sec: Optional[int] = None


@router.get("/alerts")
async def alerts_get():
    if _alerts is None:
        raise HTTPException(status_code=503, detail="alerts module not available")
    return _alerts.get_status()


@router.patch("/alerts")
async def alerts_patch(body: _AlertsSettingsBody):
    if _alerts is None:
        raise HTTPException(status_code=503, detail="alerts module not available")
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="no fields to update")
    _alerts.update_settings(patch)
    return _alerts.get_status()


@router.post("/alerts/test")
async def alerts_test():
    if _alerts is None:
        raise HTTPException(status_code=503, detail="alerts module not available")
    return _alerts.trigger_test()
