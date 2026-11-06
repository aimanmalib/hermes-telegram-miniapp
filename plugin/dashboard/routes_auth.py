"""Liveness and the Telegram login.

``/auth/verify`` is a token route: Hermes lets it through only when the bearer is Telegram
``initData`` that ``tg_token.verify_bearer`` accepts (registered in
``plugin/__init__.py``). ``/health`` and everything else take the dashboard session token.
"""

from __future__ import annotations

import logging
import sys

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

compat = sys.modules["hermes_tma_hermes_compat"]  # loaded first by plugin_api.py
settings = compat.load_sibling("settings")
tg_auth = compat.load_sibling("tg_auth")
tg_token = compat.load_sibling("tg_token")

router = APIRouter()
_log = logging.getLogger("hermes.plugin.telegram-app")

_limiter = tg_auth.FailureLimiter(max_failures=10, window_sec=300)


def _client_key(request: Request) -> str:
    # Behind a reverse proxy every request comes from the proxy address, so
    # this degrades to one global bucket — acceptable for a single-owner panel.
    return request.client.host if request.client else "unknown"


@router.get("/health")
async def health():
    """Plugin status, behind the dashboard session token.

    ``auth_mode`` says whether the login route is reachable (``token-seam``); ``capabilities`` lists
    the optional Hermes features the Mini App may offer. No secrets.
    """
    return {
        "ok": True,
        "plugin": "telegram-app",
        "version": settings.VERSION,
        "uptime_sec": settings.uptime_sec(),
        "auth_mode": compat.auth_mode(tg_token.LOGIN_PATH, tg_token.PROVIDER_NAME),
        "hermes_version": compat.hermes_version(),
        "capabilities": compat.capabilities(),
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
    # Hermes v0.23.0 admits any token provider's principal on any token route, so the drain secret
    # would get through the gate. Only a principal from our own provider may log in.
    principal = getattr(request.state, "token_principal", None)
    if principal is not None and getattr(principal, "provider", None) != tg_token.PROVIDER_NAME:
        _log.warning("telegram-app: login refused, bearer vouched by %r", getattr(principal, "provider", None))
        raise HTTPException(status_code=403, detail="Invalid Telegram initData")
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
