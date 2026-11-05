# 0001. Login security model

Status: Accepted

## Context

The Mini App controls an AI agent. A dashboard session token grants access to the whole dashboard API, so the login path is the
most sensitive part of the plugin.

## Decision

- `initData` is accepted only when its HMAC-SHA256 signature (key derived from `WebAppData` and the bot token) matches, compared in
  constant time. If that check fails, the Ed25519 signature is verified against Telegram's production public key.
- `auth_date` must be fresh (default one hour, `TELEGRAM_INITDATA_MAX_AGE`).
- The allowlist (`TELEGRAM_OWNER_ID` plus `TELEGRAM_ALLOWED_USERS`) fails closed: when it is empty, every login is refused with 503.
- Repeated failures are rate limited (429), rejections use a generic 403, and token responses are sent with `Cache-Control: no-store`.
- The proxy forwards only `/api/plugins/telegram-app/*`.

## Consequences

Any change to the login path updates [`SECURITY-REVIEW.md`](../../SECURITY-REVIEW.md) and adds regression tests under `tests/`.
The existing tests in `tests/test_tg_auth.py` are not weakened or removed.
