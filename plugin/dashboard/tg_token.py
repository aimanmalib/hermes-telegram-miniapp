"""Telegram ``initData`` as a dashboard bearer token (Hermes token-auth seam, v0.23.0+).

The Mini App sends ``Authorization: Bearer <initData>`` on ``POST /auth/verify``. Hermes asks every
token provider to vouch for the bearer; ours runs the full check from ``tg_auth`` (HMAC or Ed25519
signature, freshness, allowlist) and vouches only when all of it passes. Anything else returns None:
the seam then answers 401 and the route handler never runs.

Hermes consults every token provider on every token route, so a valid ``initData`` is also accepted
on core token routes. That grants nothing new: the same ``initData`` already buys the dashboard
session token, which authorises the whole dashboard API (see SECURITY-REVIEW.md).
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

compat = sys.modules["hermes_tma_hermes_compat"]  # loaded first by plugin/__init__.py
settings = compat.load_sibling("settings")
tg_auth = compat.load_sibling("tg_auth")

_log = logging.getLogger("hermes.plugin.telegram-app")

PROVIDER_NAME = "telegram-app-initdata"
LOGIN_PATH = "/api/plugins/telegram-app/auth/verify"
# Stamped on every principal we issue and demanded by the login route where Hermes supports route
# scopes, so another provider's credential cannot open our route and ours cannot open a scoped one.
SCOPE = "telegram-app"


def verify_bearer(token: str) -> Optional[str]:
    """``telegram:<user id>`` for valid, fresh, allowlisted ``initData``; None for anything else.

    Raises ``LoginNotConfigured`` (the seam answers 503) when the bot token or the allowlist is unset.
    """
    if not token or len(token) > tg_auth.MAX_INIT_DATA_LEN or "hash=" not in token:
        return None  # not Telegram initData; other providers decide
    try:
        user = tg_auth.verify_init_data(
            token,
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
            raise compat.LoginNotConfigured(exc.reason) from exc
        _log.warning("telegram-app: initData bearer rejected (%s)", exc.reason)
        return None
    return f"telegram:{user.get('id')}"


def provider():
    return compat.token_provider(PROVIDER_NAME, "Telegram Mini App (initData)", verify_bearer, scope=SCOPE)
