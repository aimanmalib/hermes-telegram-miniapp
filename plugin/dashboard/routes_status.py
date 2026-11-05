"""Host status and token/cost usage (read-only, behind the dashboard session token)."""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

compat = sys.modules["hermes_tma_hermes_compat"]  # loaded first by plugin_api.py
router = APIRouter()
_log = logging.getLogger("hermes.plugin.telegram-app")
settings = compat.load_sibling("settings")

@router.get("/status")
async def status_endpoint():
    import shutil
    cpu = -1
    mem_pct = -1
    mem_used_gb = 0.0
    mem_total_gb = 0.0
    load: List[float] = []
    try:
        import psutil  # type: ignore
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        mem_pct = mem.percent
        mem_total_gb = round(mem.total / 1024**3, 2)
        mem_used_gb = round(mem.used / 1024**3, 2)
    except Exception as exc:
        _log.debug("psutil missing: %s", exc)
    try:
        load = list(os.getloadavg())
    except Exception:
        pass

    disk = shutil.disk_usage("/")
    disk_pct = round(100 * disk.used / disk.total, 1)
    disk_used_gb = round(disk.used / 1024**3, 1)
    disk_total_gb = round(disk.total / 1024**3, 1)

    sessions_count = 0
    try:
        from hermes_state import SessionDB  # type: ignore
        db = SessionDB()
        if hasattr(db, "session_count"):
            sessions_count = int(db.session_count())
        else:  # older Hermes
            sessions_count = len(db.list_sessions_rich(limit=1000))
    except Exception:
        pass

    cron_count = 0
    try:
        from cron.jobs import list_jobs  # type: ignore
        cron_count = len(list_jobs())
    except Exception:
        pass

    return {
        "cpu_pct": cpu,
        "mem_pct": mem_pct,
        "mem_used_gb": mem_used_gb,
        "mem_total_gb": mem_total_gb,
        "load_avg": load,
        "disk_pct": disk_pct,
        "disk_used_gb": disk_used_gb,
        "disk_total_gb": disk_total_gb,
        "sessions_count": sessions_count,
        "cron_count": cron_count,
        "uptime_sec": settings.uptime_sec(),
    }


# ---------------------------------------------------------------------------
# Usage / cost aggregation — totals + top-cost sessions, filtered by window.
# ---------------------------------------------------------------------------
def _now() -> float:
    return time.time()


def _window_start(window: str) -> float:
    """Returns the unix-timestamp lower bound for a named window."""
    import datetime as dt

    now = dt.datetime.now()
    if window == "today":
        # Local-day boundary
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.timestamp()
    if window == "week":
        start = now - dt.timedelta(days=7)
        return start.timestamp()
    if window == "month":
        start = now - dt.timedelta(days=30)
        return start.timestamp()
    # "all" or anything else
    return 0.0


@router.get("/usage")
async def usage_summary(window: str = "today", top: int = 5):
    """Sum tokens + cost across sessions started inside the chosen window.

    window : today (00:00 local) | week (last 7d) | month (last 30d) | all
    top    : number of expensive sessions to surface (capped 1..20)
    """
    if window not in ("today", "week", "month", "all"):
        raise HTTPException(
            status_code=400,
            detail="window must be today | week | month | all",
        )
    top = max(1, min(20, int(top)))

    try:
        from hermes_state import SessionDB  # type: ignore
        # Pull a generous slice — ordered by recency. For 'all' grab a hard
        # cap so we don't walk the whole DB just for a phone widget.
        rows = SessionDB().list_sessions_rich(
            limit=2000 if window == "all" else 500,
            order_by_last_active=True,
        )
    except Exception as exc:
        _log.exception("usage list failed")
        raise HTTPException(status_code=500, detail=str(exc))

    cutoff = _window_start(window)

    in_window: List[Dict[str, Any]] = []
    for s in rows:
        # last_active is more representative of "active during window" than
        # started_at for long-running conversations (a session started 8h
        # ago that just sent a message at 10pm should still count today).
        ts = s.get("last_active") or s.get("started_at") or 0
        try:
            ts = float(ts)
        except (TypeError, ValueError):
            ts = 0
        if ts >= cutoff:
            in_window.append(s)

    total_input = sum(int(s.get("input_tokens") or 0) for s in in_window)
    total_output = sum(int(s.get("output_tokens") or 0) for s in in_window)
    total_cost = sum(float(s.get("estimated_cost_usd") or 0) for s in in_window)
    total_messages = sum(int(s.get("message_count") or 0) for s in in_window)

    # Top by cost (fall back to total tokens when cost is 0/unknown so the
    # widget still ranks something useful for free-tier providers).
    def _rank_key(s: Dict[str, Any]) -> float:
        c = float(s.get("estimated_cost_usd") or 0)
        if c > 0:
            return c
        return float((s.get("input_tokens") or 0) + (s.get("output_tokens") or 0)) / 1e9

    top_rows = sorted(in_window, key=_rank_key, reverse=True)[:top]
    top_slim = [
        {
            "id": s.get("id"),
            "title": (s.get("title") or "(untitled)")[:80],
            "source": s.get("source"),
            "model": s.get("model"),
            "input_tokens": int(s.get("input_tokens") or 0),
            "output_tokens": int(s.get("output_tokens") or 0),
            "estimated_cost_usd": float(s.get("estimated_cost_usd") or 0),
            "message_count": int(s.get("message_count") or 0),
            "last_active": s.get("last_active"),
        }
        for s in top_rows
    ]

    return {
        "window": window,
        "session_count": len(in_window),
        "input_tokens": total_input,
        "output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "estimated_cost_usd": round(total_cost, 4),
        "message_count": total_messages,
        "top_sessions": top_slim,
        "as_of": _now(),
    }
