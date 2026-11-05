"""Session list and slimmed message history (read-only)."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

router = APIRouter()
_log = logging.getLogger("hermes.plugin.telegram-app")


@router.get("/sessions")
async def sessions_list(limit: int = 30, source: Optional[str] = None):
    """Recent sessions, slimmed for mobile UI (omits the ~20KB system prompt)."""
    try:
        from hermes_state import SessionDB  # type: ignore
        rows = SessionDB().list_sessions_rich(
            source=source, limit=limit, order_by_last_active=True,
        )
        return {
            "sessions": [
                {
                    "id": s.get("id"),
                    "title": s.get("title") or "(untitled)",
                    "preview": (s.get("preview") or "")[:200],
                    "source": s.get("source"),
                    "model": s.get("model"),
                    "started_at": s.get("started_at"),
                    "last_active": s.get("last_active"),
                    "message_count": s.get("message_count"),
                    "tool_call_count": s.get("tool_call_count"),
                    "input_tokens": s.get("input_tokens", 0),
                    "output_tokens": s.get("output_tokens", 0),
                    "estimated_cost_usd": s.get("estimated_cost_usd", 0),
                }
                for s in rows
            ]
        }
    except Exception as exc:
        _log.exception("sessions list failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/sessions/{session_id}/messages")
async def session_messages(session_id: str, limit: int = 200):
    """Messages for a session. ``limit`` clamps the trailing slice for the UI."""
    try:
        from hermes_state import SessionDB  # type: ignore
        msgs = SessionDB().get_messages(session_id=session_id) or []
        if limit and len(msgs) > limit:
            msgs = msgs[-limit:]
        # Slim each message: drop tool_calls payloads + reasoning to keep
        # the response phone-friendly. The dashboard's full message view
        # uses upstream /api/sessions/{id}/messages for full fidelity.
        slim = []
        for m in msgs:
            if not isinstance(m, dict):
                continue
            content = m.get("content")
            if isinstance(content, list):
                # Multipart content (vision messages, etc.) — collapse to
                # a text-only summary.
                parts = []
                for p in content:
                    if isinstance(p, dict):
                        if p.get("type") == "text":
                            parts.append(p.get("text", ""))
                        elif p.get("type") in ("image_url", "image"):
                            parts.append("[image]")
                        elif p.get("type") == "input_audio":
                            parts.append("[voice]")
                content = "\n".join(parts)
            if isinstance(content, str) and len(content) > 4000:
                content = content[:4000] + " …[truncated]"
            slim.append({
                "role": m.get("role"),
                "content": content,
                "name": m.get("name"),
                "timestamp": m.get("timestamp"),
            })
        return {"session_id": session_id, "messages": slim}
    except Exception as exc:
        _log.exception("session messages failed")
        raise HTTPException(status_code=500, detail=str(exc))
