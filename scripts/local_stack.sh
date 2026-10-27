#!/usr/bin/env bash
# Start/stop the native local stack (UI + bridge) against an existing ComfyUI.
# Usage: scripts/local_stack.sh start|stop|status
# Reads .env.local. PYTHON defaults to the interpreter that runs your ComfyUI.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
RUN=$ROOT/.runtime; mkdir -p "$RUN/logs"
PYTHON=${PYTHON:-python3}
# A relative path (.venv/bin/python) must survive the cd into backend/.
case $PYTHON in /*) ;; */*) PYTHON=$ROOT/$PYTHON ;; esac
UI_PORT=${UI_PORT:-8188}
BRIDGE_PORT=${BRIDGE_PORT:-8766}

stop_one() {  # name port
  local f=$RUN/$1.pid pids
  pids="$( [ -f "$f" ] && cat "$f" ) $(ss -ltnpH "sport = :$2" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | sort -u || true)"
  for pid in $pids; do kill "$pid" 2>/dev/null || true; done
  for _ in $(seq 1 10); do ss -ltnH "sport = :$2" | grep -q . || break; sleep 1; done
  rm -f "$f"
}

case "${1:-}" in
  start)
    stop_one bridge "$BRIDGE_PORT"; stop_one ui "$UI_PORT"
    (cd backend && nohup "$PYTHON" -m uvicorn server:app --host 127.0.0.1 --port "$BRIDGE_PORT" \
      --env-file ../.env.local > "$RUN/logs/bridge.log" 2>&1 < /dev/null & echo $! > "$RUN/bridge.pid")
    # The UI reaches the bridge through HENGE_BACKEND_URL; point it at this BRIDGE_PORT.
    HENGE_BACKEND_URL=${HENGE_BACKEND_URL:-http://127.0.0.1:$BRIDGE_PORT} nohup node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port "$UI_PORT" > "$RUN/logs/ui.log" 2>&1 < /dev/null & echo $! > "$RUN/ui.pid"
    echo "bridge pid $(cat "$RUN/bridge.pid"), ui pid $(cat "$RUN/ui.pid"); logs in $RUN/logs"
    ;;
  stop) stop_one bridge "$BRIDGE_PORT"; stop_one ui "$UI_PORT" ;;
  status)
    for u in "http://127.0.0.1:$BRIDGE_PORT/jobs" "http://127.0.0.1:$UI_PORT/"; do
      echo "$u $(curl -s -m 10 -o /dev/null -w '%{http_code}' "$u" || true)"
    done ;;
  *) echo "usage: $0 start|stop|status"; exit 1 ;;
esac
