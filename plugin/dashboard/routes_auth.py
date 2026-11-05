"""Public routes: liveness and the Telegram login.

Both paths are registered with the dashboard as public (see ``plugin_api.py``);
everything else in the plugin sits behind the dashboard's session-token check.
"""

from __future__ import annotations

import logging
import sys

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

compat = sys.modules["hermes_tma_hermes_compat"]  # loaded first by plugin_api.py
settings = compat.load_sibling("settings")
tg_auth = compat.load_sibling("tg_auth")

router = APIRouter()
_log = logging.getLogger("hermes.plugin.telegram-app")

_limiter = tg_auth.FailureLimiter(max_failures=10, window_sec=300)


def _client_key(request: Request) -> str:
    # Behind a reverse proxy every request comes from the proxy address, so
    # this degrades to one global bucket — acceptable for a single-owner panel.
    return request.client.host if request.client else "unknown"


@router.get("/health")
async def health():
    """Public — no auth required. Used by reverse proxies / uptime checks."""
    return {
        "ok": True,
        "plugin": "telegram-app",
        "version": settings.VERSION,
        "uptime_sec": settings.uptime_sec(),
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
            bot_token=settings.bot_token(),
            allowed_user_ids=settings.allowed_user_ids(),
            max_age_sec=settings.max_age(),
            bot_id=settings.env("TELEGRAM_BOT_ID") or None,
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

    token = compat.get_session_token()
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
