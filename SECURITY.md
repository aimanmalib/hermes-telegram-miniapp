# Security policy

This project hands a Hermes Agent dashboard session to a phone, so reports about the login path (`plugin/dashboard/tg_auth.py`, `/auth/verify`) are especially welcome.

## Reporting a vulnerability

Please report privately through GitHub: **Security → Report a vulnerability** on this repository ([private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)). Do not open a public issue for security problems.

Include what you found, how to reproduce it, and the affected commit. You should get a reply within 7 days. Fixes are released as soon as they are ready and credited in the advisory unless you prefer otherwise.

## Supported versions

Only the latest commit on `main` is supported.

## Scope

In scope: the plugin backend in `plugin/dashboard/`, the web app in `web/`, and the setup instructions in the README (for example a proxy configuration that exposes more than intended).

Out of scope: vulnerabilities in Hermes Agent itself (report those to [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent/security)), in Telegram, or in your own server configuration.

The design decisions behind the current auth model are documented in [SECURITY-REVIEW.md](SECURITY-REVIEW.md).
