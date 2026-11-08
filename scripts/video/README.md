# Demo video rig

Scripts for recording the demo video against a real Hermes Agent, not the demo build.

| File | What it does |
|------|--------------|
| `rig.sh` | `up` / `down` / `status`: runs `hermes dashboard` on loopback with a throwaway Hermes home that has this plugin installed (symlink) and enabled. |
| `seed.py` | Makes real data in that home: one agent turn per prompt, cron jobs created through the plugin's `POST /cron`, and one run of the due jobs. Writes a summary JSON. |
| `seed.json` | The prompts and cron jobs `seed.py` uses. Edit this, not the script. |

## Environment

| Variable | Meaning |
|----------|---------|
| `HERMES_BIN` | `hermes` executable, v0.23.0 or later. A tag checkout with `uv sync` works. |
| `HERMES_HOME` | Hermes home owned by the rig. Never point it at your real one: `rig.sh up` rewrites its `config.yaml` and `.env`. |
| `MODEL_BASE_URL`, `MODEL_NAME` | OpenAI-compatible endpoint and model the agent calls. |
| `MODEL_API_KEY_FILE`, `MODEL_API_KEY_VAR` | `KEY=VALUE` file holding the endpoint key, and the variable name in it (default `MODEL_API_KEY`). The key is copied to `$HERMES_HOME/.env` (mode 0600) and never printed. |
| `OUT_DIR` | PID file, dashboard log, and `dashboard-token` (mode 0600). |
| `DASHBOARD_PORT` | Loopback port, default `9119` (the Vite dev proxy target). |
| `RIG_SUMMARY` | Where `seed.py` writes its summary, default `$OUT_DIR/rig.json`. |
| `RIG_SUMMARY_ALIASES` | Optional `key=alias,...`: also write these summary keys under another name. |
| `SEED_SUMMARY_ONLY` | `1` = seed nothing, only read the running rig back and rewrite the summary. |

## Use

```sh
set -a; . ./rig.env; set +a            # your values for the variables above
scripts/video/rig.sh up                # the first start builds the Hermes web UI (a few minutes)
python3 scripts/video/seed.py
cd web && npm run dev                  # then set localStorage.devSessionToken to $OUT_DIR/dashboard-token
scripts/video/rig.sh down
```

`localStorage.devSessionToken` is the existing development login path: only the Vite dev server reads it,
production builds ignore it, and Telegram login (`/auth/verify`) is unchanged.

The summary's `live` is true only when `/health` answered from a running Hermes and at least one real
session exists. The video may say "real Hermes" only when it is true.
