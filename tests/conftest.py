"""Shared helpers. The plugin is loaded from files, the way Hermes loads it."""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import sys
import urllib.parse
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugin" / "dashboard"

BOT_TOKEN = "123456789:AAE-known-answer-test-token"
OWNER_ID = 424242
USER = {"id": OWNER_ID, "first_name": "Ada", "username": "ada_test", "language_code": "en"}
USER_JSON = json.dumps(USER, separators=(",", ":"))


def load_module(name: str, alias: str):
    sys.modules.pop(alias, None)
    spec = importlib.util.spec_from_file_location(alias, PLUGIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


def spec_hash(fields: dict, bot_token: str) -> str:
    """Independent re-statement of the spec (deliberately not using tg_auth)."""
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields) if k != "hash")
    return hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()


def encode(fields: dict, *, plus_spaces: bool = False) -> str:
    quote = urllib.parse.quote_plus if plus_spaces else urllib.parse.quote
    return "&".join(f"{k}={quote(str(v), safe='')}" for k, v in fields.items())


def make_init_data(
    *,
    auth_date: int,
    user: dict | None = None,
    bot_token: str = BOT_TOKEN,
    extra: dict | None = None,
    ed_key=None,
    ed_bot_id: str | None = None,
    plus_spaces: bool = False,
) -> str:
    fields = {
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(user or USER, separators=(",", ":")),
        "auth_date": str(auth_date),
    }
    fields.update(extra or {})
    if ed_key is not None:
        body = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
        message = f"{ed_bot_id}:WebAppData\n{body}".encode()
        fields["signature"] = base64.urlsafe_b64encode(ed_key.sign(message)).rstrip(b"=").decode()
    fields["hash"] = spec_hash(fields, bot_token)
    return encode(fields, plus_spaces=plus_spaces)


@pytest.fixture
def tg_auth():
    return load_module("tg_auth", "tma_test_tg_auth")
