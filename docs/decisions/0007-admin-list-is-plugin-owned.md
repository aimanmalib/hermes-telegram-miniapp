# 0007. The admin list is plugin-owned

Status: Accepted. Narrows the allowlist in [0001](0001-login-security-model.md).

## Context

Until 0.5.3 the login allowlist was `TELEGRAM_OWNER_ID` plus `TELEGRAM_ALLOWED_USERS`. In Hermes,
`TELEGRAM_ALLOWED_USERS` is the list of people who may chat with the bot, and the Telegram QR setup fills it in. So
anyone allowed to chat with the agent could also open the Mini App and receive the dashboard session token, which
reads sessions, memory and logs and creates cron jobs. Chatting with an agent and administering it are different
grants. A plugin catalog review raised this.

Hermes v0.23.0 has a supported per-plugin config path: `config_schema` in `plugin.yaml` declares the keys, and
`PluginContext.get_config(key, default)` reads `plugins.entries.<plugin>.settings.<key>` from `config.yaml` on every
call, so an edit applies without a restart.

## Decision

- The admin list is `TELEGRAM_OWNER_ID` (one id or several, comma-separated) plus the plugin setting `admins` (a YAML
  list or a comma-separated string). `settings.admin_user_ids()` is the only source.
- `TELEGRAM_ALLOWED_USERS` is not read anywhere in `plugin/`, in any form: no fallback, no compatibility flag.
- Login, the provider on the token route, alert delivery and the send box (`POST /command`) all use the admin list.
  Alerts go to the first admin.
- An empty admin list keeps the fail-closed behaviour of 0001: every login is refused with 503, and the dashboard log
  says `refusing login, allowlist_unset (set TELEGRAM_BOT_TOKEN and TELEGRAM_OWNER_ID or the plugin setting admins)`.
- `register(ctx)` binds the plugin context through `hermes_compat.bind_plugin_context`; settings are read only through
  `hermes_compat.plugin_setting` (decision 0002: Hermes names stay in that module). With no context every setting
  reads as its default, which for `admins` means no extra admins.
- `TELEGRAM_APP_ALERTS_DISABLED`: replaced by the plugin setting `alerts_enabled` (bool, default true), since a
  supported config path now exists. `hermes dashboard` runs plugin discovery before it imports the web server, so the
  setting is read when the alerts route mounts. The old variable still turns alerts off for 0.6.x, with a deprecation
  warning in the dashboard log, and is removed in the next minor release.

## Consequences

- Breaking for installs that set only `TELEGRAM_ALLOWED_USERS`: login answers 503 until the owner's id is in
  `TELEGRAM_OWNER_ID` or `admins`. The release is 0.6.0 and the changelog gives the one-line migration.
- Tested in unit tests (`test_allowed_users_only_is_refused`, `test_allowed_users_alone_is_unconfigured`,
  `test_admins_setting_extends_the_admin_list`, `test_alerts_route_starts_the_watcher_only_when_enabled`) and against
  real Hermes (`test_allowed_users_do_not_grant_login`, `test_admins_plugin_setting_grants_login`,
  `test_alerts_setting_applies_at_mount`).

## Undo

Revert the commits that introduced `admin_user_ids` and `alerts_enabled`. Do not restore the union with
`TELEGRAM_ALLOWED_USERS` without a new decision: it grants the panel to everyone who can chat with the bot.
