# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `POST /ask`: Ask Hermes. Queues one agent run whose answer Hermes delivers to an admin's Telegram chat: a one-shot
  cron job (`repeat=1`, `deliver=telegram:<admin id>`), prompt only. New plugin settings `ask_max_chars` (default
  2000) and `ask_max_pending` (default 1). Covered by a contract test against real Hermes. See
  [decision 0008](docs/decisions/0008-ask-hermes.md).

## [0.6.1] - 2026-11-08

Web and docs only. The plugin code is unchanged from 0.6.0; only its version lines moved.

### Added

- **Status gauges are green, amber or red** by band. The bands live in `web/src/config.json`, not in the tab.
- **Spend over the last 7 days** as a small line under Usage, built from the sessions list (each session counts on the
  day it was last active, the same rule `/usage` uses). Plain SVG, no chart library; the number of days is in
  `web/src/config.json`.
- **Demo video scripts** in `scripts/video/`: run a real Hermes dashboard on loopback with a throwaway home, seed it
  through the agent and the plugin API, record the phone screens with WebKit and build a portrait mp4 with ffmpeg.
  Text and timing live in `storyboard.json`. See `scripts/video/README.md`.

### Changed

- **Tab bar icons are drawn, not emoji.** Six outline icons copied from Tabler Icons (MIT, attribution in
  `web/src/icons.tsx`); no new package. They follow the Telegram theme through `currentColor`.
- **Telegram-style header.** The bot name sits over a status line read from `/health` ("Connected · v0.23.0",
  or "Hermes unreachable"), with the user's initial on the right. The tab bar uses the main background with a hairline.
- **Demo mode shows a small "Sample data" pill** in the header instead of the full-width yellow banner.
  `check:no-demo` now also looks for the pill text in production bundles.
- README screenshots recaptured with the new icons, header and gauges.

## [0.6.0] - 2026-11-08

### Breaking

- **Only the plugin-owned admin list can log in.** `TELEGRAM_ALLOWED_USERS` is Hermes's list of who may chat with the
  bot (the Telegram QR setup fills it in), and until now it also granted Mini App login, alerts and the send box. It
  is no longer read. Admins are `TELEGRAM_OWNER_ID` (one or more ids, comma-separated) plus the new plugin setting
  `admins`. Migration: if you relied on `TELEGRAM_ALLOWED_USERS`, put your id in `TELEGRAM_OWNER_ID`; otherwise login
  answers 503. [Decision 0007](docs/decisions/0007-admin-list-is-plugin-owned.md).

### Added

- **Plugin settings** in `config.yaml` under `plugins.entries.telegram-app.settings`, declared in `plugin.yaml`
  `config_schema`: `admins` (extra admins, applies on the next login) and `alerts_enabled` (default true, read at
  dashboard start).

### Deprecated

- `TELEGRAM_APP_ALERTS_DISABLED=1` still turns alerts off, with a warning in the dashboard log. Use
  `alerts_enabled: false`; the variable goes in the next minor release.

### Fixed

- The Hermes dashboard tab named `TELEGRAM_ALLOWED_USERS` as a way to log in. It now names `TELEGRAM_OWNER_ID` and the
  `admins` setting.

### Changed

- **README layout.** A centred header with the project logo, CI, release and licence badges and a one-line summary in
  English and Malay, a Malay section near the end, and absolute image links so the page renders the same anywhere. The
  logo source is `brand/logo.svg`; `brand/jana-aset.py` renders `brand/logo-512.png` and `brand/logo-64.png`. No code change.

## [0.5.3] - 2026-11-06

### Fixed

- **Login accepts only its own provider's principal.** On Hermes v0.23.0 the token gate admits any provider's
  principal on any token route, so `POST /auth/verify` with the drain secret as the bearer and a valid `initData`
  body returned the session token. It needed a valid `initData` anyway, so no access was gained, but the route now
  answers 403 unless our provider vouched for the bearer. Covered by a unit test and by
  `test_other_token_credentials_cannot_log_in` against real Hermes.

## [0.5.2] - 2026-11-06

### Added

- **Scoped login, ready for Hermes route scopes.** Every principal the plugin's token provider issues carries the scope
  `telegram-app`. Where Hermes's `register_token_route` takes `scope` (proposed in NousResearch/hermes-agent#146551),
  the login route demands it. Tested against Hermes `main` with that PR merged: `/api/gateway/drain` refuses an
  `initData` bearer (403) and the drain secret cannot open the login route (403). Detected by probing the function
  signature; on v0.23.0 nothing changes.
- Contract test `test_other_token_credentials_cannot_log_in`; the drain test is now `test_init_data_and_core_token_routes`
  and checks the result on both kinds of seam.

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
