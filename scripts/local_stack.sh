#!/usr/bin/env bash
# Start/stop the native local stack (UI + bridge) against an existing ComfyUI.
# Usage: scripts/local_stack.sh start|stop|status
# Reads .env.local. PYTHON defaults to the interpreter that runs your ComfyUI.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
RUN=$ROOT/.runtime; mkdir -p "$RUN/logs"
PYTHON=${PYTHON:-python3}
UI_PORT=${UI_PORT:-8188}
BRIDGE_PORT=${BRIDGE_PORT:-8766}

stop_one() {
  local f=$RUN/$1.pid
  [ -f "$f" ] || return 0
  local pid; pid=$(cat "$f")
  if kill -0 "$pid" 2>/dev/null; then
    kill -- -"$pid" 2>/dev/null || kill "$pid"
    for _ in $(seq 1 10); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  fi
  rm -f "$f"
}

case "${1:-}" in
  start)
    stop_one bridge; stop_one ui
    (cd backend && setsid "$PYTHON" -m uvicorn server:app --host 127.0.0.1 --port "$BRIDGE_PORT" \
      --env-file ../.env.local > "$RUN/logs/bridge.log" 2>&1 & echo $! > "$RUN/bridge.pid")
    setsid npm run start -- --port "$UI_PORT" > "$RUN/logs/ui.log" 2>&1 & echo $! > "$RUN/ui.pid"
    echo "bridge pid $(cat "$RUN/bridge.pid"), ui pid $(cat "$RUN/ui.pid"); logs in $RUN/logs"
    ;;
  stop) stop_one bridge; stop_one ui ;;
  status)
    for u in "http://127.0.0.1:$BRIDGE_PORT/jobs" "http://127.0.0.1:$UI_PORT/"; do
      echo "$u $(curl -s -m 10 -o /dev/null -w '%{http_code}' "$u" || true)"
    done ;;
  *) echo "usage: $0 start|stop|status"; exit 1 ;;
esac
