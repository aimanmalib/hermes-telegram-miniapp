"""Logs — tail of ``<hermes home>/logs/<file>.log`` with an optional level filter."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException

compat = sys.modules["hermes_tma_hermes_compat"]  # loaded first by plugin_api.py
router = APIRouter()
_log = logging.getLogger("hermes.plugin.telegram-app")


_LOG_FILES = {"agent", "errors", "gateway"}
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
# Standard Python logger.Formatter("%(asctime)s ...") prefix is e.g.
# "2026-05-23 17:42:18,123 - hermes.agent - INFO - msg" — extract level
# from the third "-"-separated field. We're forgiving: anything that
# matches a known level token in the line counts as that level.
_LEVEL_PRIORITY = {
    "DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50,
}


def _classify_level(line: str) -> str:
    upper = line.upper()
    # Cheap order: most specific first so 'WARNING' isn't beaten by 'INFO'
    for lv in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"):
        if lv in upper:
            return lv
    return "INFO"


def _tail_file(path: Path, max_lines: int) -> List[str]:
    """Read the last ``max_lines`` lines of a file efficiently.

    For mini-app log tails we cap reads at the last ~512 KB. Logs longer
    than that get clipped to the most recent slice — fine for a phone UI.
    """
    if not path.exists() or not path.is_file():
        return []
    try:
        size = path.stat().st_size
        read_window = min(size, 512 * 1024)
        with path.open("rb") as fh:
            fh.seek(size - read_window)
            data = fh.read()
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if read_window < size:
            # We started mid-line; drop the (likely partial) first line.
            lines = lines[1:]
        return lines[-max_lines:]
    except Exception as exc:
        _log.warning("log tail failed for %s: %s", path, exc)
        return []


@router.get("/logs")
async def logs_tail(
    file: str = "agent",
    lines: int = 200,
    level: str = "ALL",
):
    """Tail of ``~/.hermes/logs/<file>.log`` with optional level filter.

    Parameters
    ----------
    file : agent | errors | gateway
    lines : 1..2000 (clamped) — how many tail lines to return after filter
    level : ALL | DEBUG | INFO | WARNING | ERROR | CRITICAL —
            include this level *and above*, e.g. WARNING returns warnings,
            errors and criticals.
    """
    if file not in _LOG_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"file must be one of {sorted(_LOG_FILES)}",
        )
    lines = max(1, min(2000, int(lines)))
    level_upper = (level or "ALL").upper()
    min_priority = 0
    if level_upper != "ALL":
        if level_upper not in _LOG_LEVELS:
            raise HTTPException(
                status_code=400,
                detail=f"level must be ALL or one of {sorted(_LOG_LEVELS)}",
            )
        min_priority = _LEVEL_PRIORITY[level_upper]

    log_path = compat.hermes_home() / "logs" / f"{file}.log"
    # Read 4× requested so the post-filter slice has room.
    raw = _tail_file(log_path, lines * 4 if min_priority else lines)

    if min_priority:
        filtered = [
            line for line in raw
            if _LEVEL_PRIORITY.get(_classify_level(line), 0) >= min_priority
        ]
    else:
        filtered = raw
    filtered = filtered[-lines:]

    # Best-effort file mtime (UI shows "as of …")
    try:
        mtime = log_path.stat().st_mtime if log_path.exists() else 0
    except Exception:
        mtime = 0

    return {
        "file": file,
        "level": level_upper,
        "lines": filtered,
        "count": len(filtered),
        "mtime": mtime,
        "path": str(log_path),
    }
