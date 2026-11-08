"""Send tab: forward text to the owner's Telegram DM through the bot."""

from __future__ import annotations

import json
import logging
import sys
import urllib.request
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

compat = sys.modules["hermes_tma_hermes_compat"]  # loaded first by plugin_api.py
router = APIRouter()
_log = logging.getLogger("hermes.plugin.telegram-app")
settings = compat.load_sibling("settings")

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
    token = settings.bot_token()
    if not token:
        raise HTTPException(status_code=500, detail="Bot token not configured")

    allowed = settings.admin_user_ids()
    if not allowed:
        raise HTTPException(
            status_code=400,
            detail="No Mini App admin configured (TELEGRAM_OWNER_ID)",
        )
    chat_id = body.chat_id or int(allowed[0])
    # The bot only ever writes to an admin's DM, never an arbitrary chat.
    if str(chat_id) not in allowed:
        raise HTTPException(status_code=403, detail="chat_id is not a Mini App admin")

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
