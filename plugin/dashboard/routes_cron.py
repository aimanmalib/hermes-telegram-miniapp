"""Cron jobs: list, create, edit, delete, pause/resume/trigger — through ``cron.jobs``."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()
_log = logging.getLogger("hermes.plugin.telegram-app")


@router.get("/cron")
async def cron_list():
    try:
        from cron.jobs import list_jobs  # type: ignore
        # include_disabled=True so the UI can show paused jobs and resume them.
        return {"jobs": list_jobs(include_disabled=True)}
    except Exception as exc:
        _log.exception("cron list failed")
        raise HTTPException(status_code=500, detail=str(exc))


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


@router.post("/cron")
async def cron_create(body: _CronCreateBody):
    """Create an agent cron job via ``cron.jobs.create_job``."""
    try:
        from cron.jobs import create_job  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    try:
        job = create_job(**body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        _log.exception("cron create failed")
        raise HTTPException(status_code=500, detail=str(exc))
    return {"ok": True, "job": job}


class _CronUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    schedule: Optional[str] = None
    prompt: Optional[str] = None
    deliver: Optional[str] = None
    repeat: Optional[int] = None
    skills: Optional[List[str]] = None
    enabled_toolsets: Optional[List[str]] = None


@router.patch("/cron/{job_id}")
async def cron_update(job_id: str, body: _CronUpdateBody):
    try:
        from cron.jobs import update_job  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    updates: Dict[str, Any] = {}
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            updates[k] = v
    if not updates:
        raise HTTPException(status_code=400, detail="no fields to update")
    try:
        job = update_job(job_id, updates)
    except Exception as exc:
        _log.exception("cron update failed")
        raise HTTPException(status_code=500, detail=str(exc))
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job": job}


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
