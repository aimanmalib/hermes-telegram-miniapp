# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.0] - 2026-10-23

### Changed

- Credentials and settings (`TELEGRAM_BOT_TOKEN`, the allowlist, `TELEGRAM_INITDATA_MAX_AGE`, `TELEGRAM_BOT_ID`) are
  read through Hermes's `agent.secret_scope.get_secret` instead of parsing `~/.hermes/.env` directly. This honours
  the active profile when one dashboard serves several. Values saved through Hermes apply at once, but **after
  editing `.env` by hand, restart the dashboard**; the plugin used to re-read the file on every request.

### Added

- `plugin/plugin.yaml` and `plugin/__init__.py`, so `hermes plugins validate plugin/` can check the plugin. One check
  still fails: login adds its two routes to Hermes's private `_PUBLIC_API_PATHS`, because Hermes has no public way
  for a plugin to declare an unauthenticated or plugin-authenticated route.

## [0.2.0] - 2026-10-22

First public release.

### Security

- An empty allowlist (`TELEGRAM_OWNER_ID` / `TELEGRAM_ALLOWED_USERS` unset) now refuses every login. Before, any
  Telegram user who opened the bot received the dashboard token.
- `auth_date` is required and must be fresh (default 1 hour, `TELEGRAM_INITDATA_MAX_AGE`); future dates are rejected.
- The Ed25519 fallback now signs the string Telegram specifies (it previously could never verify).
- Login is rate-limited; malformed input returns 4xx instead of 500; the token is no longer returned on GET; the
  allowlist is no longer logged; `/command` only posts to allowlisted users; the example proxy only forwards
  `/api/plugins/telegram-app/*`. Details: [SECURITY-REVIEW.md](SECURITY-REVIEW.md).

### Fixed

- Aligned with the Hermes Agent dashboard plugin contract as of v0.22.4 (`plugins.enabled`, session count, cron job
  format, dashboard tab file).

### Added

- Demo mode (`?demo=1` in dev, `npm run build:demo`) with sample data; production builds are checked to contain none.
- Tests (Python plugin + web), CI on GitHub Actions and Depot CI, Dependabot, security policy, screenshots.

## [0.1.0]

Initial version (before the public release).
