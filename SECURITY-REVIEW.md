# Security review: Telegram login path

Date: 22 October 2026. Scope: how the plugin turns Telegram `initData` into a Hermes dashboard session (`plugin/dashboard/tg_auth.py`, `plugin_api.py`), the endpoints reachable with that session, and the documented deployment.

References:
[validating data received via the Mini App](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app),
[validating data for third-party use](https://core.telegram.org/bots/webapps#validating-data-for-third-party-use),
Hermes Agent source at commit `81a55437f3f31a9f12a30c53b6c5d49d420898aa`.

Each finding is marked **Fixed** or **Not an issue**, with the reason. Tests named here are in `tests/`.

## Findings

### 1. Allowlist failed open — Fixed (critical)

Before: `if allowed and user_id not in allowed`. With neither `TELEGRAM_OWNER_ID` nor `TELEGRAM_ALLOWED_USERS` set, any Telegram user who opened the bot (anyone can) received the dashboard session token.

Now: an empty allowlist rejects every login (HTTP 503, "not configured"), and the two variables are combined instead of `OWNER_ID` silently hiding `ALLOWED_USERS`. Non-numeric entries are ignored. Tests: `test_empty_allowlist_fails_closed`, `test_unconfigured_allowlist_refuses`, `test_non_owner_rejected`.

### 2. Freshness check could be skipped — Fixed (high)

Before: `auth_date` defaulted to `0`, and `if auth_date and age > 86400` skipped the check for a missing or zero value. The window was a fixed 24 hours.

Now: `auth_date` must be a positive integer, the default window is 1 hour, configurable with `TELEGRAM_INITDATA_MAX_AGE` (clamped to 60 s to 7 days), and values more than 60 s in the future are rejected. Tests: `test_stale_auth_date_rejected`, `test_auth_date_zero_is_stale_not_skipped`, `test_missing_or_bad_auth_date_rejected`, `test_auth_date_far_in_future_rejected`, `test_freshness_window_configurable`.

### 3. Ed25519 fallback used the wrong data-check-string — Fixed (fail-closed bug)

Before: the signed string included `hash` and lacked the `"<bot_id>:WebAppData\n"` prefix, so no genuine Telegram signature could ever verify. It failed closed, so it was dead code rather than a bypass.

Now: built per spec (prefix, all fields except `hash` and `signature`, sorted, `\n`-joined), the signature must decode to 64 bytes, and `bot_id` comes from the bot token (or `TELEGRAM_BOT_ID`). Only Telegram's production key is trusted; the test-environment key is defined but not trusted by default. Both keys were checked against the spec. Tests generate their own key pair to prove the path works and that wrong bot ids, untrusted keys and the old string format are rejected.

### 4. HMAC data-check-string and secret key — Not an issue (verified)

`secret = HMAC_SHA256(key="WebAppData", msg=bot_token)`; the data-check-string is every received field except `hash`, `signature` included, sorted, `key=value` joined by `\n`. Both were already correct. Known-answer vectors were computed independently with `openssl` and are pinned in `test_known_answer_*`, including one with a `signature` field.

Parsing changed from splitting on `&` with `unquote` to `parse_qsl(strict_parsing=True)`, which also decodes `+` as a space, rejects malformed pairs, and duplicate keys are now refused.

### 5. Constant-time comparison could raise on hostile input — Fixed (low)

`hmac.compare_digest` was used, which is right, but on `str` arguments it raises `TypeError` for non-ASCII input, so `hash=é` produced a 500. Both sides are now compared as bytes. `test_hash_compared_with_compare_digest` fails if the comparison is replaced with `==`; `test_non_ascii_hash_does_not_raise_type_error` covers the crash.

### 6. No rate limiting on the public endpoint — Fixed (medium)

Added a per-client failure limiter: 10 failures in 5 minutes returns 429 with `Retry-After`. Successful logins are not counted. Behind a reverse proxy all requests share the proxy address, so it acts as a global limit, which is acceptable for a single-owner panel. Memory is bounded. Tests: `test_failure_limiter_*`, `test_rate_limited_after_repeated_failures`.

### 7. Malformed input — Fixed (low)

A `user` field that was valid JSON but not an object (or had a non-integer id) raised inside the handler (500). Input length was unbounded. Now: `init_data` is capped at 8 KB (422 at the HTTP layer), and every malformed shape is a plain rejection. Tests: `test_malformed_payloads`, `test_malformed_user_rejected`, `test_oversized_and_missing_body`.

### 8. Token returned on a GET request — Fixed (low)

`GET /auth/verify` accepted `initData` in a header and returned the session token in a GET response, which caches and proxies may store. The SPA never used it; it was removed. `POST /auth/verify` now sends `Cache-Control: no-store`. Every rejection returns the same 403 body so callers cannot tell which check failed; the reason is logged server-side.

### 9. Logging — Fixed (low)

No path logged `initData` or the token. The allowlist itself was logged on rejection (now only a reason code), and send failures echoed exception text to the client and logs (now a generic message and the exception type only, since a `urllib` error could carry the request URL, which contains the bot token). `test_initdata_never_logged` checks a login does not log `initData` contents or the bot token.

### 10. Reverse proxy exposed the whole dashboard API — Fixed in docs (high)

The README's Caddy example forwarded all of `/api/*`. The session token authorises the whole dashboard API, so this put every dashboard endpoint on the internet behind that one token, which is the exposure Hermes otherwise prevents by switching to its cookie gate for public hostnames. The example now forwards only `/api/plugins/telegram-app/*` and answers 404 for the rest of `/api/`. The SPA only calls the plugin prefix, so nothing else is needed.

### 11. Scope of the returned token — Not fixable in the plugin (documented)

The plugin returns the dashboard's own session token rather than minting a narrower one, because Hermes has no API for scoped tokens. It is valid until the dashboard restarts. The old response claimed `expires_at` = now + 24 h, which was false and has been removed. Mitigations: findings 1, 2, 6, 10 and 12.

### 12. Write endpoints broader than the UI needs — Fixed (medium)

- `POST /cron` accepted `no_agent`, `script` and `workdir`, which create jobs that run arbitrary commands without the agent. The UI never sends them; the endpoint now accepts agent jobs only and rejects unknown fields (`test_cron_create_refuses_script_jobs`). `PATCH /cron/{id}` also rejects unknown fields.
- `POST /command` let the caller post to any `chat_id`. It now only posts to allowlisted users and limits text to Telegram's 4096 characters (`test_command_refuses_non_allowlisted_chat`).

### 13. CORS — Not an issue

The plugin adds no CORS headers. Hermes' CORS middleware only allows `localhost`/`127.0.0.1` origins, and the SPA reaches the API same-origin through the proxy, so other sites cannot read responses. A cross-site `POST` with a JSON body needs a preflight, which is refused.

### 14. Path handling — Not an issue (verified)

`/logs` only accepts `agent`, `errors` or `gateway`. `/skills/{id}` resolves the path and refuses anything outside the skills directory. Tests: `test_logs_rejects_unknown_file`, `test_skill_path_traversal_refused`. Client-side, ids in URLs are now percent-encoded.

### 15. Development token in production builds — Fixed (low)

The SPA read `localStorage.devSessionToken` in every build. It is now honoured only by the Vite dev server.

### 16. Demo mode — designed to be off in production

Demo mode (sample data, no network) is compiled in only by `npm run build:demo` (output `dist-demo/`, not the `dist/` the installer deploys) or the dev server with `?demo=1`. In a production build the switch is a constant `false` and the demo module is not bundled; CI runs `npm run check:no-demo` against `dist/`. A banner is always shown while it is on.

## Sabotage checks

The tests were confirmed to catch regressions by breaking the code on purpose and restoring it:

| Change | Result |
|---|---|
| Remove the `age > max_age_sec` check | 4 tests fail (`test_stale_auth_date_rejected`, `test_default_window_is_one_hour`, `test_auth_date_zero_is_stale_not_skipped`, `test_invalid_login_is_generic_403`) |
| Replace `hmac.compare_digest` with `==` | `test_hash_compared_with_compare_digest` fails |
| Restore the old fail-open allowlist | `test_empty_allowlist_fails_closed` and `test_unconfigured_allowlist_refuses` fail |

## Residual risks

- Login depends on two private Hermes names (`_PUBLIC_API_PATHS`, `_SESSION_TOKEN`). A rename breaks login (fails closed: the verify route then sits behind the dashboard's auth and returns 401).
- Anyone on the allowlist has full control of the agent, as they would at the dashboard itself.
- The failure limiter is per process and in memory; it resets when the dashboard restarts.
