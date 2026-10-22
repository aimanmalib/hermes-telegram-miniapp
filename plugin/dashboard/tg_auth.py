"""Telegram Mini App ``initData`` verification.

Pure functions, no I/O and no side effects at import time, so the whole
auth decision can be unit-tested without a Hermes install.

Spec: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
and   https://core.telegram.org/bots/webapps#validating-data-for-third-party-use

* HMAC path (primary). ``secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)``;
  ``hash == hex(HMAC_SHA256(key=secret_key, msg=data_check_string))`` where the
  data-check-string is every received field *except* ``hash`` (``signature``
  included), sorted by key, ``key=value`` joined by ``\\n``.
* Ed25519 path (fallback). ``signature`` is a base64url Ed25519 signature by
  Telegram over ``f"{bot_id}:WebAppData\\n"`` + every received field *except*
  ``hash`` and ``signature``, sorted, ``key=value`` joined by ``\\n``.
* ``auth_date`` must be present and fresh (configurable window), and the user
  must be on an explicit allowlist. An empty allowlist rejects everyone.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
import urllib.parse
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

# Telegram's published Ed25519 public key for the production environment.
TELEGRAM_ED25519_PUBKEY_PROD = (
    "e7bf03a2fa4602af4580703d88dda5bb59f32ed8b02a56c187fe7d34caed242d"
)
# Key for Telegram's *test* environment. Not trusted unless explicitly enabled.
TELEGRAM_ED25519_PUBKEY_TEST = (
    "40055058a4ee38156a06562e52eece92a771bcd8346a8c4615cb7376eddf72ec"
)

# Real initData is well under 2 KB; anything bigger is not from Telegram.
MAX_INIT_DATA_LEN = 8192
DEFAULT_MAX_AGE_SEC = 3600
MIN_MAX_AGE_SEC = 60
MAX_MAX_AGE_SEC = 7 * 86400
# Tolerated clock skew for an auth_date slightly in the future.
FUTURE_SKEW_SEC = 60


class InitDataError(Exception):
    """Verification failed. ``reason`` is a short machine-readable code.

    The reason is for server-side logs and tests only; the HTTP layer
    returns one generic 403 so callers cannot probe which check failed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def parse_max_age(raw: Optional[str]) -> int:
    """Parse the freshness window from config, clamped to a sane range."""
    if raw is None or not str(raw).strip():
        return DEFAULT_MAX_AGE_SEC
    try:
        value = int(str(raw).strip())
    except ValueError:
        return DEFAULT_MAX_AGE_SEC
    return max(MIN_MAX_AGE_SEC, min(MAX_MAX_AGE_SEC, value))


def parse_allowlist(raw: Optional[str]) -> Tuple[str, ...]:
    """Comma-separated numeric Telegram user ids. Non-numeric entries are dropped."""
    if not raw:
        return ()
    out = []
    for piece in raw.split(","):
        piece = piece.strip()
        if piece.isdigit():
            out.append(piece)
    return tuple(out)


def bot_id_from_token(bot_token: str) -> Optional[str]:
    """Bot tokens look like ``<bot_id>:<secret>``."""
    head, sep, _ = (bot_token or "").partition(":")
    return head if sep and head.isdigit() else None


def parse_init_data(init_data: str) -> Dict[str, str]:
    """Decode the URL-encoded initData into a dict. Rejects duplicates."""
    if not isinstance(init_data, str) or not init_data:
        raise InitDataError("empty")
    if len(init_data) > MAX_INIT_DATA_LEN:
        raise InitDataError("too_long")
    try:
        pairs = urllib.parse.parse_qsl(
            init_data, keep_blank_values=True, strict_parsing=True
        )
    except ValueError:
        raise InitDataError("malformed") from None
    fields: Dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            raise InitDataError("duplicate_key")
        fields[key] = value
    return fields


def hmac_data_check_string(fields: Dict[str, str]) -> str:
    return "\n".join(f"{k}={v}" for k, v in sorted(fields.items()) if k != "hash")


def ed25519_data_check_string(fields: Dict[str, str], bot_id: str) -> str:
    body = "\n".join(
        f"{k}={v}"
        for k, v in sorted(fields.items())
        if k not in ("hash", "signature")
    )
    return f"{bot_id}:WebAppData\n{body}"


def compute_hash(fields: Dict[str, str], bot_token: str) -> str:
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(
        secret, hmac_data_check_string(fields).encode("utf-8"), hashlib.sha256
    ).hexdigest()


def check_hmac(fields: Dict[str, str], bot_token: str) -> bool:
    received = fields.get("hash", "")
    if not bot_token or not received:
        return False
    # Constant-time compare. Compare bytes: compare_digest raises TypeError on
    # non-ASCII str input, which would turn hostile input into a 500.
    expected = compute_hash(fields, bot_token).encode("ascii")
    return hmac.compare_digest(expected, received.lower().encode("utf-8"))


def check_ed25519(
    fields: Dict[str, str], bot_id: Optional[str], pubkeys_hex: Iterable[str]
) -> bool:
    sig_b64 = fields.get("signature", "")
    if not sig_b64 or not bot_id:
        return False
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        from cryptography.exceptions import InvalidSignature
    except ImportError:  # optional dependency; HMAC path still works
        return False
    try:
        sig = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
    except (binascii.Error, ValueError):
        return False
    if len(sig) != 64:
        return False
    message = ed25519_data_check_string(fields, bot_id).encode("utf-8")
    for key_hex in pubkeys_hex:
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex)).verify(sig, message)
            return True
        except (InvalidSignature, ValueError):
            continue
    return False


class FailureLimiter:
    """Per-key failed-attempt limiter for the public verify endpoint.

    After ``max_failures`` failures inside ``window_sec`` the key is blocked
    until the oldest failure ages out. Successful logins do not count.
    In-memory and per-process, which is enough for a single dashboard.
    """

    def __init__(self, max_failures: int = 10, window_sec: float = 300.0,
                 max_keys: int = 4096, clock=time.monotonic) -> None:
        self.max_failures = max_failures
        self.window_sec = window_sec
        self.max_keys = max_keys
        self._clock = clock
        self._failures: Dict[str, list] = {}

    def _prune(self, key: str, now: float) -> list:
        hits = [t for t in self._failures.get(key, []) if now - t < self.window_sec]
        if hits:
            self._failures[key] = hits
        else:
            self._failures.pop(key, None)
        return hits

    def retry_after(self, key: str) -> int:
        """Seconds until ``key`` may try again; 0 when not blocked."""
        now = self._clock()
        hits = self._prune(key, now)
        if len(hits) < self.max_failures:
            return 0
        return max(1, int(self.window_sec - (now - hits[0])) + 1)

    def record_failure(self, key: str) -> None:
        now = self._clock()
        if key not in self._failures and len(self._failures) >= self.max_keys:
            # Bound memory under a flood of distinct keys: drop the stalest key.
            stalest = min(self._failures, key=lambda k: self._failures[k][-1])
            self._failures.pop(stalest, None)
        self._prune(key, now)
        self._failures.setdefault(key, []).append(now)


def verify_init_data(
    init_data: str,
    *,
    bot_token: str,
    allowed_user_ids: Sequence[str],
    max_age_sec: int = DEFAULT_MAX_AGE_SEC,
    now: Optional[float] = None,
    bot_id: Optional[str] = None,
    ed25519_pubkeys: Sequence[str] = (TELEGRAM_ED25519_PUBKEY_PROD,),
) -> Dict[str, Any]:
    """Return the verified Telegram ``user`` object or raise :class:`InitDataError`.

    Order: parse → signature (HMAC, then Ed25519) → freshness → user → allowlist.
    """
    if not bot_token:
        raise InitDataError("bot_token_unset")
    allowed = {str(x).strip() for x in allowed_user_ids if str(x).strip()}
    if not allowed:
        # Fail closed: an unconfigured allowlist must not mean "everyone".
        raise InitDataError("allowlist_unset")

    fields = parse_init_data(init_data)

    signed = check_hmac(fields, bot_token)
    if not signed:
        signed = check_ed25519(
            fields, bot_id or bot_id_from_token(bot_token), ed25519_pubkeys
        )
    if not signed:
        raise InitDataError("bad_signature")

    raw_date = fields.get("auth_date", "")
    if not raw_date.isdigit():
        raise InitDataError("auth_date_missing")
    auth_date = int(raw_date)
    current = time.time() if now is None else now
    age = current - auth_date
    if age > max_age_sec:
        raise InitDataError("stale")
    if age < -FUTURE_SKEW_SEC:
        raise InitDataError("auth_date_in_future")

    try:
        user = json.loads(fields.get("user", ""))
    except ValueError:
        raise InitDataError("user_malformed") from None
    if not isinstance(user, dict):
        raise InitDataError("user_malformed")
    user_id = user.get("id")
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        raise InitDataError("user_malformed")

    if str(user_id) not in allowed:
        raise InitDataError("not_allowed")
    return user
