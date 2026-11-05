"""Cron jobs: list, create, edit, delete, pause/resume/trigger/cancel — through ``cron.jobs``.

Optional Hermes features (stop a running job, per-job ``catch_up``) are detected
with ``hermes_compat.capabilities()``, never by version number: on a Hermes
without them, cancel answers 501 ``unsupported`` and ``catch_up`` is dropped with
a warning in the response.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

compat = sys.modules["hermes_tma_hermes_compat"]  # loaded first by plugin_api.py
router = APIRouter()
_log = logging.getLogger("hermes.plugin.telegram-app")

# Execution states Hermes uses for a run that has not finished yet (cron/executions.py).
_LIVE_STATUSES = frozenset({"claimed", "running"})
CATCH_UP_UNSUPPORTED = "catch_up_unsupported"


def _is_running(job: Dict[str, Any]) -> bool:
    """True while the job has a run in flight.

    v0.23.0+ lists the live run as ``live_execution`` (owner checked by Hermes).
    Older releases only have ``latest_execution``; its status is the best signal there.
    """
    if "live_execution" in job:
        return bool(job.get("live_execution"))
    latest = job.get("latest_execution")
    return isinstance(latest, dict) and latest.get("status") in _LIVE_STATUSES


@router.get("/cron")
async def cron_list():
    try:
        from cron.jobs import list_jobs  # type: ignore
        # include_disabled=True so the UI can show paused jobs and resume them.
        jobs = list_jobs(include_disabled=True)
    except Exception as exc:
        _log.exception("cron list failed")
        raise HTTPException(status_code=500, detail=str(exc))
    for job in jobs:
        if isinstance(job, dict):
            job["running"] = _is_running(job)
    return {"jobs": jobs}


def _drop_unsupported_catch_up(fields: Dict[str, Any]) -> List[str]:
    """Remove ``catch_up`` when this Hermes cannot store it; return response warnings."""
    if "catch_up" not in fields or compat.capabilities()["cron_catch_up"]:
        return []
    fields.pop("catch_up")
    _log.warning("cron: this Hermes has no per-job catch_up; the setting was ignored")
    return [CATCH_UP_UNSUPPORTED]


class _CronCreateBody(BaseModel):
    # Agent jobs only. Script-only jobs (``no_agent`` / ``script``) and
    # ``workdir`` are deliberately not accepted from the phone: they run
    # arbitrary commands without the agent in the loop, and the Mini App UI
    # never uses them. Unknown fields are rejected rather than ignored.
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(..., min_length=1, max_length=20_000)
    schedule: str = Field(..., min_length=1, max_length=200)
    name: Optional[str] = Field(None, max_length=200)
    deliver: Optional[str] = None  # "origin" | "local" | "telegram" | ...
    repeat: Optional[int] = None
    skills: Optional[List[str]] = None
    enabled_toolsets: Optional[List[str]] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    catch_up: Optional[bool] = None  # None = Hermes default (cron.catch_up_missed)


@router.post("/cron")
async def cron_create(body: _CronCreateBody):
    """Create an agent cron job via ``cron.jobs.create_job``."""
    try:
        from cron.jobs import create_job  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    fields = body.model_dump(exclude_none=True)
    warnings = _drop_unsupported_catch_up(fields)
    try:
        job = create_job(**fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        _log.exception("cron create failed")
        raise HTTPException(status_code=500, detail=str(exc))
    return {"ok": True, "job": job, "warnings": warnings}


class _CronUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    schedule: Optional[str] = None
    prompt: Optional[str] = None
    deliver: Optional[str] = None
    repeat: Optional[int] = None
    skills: Optional[List[str]] = None
    enabled_toolsets: Optional[List[str]] = None
    catch_up: Optional[bool] = None  # an explicit null resets to the Hermes default


@router.patch("/cron/{job_id}")
async def cron_update(job_id: str, body: _CronUpdateBody):
    try:
        from cron.jobs import update_job  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    sent = body.model_dump(exclude_unset=True)
    # ``catch_up: null`` is meaningful (back to the default); other nulls mean "unchanged".
    updates: Dict[str, Any] = {k: v for k, v in sent.items() if v is not None or k == "catch_up"}
    if not updates:
        raise HTTPException(status_code=400, detail="no fields to update")
    warnings = _drop_unsupported_catch_up(updates)
    try:
        if updates:
            job = update_job(job_id, updates)
        else:  # only catch_up was sent, and this Hermes ignores it
            from cron.jobs import get_job  # type: ignore

            job = get_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        _log.exception("cron update failed")
        raise HTTPException(status_code=500, detail=str(exc))
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job": job, "warnings": warnings}


@router.delete("/cron/{job_id}")
async def cron_delete(job_id: str):
    try:
        from cron.jobs import remove_job  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        ok = remove_job(job_id)
    except Exception as exc:
        _log.exception("cron delete failed")
        raise HTTPException(status_code=500, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "id": job_id, "action": "deleted"}


def _cron_action(job_id: str, fn_name: str, action: str) -> Dict[str, Any]:
    try:
        import cron.jobs as jobs  # type: ignore

        fn = getattr(jobs, fn_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        job = fn(job_id)
    except ValueError as exc:  # e.g. trigger on a terminal job
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        _log.exception("cron %s failed", action)
        raise HTTPException(status_code=500, detail=str(exc))
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "id": job_id, "action": action}


@router.post("/cron/{job_id}/pause")
async def cron_pause(job_id: str):
    return _cron_action(job_id, "pause_job", "paused")


@router.post("/cron/{job_id}/resume")
async def cron_resume(job_id: str):
    return _cron_action(job_id, "resume_job", "resumed")


@router.post("/cron/{job_id}/trigger")
async def cron_trigger(job_id: str):
    return _cron_action(job_id, "trigger_job", "triggered")


@router.post("/cron/{job_id}/cancel")
async def cron_cancel(job_id: str):
    """Stop the job's run in flight (``cron.jobs.cancel_job_run``); its schedule is untouched."""
    if not compat.capabilities()["cron_cancel"]:
        raise HTTPException(
            status_code=501,
            detail={"code": "unsupported", "message": "This Hermes cannot stop a running job"},
        )
    try:
        import cron.jobs as jobs  # type: ignore

        if not jobs.get_job(job_id):
            raise HTTPException(status_code=404, detail="job not found")
        result = jobs.cancel_job_run(job_id, reason="stopped from the Telegram Mini App")
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("cron cancel failed")
        raise HTTPException(status_code=500, detail=str(exc))
    cancelled = bool(isinstance(result, dict) and result.get("cancelled"))
    # "idle": nothing was in flight, so there was nothing to stop.
    return {"ok": True, "id": job_id, "action": "cancelled" if cancelled else "idle", "cancelled": cancelled}
