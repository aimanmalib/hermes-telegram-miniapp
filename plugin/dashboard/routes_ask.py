"""Ask Hermes: one prompt from the phone, answered by the agent in an admin's Telegram chat.

Nothing new is opened up in Hermes. An Ask is the same agent cron job ``POST /cron`` can
already create, narrowed further: the client sends only the prompt (and, optionally, which
admin's chat gets the answer). The job is scheduled once, for now, with ``repeat=1``, and is
delivered to ``telegram:<admin chat id>``; Hermes's cron ticker (in the gateway) runs it and
sends the answer. No ``script``, ``workdir``, ``model``, ``provider`` or toolsets from the
client, the prompt length is capped by the ``ask_max_chars`` plugin setting, and at most
``ask_max_pending`` Asks may wait or run at once. See docs/decisions/0008-ask-hermes.md.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

compat = sys.modules["hermes_tma_hermes_compat"]  # loaded first by plugin_api.py
router = APIRouter()
_log = logging.getLogger("hermes.plugin.telegram-app")
settings = compat.load_sibling("settings")
cron_routes = compat.load_sibling("routes_cron")

# Asks are ordinary cron jobs; the name prefix is how the plugin tells them apart.
ASK_NAME_PREFIX = "Ask: "
_NAME_PROMPT_CHARS = 48
# Hermes job states after which a one-shot job will not run again.
_DONE_STATES = frozenset({"completed", "error", "failed", "cancelled"})


class _AskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The hard ceiling; the configurable limit (ask_max_chars) is checked in the route.
    prompt: str = Field(..., min_length=1, max_length=20_000)
    chat_id: Optional[int] = None  # must be a Mini App admin; defaults to the first


def _job_name(prompt: str) -> str:
    text = " ".join(prompt.split())
    if len(text) > _NAME_PROMPT_CHARS:
        text = text[: _NAME_PROMPT_CHARS - 1].rstrip() + "…"
    return ASK_NAME_PREFIX + text


def _is_pending_ask(job: Any) -> bool:
    if not isinstance(job, dict) or not str(job.get("name") or "").startswith(ASK_NAME_PREFIX):
        return False
    if cron_routes._is_running(job):
        return True
    return bool(job.get("enabled", True)) and job.get("state") not in _DONE_STATES


def _pending_asks() -> int:
    from cron.jobs import list_jobs  # type: ignore

    return sum(1 for job in list_jobs(include_disabled=True) if _is_pending_ask(job))


@router.post("/ask")
async def ask(body: _AskBody) -> Dict[str, Any]:
    """Queue one agent run whose answer Hermes delivers to an admin's Telegram chat."""
    prompt = body.prompt.strip()
    limit = settings.ask_max_chars()
    if not prompt:
        raise HTTPException(status_code=422, detail={"code": "empty", "message": "The question is empty"})
    if len(prompt) > limit:
        raise HTTPException(
            status_code=422,
            detail={"code": "too_long", "message": f"Questions are limited to {limit} characters", "limit": limit},
        )

    allowed = settings.admin_user_ids()
    if not allowed:
        raise HTTPException(status_code=400, detail="No Mini App admin configured (TELEGRAM_OWNER_ID)")
    chat_id = body.chat_id or int(allowed[0])
    # Like the send box: answers only ever go to an admin's own chat.
    if str(chat_id) not in allowed:
        raise HTTPException(status_code=403, detail="chat_id is not a Mini App admin")

    try:
        from cron.jobs import create_job  # type: ignore

        pending = _pending_asks()
    except Exception as exc:
        _log.exception("ask: cannot read cron jobs")
        raise HTTPException(status_code=500, detail=str(exc))
    max_pending = settings.ask_max_pending()
    if pending >= max_pending:
        raise HTTPException(
            status_code=409,
            detail={"code": "busy", "message": "Hermes is still answering the last question", "limit": max_pending},
        )

    try:
        job = create_job(
            prompt=prompt,
            schedule=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            name=_job_name(prompt),
            repeat=1,
            deliver=f"telegram:{chat_id}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        _log.exception("ask: create failed")
        raise HTTPException(status_code=500, detail=str(exc))
    return {"ok": True, "job": job}
