# Contributing

Thanks for helping. This project controls an AI agent from a phone, so changes to the login path get extra scrutiny.

## Set up

```bash
# Plugin (Python 3.11+)
pip install -r requirements-dev.txt
python -m pytest

# Web app (Node 22)
cd web && npm ci
npm run typecheck && npm test && npm run build
npm run check:no-demo        # production build must not contain demo code
npm run dev                  # Vite on :5173; add ?demo=1 to see sample data without a Hermes server
```

## Before you open a pull request

- Run the commands above; CI runs the same steps.
- **Anything touching `plugin/dashboard/tg_auth.py` or the `/auth/verify` route needs a test** that fails without
  your change. Read [SECURITY-REVIEW.md](SECURITY-REVIEW.md) first: the allowlist fails closed, `auth_date` is
  required and must be fresh, and signatures are compared in constant time. Don't weaken these.
- Keep the plugin inside `~/.hermes/plugins/telegram-app/`: no patches to upstream Hermes files.
- One topic per pull request; describe how you tested it.

## Reporting security issues

Please don't open a public issue. Use
[private vulnerability reporting](https://github.com/aimanmalib/hermes-telegram-miniapp/security/advisories/new).

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE) and that you follow
the [Code of Conduct](CODE_OF_CONDUCT.md).
