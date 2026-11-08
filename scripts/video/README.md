# Demo video rig

Scripts for recording the demo video against a real Hermes Agent, not the demo build.

| File | What it does |
|------|--------------|
| `rig.sh` | `up` / `down` / `status` / `gateway`: runs `hermes dashboard` on loopback with a throwaway Hermes home that has this plugin installed (symlink) and enabled; `gateway` adds `hermes gateway run`, whose ticker fires cron jobs and Asks. |
| `bot_api_stub.py` | A loopback stand-in for the Telegram Bot API. With `RIG_ADMIN_ID` set, the rig points Hermes's Telegram adapter at it through the adapter's own `base_url` setting (meant for a self-hosted Bot API server), so an Ask really runs and is really delivered, into a JSON-lines file instead of Telegram. |
| `seed.py` | Makes real data in that home: one agent turn per prompt, cron jobs created through the plugin's `POST /cron`, and one run of the due jobs. Writes a summary JSON. |
| `seed.json` | The prompts and cron jobs `seed.py` uses. Edit this, not the script. |
| `storyboard.json` | Shots, captions, durations, phone frame size and the strings that must never be on screen (`FORBID_ON_SCREEN` adds your own, such as host names). Edit this, not the scripts. |
| `record.py` | Records each screen shot with WebKit (iPhone 13, touch ripples, no pointer) against the Vite dev server, renders the cards and frames (`frames.py`), and writes `manifest.json`. Stops if a forbidden string or the token appears in the kept part of a shot. |
| `telegram-mock.html` | The chat screen in the opening and Ask shots. It is a mock, labelled "Mock" for the whole shot; the panel inside it is the real app, and the reply shown in the Ask shot is the text Hermes delivered to the stand-in. |
| `audio.py` | Writes the soundtrack (a generated chord bed, a tick per recorded tap, a chime when an answer arrives; no third-party audio) and the subtitles (one cue per caption) from `manifest.json`. |
| `compose.sh` | Builds the mp4 from `manifest.json` with ffmpeg: H.264, yuv420p, AAC soundtrack normalised to the storyboard's loudness, an English subtitle track, `+faststart`, and the same subtitles as a `.srt` next to the video. `SAMPLE_DIR=<dir>` also saves one frame per shot. |

## Environment

| Variable | Meaning |
|----------|---------|
| `HERMES_BIN` | `hermes` executable, v0.23.0 or later. A tag checkout with `uv sync` works. |
| `HERMES_HOME` | Hermes home owned by the rig. Never point it at your real one: `rig.sh up` rewrites its `config.yaml` and `.env`. |
| `MODEL_BASE_URL`, `MODEL_NAME` | OpenAI-compatible endpoint and model the agent calls. |
| `MODEL_API_KEY_FILE`, `MODEL_API_KEY_VAR` | `KEY=VALUE` file holding the endpoint key, and the variable name in it (default `MODEL_API_KEY`). The key is copied to `$HERMES_HOME/.env` (mode 0600) and never printed. |
| `OUT_DIR` | PID file, dashboard log, and `dashboard-token` (mode 0600). |
| `DASHBOARD_PORT` | Loopback port, default `9119` (the Vite dev proxy target). |
| `RIG_ADMIN_ID` | A made-up Telegram user id, written as `TELEGRAM_OWNER_ID` so Ask has an admin chat. Also turns on the Bot API stand-in. |
| `BOT_API_PORT` | Loopback port of the stand-in, default `9180`. Messages go to `$OUT_DIR/bot-api-messages.jsonl`. |
| `RIG_SUMMARY` | Where `seed.py` writes its summary, default `$OUT_DIR/rig.json`. |
| `RIG_SUMMARY_ALIASES` | Optional `key=alias,...`: also write these summary keys under another name. |
| `SEED_SUMMARY_ONLY` | `1` = seed nothing, only read the running rig back and rewrite the summary. |

## Use

```sh
set -a; . ./rig.env; set +a            # your values for the variables above
scripts/video/rig.sh up                # the first start builds the Hermes web UI (a few minutes)
scripts/video/rig.sh gateway           # cron ticker + Telegram adapter (needs python-telegram-bot in Hermes's env)
python3 scripts/video/seed.py
cd web && npm run dev                  # then set localStorage.devSessionToken to $OUT_DIR/dashboard-token
scripts/video/rig.sh down
```

Recording, with the rig up and the Vite dev server on port 5173:

```sh
VIDEO_OUT=out uv run --with playwright==1.58.0 --with pillow python scripts/video/record.py
VIDEO_OUT=out VIDEO_FILE=out/demo.mp4 SAMPLE_DIR=out/samples scripts/video/compose.sh
```

The Ask shot waits for Hermes's cron ticker (up to a minute) and keeps two parts of the recording: asking, and
the answer arriving. A chip over the second part says the wait was skipped; nothing is sped up or replayed.

`RECORD_SHOTS=brain,logs` re-records only those shots and keeps the others from the last manifest. A caption marked
`needs_live` is refused unless the rig summary says `live: true`. Cron jobs run only while a Hermes gateway
serves the rig's home (`hermes gateway run`); the dashboard alone shows them but does not fire them.

`localStorage.devSessionToken` is the existing development login path: only the Vite dev server reads it,
production builds ignore it, and Telegram login (`/auth/verify`) is unchanged.

The summary's `live` is true only when `/health` answered from a running Hermes and at least one real
session exists. The video may say "real Hermes" only when it is true.
