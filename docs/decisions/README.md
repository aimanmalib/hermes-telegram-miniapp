# Architecture decisions

Short records of the decisions that shape this project. Each one states the context, the decision, and how to undo it.
Add a new file with the next number when a decision changes; do not rewrite an accepted record, supersede it.

| # | Decision | Status |
|---|---|---|
| [0001](0001-login-security-model.md) | Login: Telegram `initData` HMAC, Ed25519 fallback, fail-closed allowlist | Accepted |
| [0002](0002-backend-module-layout.md) | Backend split into one module per tab, Hermes internals behind `hermes_compat.py` | Accepted |
| [0003](0003-no-new-runtime-dependencies.md) | No new runtime packages in the web app | Accepted |
