# 0003. No new runtime packages in the web app

Status: Accepted

## Context

The web app runs inside Telegram with access to an agent dashboard. Each runtime package adds supply-chain surface and bundle size.
Features such as two-language UI text need only a small amount of code.

## Decision

Do not add runtime packages (for example `i18next`, a Telegram Mini Apps SDK, or a UI kit). Write small helpers instead.
A dev dependency is allowed only when a test needs it, and the reason is noted in the pull request.

## Consequences

Translations use a small `t()` helper with JSON message files. Revisit this record if a feature needs code that would be larger and
riskier to maintain than a vetted package.
