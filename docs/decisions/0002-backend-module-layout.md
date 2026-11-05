# 0002. Backend module layout

Status: Accepted

## Context

`plugin/dashboard/plugin_api.py` had grown to almost 1,000 lines and mixed every tab's routes with the code that reaches into Hermes
internals. Hermes upgrades could break the plugin anywhere in that file.

## Decision

- One module per tab: `routes_auth.py` (public `/health` and `/auth/verify`), `routes_status.py`, `routes_sessions.py`,
  `routes_cron.py`, `routes_knowledge.py`, `routes_logs.py`, `routes_send.py`, `routes_alerts.py`.
- `settings.py` holds credentials, version and start time.
- `hermes_compat.py` is the only module that touches Hermes internals (public API paths, the session token, secrets, `HERMES_HOME`).
- `plugin_api.py` loads `hermes_compat` first, then the sibling modules, and only assembles the router.
- `tests/test_layout.py` pins the route table and fails if a Hermes internal name appears outside `hermes_compat.py`.

## Consequences

Supporting a new Hermes release means changing `hermes_compat.py`, not the route modules. The split changed no endpoint or behaviour,
so it can be reverted as a single commit (`3135331`).
