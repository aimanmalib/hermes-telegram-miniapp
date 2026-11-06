# 0006. Login goes through Hermes's token-auth seam

Status: Accepted. Supersedes [0005](0005-login-stays-on-public-paths.md).

## Context

Decision 0005 kept the login route public by adding it to the private `hermes_cli.web_server._PUBLIC_API_PATHS` set.
`hermes plugins validate` (Hermes v0.23.0) refuses that as a core override, so the plugin could not be listed in the
Hermes plugin catalog, whose CI runs the validator.

0005 rejected the token seam because "a request with no recognised bearer token gets 401", so the login route would
still need to be public. That misses one option: the caller's credential can *be* the bearer. The Mini App already
holds Telegram `initData`, and checking it is exactly what a token provider does.

## Decision

- `plugin/__init__.py` registers a token-only provider (`telegram-app-initdata`) with
  `ctx.register_dashboard_auth_provider` and marks `POST /api/plugins/telegram-app/auth/verify` as a token route.
- The Mini App sends `Authorization: Bearer <initData>`. The provider runs the full check from decision 0001
  (signature, freshness, allowlist) and returns `None` for anything else, so the seam answers 401 before the route
  runs. The route then verifies the body's `initData` again, with the failure limiter, and returns the session token.
- Nothing is added to the dashboard's public paths. `/health` now needs the session token.
- `requires_hermes` rises to `>=0.23.0`, the first release with the seam. `auth_mode` reports `token-seam` or
  `unavailable`.
- Exact-path matching does not matter: only the login route uses the seam; every other route takes the session token.

## Consequences

- The plugin passes `hermes plugins validate` (private-import warnings remain: `_SESSION_TOKEN`, `register_token_route`,
  `cron.jobs`).
- Hermes asks every token provider on every token route, so a valid `initData` is also accepted on core token routes.
  Today the only one is `/api/gateway/drain`, and only when `HERMES_DASHBOARD_DRAIN_SECRET` is set. That route refuses
  the dashboard session token, so this is one endpoint the `initData` holder could not reach before (corrected in
  0.5.1; 0.5.0 said "nothing new", which was wrong). It is weaker than what the same holder can already do: create
  agent cron jobs. The plugin cannot close it, because a provider is not told which route it is vouching for; the fix
  is provider-bound token routes in Hermes (NousResearch/hermes-agent#143507).
  `test_init_data_also_passes_core_token_routes` measures it and will flip when Hermes changes.
- A seam rejection is 401 (was 403). The Mini App shows its "close and reopen" message, which also fixes the most
  common cause, stale `initData`.
- Hermes v0.22.x is no longer supported.

## Undo

Revert the 0.5.0 commit that introduced this record; 0005's public-path registration comes back with it.
