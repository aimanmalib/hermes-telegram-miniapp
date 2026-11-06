# Architecture decisions

Short records of the decisions that shape this project. Each one states the context, the decision, and how to undo it.
Add a new file with the next number when a decision changes; do not rewrite an accepted record, supersede it.

| # | Decision | Status |
|---|---|---|
| [0001](0001-login-security-model.md) | Login: Telegram `initData` HMAC, Ed25519 fallback, fail-closed allowlist | Accepted |
| [0002](0002-backend-module-layout.md) | Backend split into one module per tab, Hermes internals behind `hermes_compat.py` | Accepted |
| [0003](0003-no-new-runtime-dependencies.md) | No new runtime packages in the web app | Accepted |
| [0004](0004-contract-tests-against-real-hermes.md) | Contract tests run real Hermes releases (`compat/hermes-versions.json`) | Accepted |
| [0005](0005-login-stays-on-public-paths.md) | Login stays on the public-path set; Hermes v0.23.0 token seam not used | Superseded by 0006 |
| [0006](0006-login-through-the-token-seam.md) | Login goes through Hermes's token-auth seam (`initData` as the bearer) | Accepted |
