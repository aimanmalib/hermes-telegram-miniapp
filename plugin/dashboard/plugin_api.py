"""Telegram Mini App plugin — backend API routes.

Mounted by the Hermes dashboard plugin loader at ``/api/plugins/telegram-app/``.

Auth model
----------
Hermes gates every ``/api/*`` route with the dashboard session token
(``X-Hermes-Session-Token``). This plugin lets two paths through *without*
that token by adding them to the dashboard's public-path set:

  /api/plugins/telegram-app/health        — liveness, no secrets
  /api/plugins/telegram-app/auth/verify   — accepts Telegram initData and
                                            returns the dashboard session token

The Mini App then:

  1. Reads ``window.Telegram.WebApp.initData``.
  2. POSTs it to ``/auth/verify``. The plugin verifies the signature (HMAC-SHA256
     keyed by the bot token; Ed25519 against Telegram's public key as a
     fallback), rejects stale ``auth_date`` values and checks the user against
     an explicit allowlist (see ``tg_auth.py``).
  3. Receives the dashboard session token and sends it as
     ``X-Hermes-Session-Token`` on every later call, so the dashboard's own
     auth middleware does the rest.

Every other route below relies on that upstream middleware.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

_HERE = Path(__file__).resolve().parent

router = APIRouter()
_log = logging.getLogger("hermes.plugin.telegram-app")
_start_time = time.time()


def _load_sibling(name: str):
    """Import a module that lives next to this file under a unique name.

    Hermes imports ``plugin_api.py`` with ``spec_from_file_location`` (not as a
    package), so ``from . import x`` does not work, and putting this directory
    on ``sys.path`` would let a generic name like ``alerts`` collide with any
    other module of that name.
    """
    mod_name = f"hermes_tma_{name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, _HERE / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
    return mod


tg_auth = _load_sibling("tg_auth")


def _plugin_version() -> str:
    try:
        return str(json.loads((_HERE / "manifest.json").read_text("utf-8")).get("version", "0.0.0"))
    except Exception:
        return "0.0.0"


_VERSION = _plugin_version()


def _hermes_home() -> Path:
    """Hermes home directory: Hermes' own resolver when available, else $HERMES_HOME or ~/.hermes."""
    try:
        from hermes_constants import get_hermes_home  # type: ignore

        return Path(get_hermes_home())
    except Exception:
        env = os.environ.get("HERMES_HOME", "").strip()
        return Path(env).expanduser() if env else Path.home() / ".hermes"


# ---------------------------------------------------------------------------
# Public paths. Hermes has no plugin API for declaring unauthenticated routes,
# so we add ours to ``hermes_cli.web_server._PUBLIC_API_PATHS`` at import time.
# The loopback auth middleware looks that module global up on every request.
# The OAuth-gated mode (``auth_required``) uses a separate list and cookie
# auth, and is not supported by this plugin.
# ---------------------------------------------------------------------------
PUBLIC_PATHS = (
    "/api/plugins/telegram-app/health",
    "/api/plugins/telegram-app/auth/verify",
)


def _allow_public(paths: Tuple[str, ...]) -> None:
    try:
        import hermes_cli.web_server as ws  # type: ignore

        existing = set(getattr(ws, "_PUBLIC_API_PATHS", frozenset()))
        existing.update(paths)
        ws._PUBLIC_API_PATHS = frozenset(existing)
        _log.info("telegram-app: registered public paths %s", list(paths))
    except Exception as exc:
        _log.warning("telegram-app: could not register public paths: %s", exc)


_allow_public(PUBLIC_PATHS)


# ---------------------------------------------------------------------------
# Alerts watcher — background thread that DMs the owner about cron failures,
# error-log bursts and daily spend.
# ---------------------------------------------------------------------------
try:
    _alerts = _load_sibling("alerts")
except Exception as _exc:  # pragma: no cover - defensive
    _alerts = None
    _log.warning("telegram-app: alerts module unavailable: %s", _exc)

if _alerts is not None and os.environ.get("TELEGRAM_APP_ALERTS_DISABLED", "") != "1":
    try:
        _alerts.ensure_started()
    except Exception as _exc:
        _log.warning("telegram-app: alerts ensure_started failed: %s", _exc)


def _get_session_token() -> str:
    """The running dashboard's session token (``hermes_cli.web_server._SESSION_TOKEN``).

    Read at request time: Hermes may rebind it (desktop/SSH launches).
    """
    try:
        import hermes_cli.web_server as ws  # type: ignore

        return getattr(ws, "_SESSION_TOKEN", "") or ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Config — read at request time so .env edits are picked up without a restart.
# ---------------------------------------------------------------------------
def _env(name: str, default: str = "") -> str:
    val = os.getenv(name, "").strip()
    if val:
        return val
    env_file = _hermes_home() / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == name:
                return v.strip().strip('"').strip("'")
    return default


def _bot_token() -> str:
    return _env("TELEGRAM_BOT_TOKEN")


def _allowed_user_ids() -> List[str]:
    """Union of TELEGRAM_OWNER_ID and TELEGRAM_ALLOWED_USERS (numeric ids, owner first)."""
    ids: List[str] = []
    for raw in (_env("TELEGRAM_OWNER_ID"), _env("TELEGRAM_ALLOWED_USERS")):
        for uid in tg_auth.parse_allowlist(raw):
            if uid not in ids:
                ids.append(uid)
    return ids


def _max_age() -> int:
    return tg_auth.parse_max_age(_env("TELEGRAM_INITDATA_MAX_AGE"))


_limiter = tg_auth.FailureLimiter(max_failures=10, window_sec=300)


def _client_key(request: Request) -> str:
    # Behind a reverse proxy every request comes from the proxy address, so
    # this degrades to one global bucket — acceptable for a single-owner panel.
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/health")
async def health():
    """Public — no auth required. Used by reverse proxies / uptime checks."""
    return {
        "ok": True,
        "plugin": "telegram-app",
        "version": _VERSION,
        "uptime_sec": int(time.time() - _start_time),
    }


class _AuthVerifyBody(BaseModel):
    init_data: str = Field(..., max_length=tg_auth.MAX_INIT_DATA_LEN)


@router.post("/auth/verify")
async def auth_verify(body: _AuthVerifyBody, request: Request, response: Response):
    """Verify Telegram initData and return the dashboard session token.

    Every rejection returns the same 403 so callers cannot tell which check
    failed; the reason is logged server-side (never the initData itself).
    """
    response.headers["Cache-Control"] = "no-store"
    key = _client_key(request)
    wait = _limiter.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts",
            headers={"Retry-After": str(wait)},
        )

    try:
        user = tg_auth.verify_init_data(
            body.init_data,
            bot_token=_bot_token(),
            allowed_user_ids=_allowed_user_ids(),
            max_age_sec=_max_age(),
            bot_id=_env("TELEGRAM_BOT_ID") or None,
        )
    except tg_auth.InitDataError as exc:
        if exc.reason in ("bot_token_unset", "allowlist_unset"):
            _log.error(
                "telegram-app: refusing login, %s (set TELEGRAM_BOT_TOKEN and "
                "TELEGRAM_OWNER_ID or TELEGRAM_ALLOWED_USERS)", exc.reason,
            )
            raise HTTPException(status_code=503, detail="Mini App login is not configured")
        _limiter.record_failure(key)
        _log.warning("telegram-app: initData rejected (%s)", exc.reason)
        raise HTTPException(status_code=403, detail="Invalid Telegram initData")

    token = _get_session_token()
    if not token:
        raise HTTPException(status_code=503, detail="Dashboard session token unavailable")

    return {
        "ok": True,
        "session_token": token,
        "user": {
            "id": user.get("id"),
            "first_name": user.get("first_name"),
            "username": user.get("username"),
            "language_code": user.get("language_code"),
            "is_premium": bool(user.get("is_premium", False)),
        },
    }


# ---------------------------------------------------------------------------
# Read-only convenience endpoints (gated by upstream auth — caller must
# include ``X-Hermes-Session-Token``).
# ---------------------------------------------------------------------------
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
        "uptime_sec": int(time.time() - _start_time),
    }


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
    prompt: Optional[str] = None
    schedule: str
    name: Optional[str] = None
    deliver: Optional[str] = None  # "origin" | "local" | "telegram" | ...
    repeat: Optional[int] = None
    skills: Optional[List[str]] = None
    enabled_toolsets: Optional[List[str]] = None
    workdir: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    no_agent: bool = False
    script: Optional[str] = None


@router.post("/cron")
async def cron_create(body: _CronCreateBody):
    """Create a new cron job. Same kwargs as ``cron.jobs.create_job``."""
    try:
        from cron.jobs import create_job  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not body.schedule:
        raise HTTPException(status_code=400, detail="schedule is required")
    if body.no_agent:
        if not body.script:
            raise HTTPException(
                status_code=400,
                detail="script is required when no_agent=True",
            )
    else:
        if not body.prompt:
            raise HTTPException(
                status_code=400, detail="prompt is required for agent jobs"
            )

    try:
        job = create_job(
            prompt=body.prompt,
            schedule=body.schedule,
            name=body.name,
            deliver=body.deliver,
            repeat=body.repeat,
            skills=body.skills,
            enabled_toolsets=body.enabled_toolsets,
            workdir=body.workdir,
            model=body.model,
            provider=body.provider,
            no_agent=body.no_agent,
            script=body.script,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        _log.exception("cron create failed")
        raise HTTPException(status_code=500, detail=str(exc))
    return {"ok": True, "job": job}


class _CronUpdateBody(BaseModel):
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


# ---------------------------------------------------------------------------
# Skills index + memory dump (read-only).
# ---------------------------------------------------------------------------
def _skills_root() -> Path:
    return _hermes_home() / "skills"


def _parse_skill_meta(skill_md: Path) -> Dict[str, Any]:
    """Pull name + description from the YAML frontmatter of a SKILL.md."""
    name = skill_md.parent.name
    description = ""
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {"name": name, "description": "", "size": 0}
    size = len(text.encode("utf-8"))
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            front = text[3:end]
            for line in front.splitlines():
                line = line.strip()
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("description:"):
                    description = (
                        line.split(":", 1)[1].strip().strip('"').strip("'")
                    )
    return {"name": name, "description": description, "size": size}


@router.get("/skills")
async def skills_list():
    """List all installed skills (one entry per SKILL.md)."""
    root = _skills_root()
    if not root.exists():
        return {"skills": [], "root": str(root)}

    items: List[Dict[str, Any]] = []
    for skill_md in sorted(root.rglob("SKILL.md")):
        try:
            rel = skill_md.parent.relative_to(root)
        except ValueError:
            continue
        category = rel.parts[0] if len(rel.parts) > 1 else None
        meta = _parse_skill_meta(skill_md)
        items.append(
            {
                "id": str(rel).replace("\\", "/"),
                "name": meta["name"],
                "description": meta["description"],
                "category": category,
                "size": meta["size"],
                "path": str(skill_md),
            }
        )
    items.sort(key=lambda x: ((x["category"] or "zzz"), x["name"]))
    return {"skills": items, "count": len(items), "root": str(root)}


def _safe_skill_path(skill_id: str) -> Optional[Path]:
    """Resolve a skill id to its absolute SKILL.md, refusing escapes."""
    if not skill_id or ".." in skill_id.split("/"):
        return None
    root = _skills_root().resolve()
    candidate = (root / skill_id / "SKILL.md").resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.exists() else None


@router.get("/skills/{skill_id:path}")
async def skill_view(skill_id: str):
    """Return the full SKILL.md text for a single skill."""
    p = _safe_skill_path(skill_id)
    if not p:
        raise HTTPException(status_code=404, detail="Skill not found")
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "id": skill_id,
        "content": text,
        "size": len(text.encode("utf-8")),
        "path": str(p),
    }


@router.get("/memory")
async def memory_dump():
    """Return the agent's persistent memory + user profile (read-only)."""
    base = _hermes_home() / "memories"
    out: Dict[str, Any] = {"root": str(base), "files": {}}
    for label, fname in (("memory", "MEMORY.md"), ("user", "USER.md")):
        path = base / fname
        if not path.exists():
            out["files"][label] = {
                "exists": False, "content": "", "size": 0, "mtime": 0,
            }
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            stat = path.stat()
            out["files"][label] = {
                "exists": True,
                "content": text,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "path": str(path),
            }
        except Exception as exc:
            out["files"][label] = {
                "exists": True,
                "content": f"<read error: {exc}>",
                "size": 0,
                "mtime": 0,
            }
    return out


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


# ---------------------------------------------------------------------------
# Logs — read tail of ~/.hermes/logs/<file>.log with optional level filter.
# ---------------------------------------------------------------------------
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

    log_path = _hermes_home() / "logs" / f"{file}.log"
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


class _SendCommandBody(BaseModel):
    # Telegram's sendMessage limit is 4096 characters.
    text: str = Field(..., min_length=1, max_length=4096)
    chat_id: Optional[int] = None  # must be an allowlisted user; defaults to the first


@router.post("/command")
async def send_command(body: _SendCommandBody):
    """Forward text to the user's Telegram DM via the bot.

    The user types in the mini app, we POST it via Bot API ``sendMessage``,
    so the message appears in their normal chat with the bot, where the
    Hermes gateway routes it to the agent and the reply streams back as
    Telegram messages. The mini app stays a control-surface, not a chat
    surface — Telegram itself is the chat surface.
    """
    token = _bot_token()
    if not token:
        raise HTTPException(status_code=500, detail="Bot token not configured")

    allowed = _allowed_user_ids()
    if not allowed:
        raise HTTPException(
            status_code=400,
            detail="No TELEGRAM_OWNER_ID / TELEGRAM_ALLOWED_USERS configured",
        )
    chat_id = body.chat_id or int(allowed[0])
    # The bot only ever writes to allowlisted users' DMs, never an arbitrary chat.
    if str(chat_id) not in allowed:
        raise HTTPException(status_code=403, detail="chat_id is not an allowed user")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": body.text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data.get("ok"):
            raise HTTPException(
                status_code=502,
                detail=f"Telegram API: {data.get('description', 'request rejected')}",
            )
        return {"ok": True, "message_id": data["result"]["message_id"]}
    except HTTPException:
        raise
    except Exception as exc:
        # Never echo the exception: urllib errors can carry the request URL,
        # which contains the bot token.
        _log.warning("telegram-app: sendMessage failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Telegram API request failed")


# ---------------------------------------------------------------------------
# Push alerts — settings + status + manual test
# ---------------------------------------------------------------------------
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
