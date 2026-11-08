#!/usr/bin/env bash
# Run a real Hermes dashboard with this plugin installed, for recording the demo video.
#
#   scripts/video/rig.sh up       start the dashboard on loopback (idempotent)
#   scripts/video/rig.sh down     stop the processes this script started
#   scripts/video/rig.sh status   show whether the rig is up and what /health says
#
# Everything host-specific comes from the environment (see scripts/video/README.md):
#   HERMES_BIN          hermes executable (a v0.23.0+ install)
#   HERMES_HOME         throwaway Hermes home owned by the rig (never your real one)
#   MODEL_BASE_URL      OpenAI-compatible endpoint the agent calls
#   MODEL_NAME          model id at that endpoint
#   MODEL_API_KEY_FILE  dotenv file holding the endpoint key (read, never printed)
#   MODEL_API_KEY_VAR   variable name inside that file (default MODEL_API_KEY)
#   OUT_DIR             where the pid, log and dashboard token file go
#   DASHBOARD_PORT      loopback port (default 9119, what the Vite dev proxy expects)
#   RIG_READY_TIMEOUT   seconds to wait for /health (default 900; the first start builds the web UI)
#
# The dashboard session token is written to $OUT_DIR/dashboard-token (mode 0600). The Vite dev
# server reads it through localStorage.devSessionToken; production builds ignore that key.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PLUGIN_NAME="telegram-app"
PORT="${DASHBOARD_PORT:-9119}"
HOST="127.0.0.1"

need() {
  local name
  for name in "$@"; do
    if [ -z "${!name:-}" ]; then
      echo "rig: $name is not set (see scripts/video/README.md)" >&2
      exit 2
    fi
  done
}

pid_alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }

health() {
  curl -s -m 5 -H "X-Hermes-Session-Token: $(cat "$OUT_DIR/dashboard-token")" \
    "http://$HOST:$PORT/api/plugins/$PLUGIN_NAME/health"
}

write_home() {
  mkdir -p "$HERMES_HOME/plugins"
  chmod 700 "$HERMES_HOME"
  ln -sfn "$REPO/plugin" "$HERMES_HOME/plugins/$PLUGIN_NAME"
  # The key stays in .env; config.yaml only names the variable.
  cat > "$HERMES_HOME/config.yaml" <<EOF
model:
  provider: custom
  base_url: $MODEL_BASE_URL
  default: $MODEL_NAME
  api_key: \${MODEL_API_KEY}
  streaming: false
plugins:
  enabled:
    - $PLUGIN_NAME
  entries:
    $PLUGIN_NAME:
      settings:
        alerts_enabled: false
EOF
  local var="${MODEL_API_KEY_VAR:-MODEL_API_KEY}" key
  key="$(sed -n "s/^${var}=//p" "$MODEL_API_KEY_FILE" | head -n 1 | sed -e 's/^["'\'']//' -e 's/["'\'']$//')"
  if [ -z "$key" ]; then
    echo "rig: $var not found in MODEL_API_KEY_FILE" >&2
    exit 2
  fi
  (umask 077 && printf 'MODEL_API_KEY=%s\n' "$key" > "$HERMES_HOME/.env")
  if [ ! -s "$OUT_DIR/dashboard-token" ]; then
    (umask 077 && python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$OUT_DIR/dashboard-token")
  fi
}

cmd_up() {
  need HERMES_BIN HERMES_HOME MODEL_BASE_URL MODEL_NAME MODEL_API_KEY_FILE OUT_DIR
  mkdir -p "$OUT_DIR"
  if pid_alive "$OUT_DIR/dashboard.pid"; then
    echo "rig: already up (pid $(cat "$OUT_DIR/dashboard.pid"), port $PORT)"
    return 0
  fi
  if [ -n "$(ss -Hltn "sport = :$PORT")" ]; then
    echo "rig: port $PORT is taken by another process; set DASHBOARD_PORT" >&2
    exit 1
  fi
  write_home
  (
    cd "$OUT_DIR"
    HERMES_HOME="$HERMES_HOME" HERMES_DASHBOARD_SESSION_TOKEN="file:$OUT_DIR/dashboard-token" \
      setsid nohup "$HERMES_BIN" dashboard --host "$HOST" --port "$PORT" --skip-build --no-open \
      > "$OUT_DIR/dashboard.log" 2>&1 < /dev/null &
    echo $! > "$OUT_DIR/dashboard.pid"
  )
  local deadline=$(($(date +%s) + ${RIG_READY_TIMEOUT:-900}))
  until health 2>/dev/null | grep -q '"ok":true'; do
    if ! pid_alive "$OUT_DIR/dashboard.pid"; then
      echo "rig: dashboard exited; last log lines:" >&2
      tail -n 20 "$OUT_DIR/dashboard.log" >&2
      exit 1
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo "rig: /health not ready in time" >&2
      exit 1
    fi
    sleep 5
  done
  echo "rig: up at http://$HOST:$PORT (pid $(cat "$OUT_DIR/dashboard.pid"))"
  health
  echo
}

cmd_down() {
  need HERMES_HOME OUT_DIR
  if pid_alive "$OUT_DIR/dashboard.pid"; then
    # setsid made the dashboard a session leader: signal its whole group (it re-executes a child).
    kill -- "-$(cat "$OUT_DIR/dashboard.pid")" 2>/dev/null || kill "$(cat "$OUT_DIR/dashboard.pid")"
    echo "rig: dashboard stopped"
  fi
  rm -f "$OUT_DIR/dashboard.pid"
  # Hermes may start an idle-exit gateway for this home; stop it only if it belongs to this home.
  local gw="$HERMES_HOME/gateway.pid" gpid
  if [ -f "$gw" ]; then
    gpid="$(python3 - "$gw" "$HERMES_HOME" <<'PY'
import json, os, sys
try:
    rec = json.load(open(sys.argv[1]))
except (OSError, ValueError):
    sys.exit(0)
if os.path.realpath(rec.get("hermes_home", "")) == os.path.realpath(sys.argv[2]):
    print(rec.get("pid", ""))
PY
)"
    if [ -n "$gpid" ] && kill -0 "$gpid" 2>/dev/null; then
      kill "$gpid" && echo "rig: gateway stopped"
    fi
  fi
}

cmd_status() {
  need OUT_DIR
  if pid_alive "$OUT_DIR/dashboard.pid"; then
    echo "rig: up (pid $(cat "$OUT_DIR/dashboard.pid"), port $PORT)"
    health
    echo
  else
    echo "rig: down"
    return 1
  fi
}

case "${1:-}" in
  up) cmd_up ;;
  down) cmd_down ;;
  status) cmd_status ;;
  *)
    echo "usage: $0 up|down|status" >&2
    exit 2
    ;;
esac
