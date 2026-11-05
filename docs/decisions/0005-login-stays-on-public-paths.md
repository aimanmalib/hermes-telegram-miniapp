# 0005. Login stays on the dashboard's public-path set

Status: Accepted

## Context

The Mini App logs in through `POST /auth/verify`, which must answer a caller that has no dashboard credential yet: it
only holds Telegram `initData`. The plugin makes that route (and `/health`) reachable by adding both paths to the
private `hermes_cli.web_server._PUBLIC_API_PATHS` set (decision 0001).

Hermes v0.23.0 added an official bearer-token seam: a plugin registers a provider with
`ctx.register_dashboard_auth_provider`, and opts a route in with
`hermes_cli.dashboard_auth.token_auth.register_token_route`. The question was whether that seam can replace the
public-path registration. It cannot:

- `register_token_route` makes a route token-authable, not public. A request with no recognised bearer token gets 401
  from the seam itself, so the login route would still have to be public.
- Routes match by exact path only. `/sessions/{session_id}/messages`, `/cron/{job_id}` and the other parameterised
  routes cannot be registered, so the Mini App would need two kinds of credential.
- The seam does not exist in v0.22.4, the oldest release this plugin supports.

## Decision

Keep the public-path registration as the only login path. All reads of `_PUBLIC_API_PATHS` and `_SESSION_TOKEN` stay in
`plugin/dashboard/hermes_compat.py`, and the session token is read when each login is served, not copied at import.
`GET /health` reports `auth_mode`: `legacy-public-paths` while both paths are still in the dashboard's public set,
`unavailable` otherwise (login then fails closed with the dashboard's own 401). It also reports `hermes_version` and
`capabilities`, so a broken login after a Hermes upgrade can be diagnosed from one public request. The contract tests
(decision 0004) assert `legacy-public-paths` on every tested release.

The login checks from decision 0001 are unchanged.

## Consequences

A Hermes release that drops or renames `_PUBLIC_API_PATHS` still breaks login, but the contract tests fail on it and
`/health` shows it. If Hermes later supports prefix or pattern token routes, or a public route registration for plugins,
revisit this with a new decision; the value `token-seam` is reserved for `auth_mode` in that case.
