# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.5.1] - 2026-11-06

No code change to the plugin's behaviour.

### Fixed

- **Security docs corrected.** 0.5.0 said a valid `initData` accepted on Hermes's other token routes "grants nothing
  new". Measured: with `HERMES_DASHBOARD_DRAIN_SECRET` set, `/api/gateway/drain` refuses the dashboard session token but
  lets a valid `initData` bearer through its token gate. ADR 0006, SECURITY-REVIEW.md and the README now say so. The
  plugin cannot scope this (a token provider is not told the route); it waits on NousResearch/hermes-agent#143507.

### Added

- Contract test `test_init_data_also_passes_core_token_routes`, which measures that behaviour against real Hermes and
  will fail when Hermes binds token routes to providers.
- `docs/brand/catalog-banner.png` (1200x600) for the Hermes plugin catalog card.

## [0.5.0] - 2026-11-06

Requires Hermes v0.23.0 or later (tested in CI). Passes `hermes plugins validate`, so the plugin can be listed in the
Hermes plugin catalog.

### Changed

- **Login uses Hermes's token-auth seam.** The Mini App sends its Telegram `initData` as `Authorization: Bearer …` on
  `POST /auth/verify`; a token provider registered by the plugin verifies it before the route runs. The plugin no
  longer adds anything to the dashboard's private public-path set ([decision 0006](docs/decisions/0006-login-through-the-token-seam.md)).
- `GET /health` now needs the session token. `auth_mode` is `token-seam` or `unavailable`.
- A refused login answers `401` from Hermes (was `403` from the plugin). A missing bot token or allowlist still
  answers `503`, now with Hermes's "auth provider unreachable" detail.
- `requires_hermes` is `>=0.23.0`; Hermes v0.22.x is no longer supported.
- `scripts/install.sh` checks that the login route answers `401` without `initData` instead of calling `/health`.

## [0.4.0] - 2026-11-06

Tested by running Hermes v0.22.4 and v0.23.0 in CI. `requires_hermes` stays `>=0.22.4`.

### Added

- **Stop a running cron job.** A job that is running shows a "running" badge and, on Hermes v0.23.0 or later, a
  Stop button with a confirmation. The backend route is `POST /cron/{id}/cancel`; on older Hermes it answers `501`
  with code `unsupported` and the button is hidden.
- **"Run missed jobs" per job** (`catch_up`). The job form shows the switch when Hermes stores the setting per job.
  It is sent only when changed, so saving a job never pins the global default. On a Hermes without it the field is
  dropped and the response carries a `catch_up_unsupported` warning.
- Each job in `GET /cron` has a boolean `running`.
- **English and Malay.** Every UI string lives in `web/src/i18n/{en,ms}.json`. The language is the saved choice,
  then the Telegram `language_code`, then English; an EN | BM switch sits at the bottom of the Status tab. Dates,
  numbers and relative times follow the language. No new package: a small `t()` helper does the lookup.
- API errors are shown as a readable sentence in the current language, with the HTTP status and the backend's
  detail. Sign-in refusals stay generic.
- `GET /health` reports `auth_mode` (`legacy-public-paths` or `unavailable`, checked on each request),
  `hermes_version` and `capabilities` (`cron_cancel`, `cron_catch_up`). Features are detected by probing Hermes,
  not by version number.
- Contract tests that install real Hermes releases and call the plugin through the Hermes dashboard app
  (`tests/contract/`). The releases under test are listed in `compat/hermes-versions.json`; CI runs one
  `hermes-contract` job per release (currently v0.22.4 and v0.23.0). Without Hermes installed the tests are skipped.

### Changed

- Hermes v0.23.0 added a bearer-token seam for plugin routes. It was evaluated and not adopted for login, for the
  reasons in [decision 0005](docs/decisions/0005-login-stays-on-public-paths.md). Login checks are unchanged.
- The backend is split into one module per tab (`plugin/dashboard/routes_*.py`). Every read of Hermes internals
  (public paths, the dashboard session token, `get_secret`, the Hermes home directory) now lives in
  `plugin/dashboard/hermes_compat.py`, so a Hermes upgrade that renames one of them breaks a single file.
  `plugin_api.py` only assembles the router.

### Fixed

- In the Cron tab, the new job form opened with its Cancel and Create buttons disabled.

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
