#!/bin/bash
# Hand a task to Claude Code with the Henge MCP and the agent rules, unattended:
#   mcp/examples/run_claude.sh mcp/examples/two-cut-swap/task.txt /path/to/clip.mp4 [picture ...]
# In the task, @SRC@ stands for the clip and @PICTURE1@, @PICTURE2@... for the pictures.
# Needs Henge running (HENGE_URL, default http://127.0.0.1:8188), `uv` and `claude` on the PATH.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); MCP=$(cd "$HERE/.." && pwd)
TASK=${1:?task file}; SRC=$(realpath "${2:?guide video}"); shift 2
text=$(sed "s#@SRC@#$SRC#g" "$TASK"); i=1
for p in "$@"; do text=${text//@PICTURE$i@/$(realpath "$p")}; i=$((i + 1)); done
config=$(mktemp --suffix=.json); trap 'rm -f "$config"' EXIT
cat > "$config" <<JSON
{"mcpServers": {"henge": {"command": "uv", "args": ["run", "--script", "$MCP/henge_mcp.py"],
  "env": {"HENGE_URL": "${HENGE_URL:-http://127.0.0.1:8188}", "HENGE_CHARS": "${HENGE_CHARS:-$HOME/.henge/chars}",
          "HENGE_MCP_OUT": "${HENGE_MCP_OUT:-$PWD/henge-results}"}}}}
JSON
# wait_for_job blocks up to 30 min per call
export MCP_TOOL_TIMEOUT=${MCP_TOOL_TIMEOUT:-2000000}
exec claude -p --mcp-config "$config" --allowedTools 'mcp__henge__*' --append-system-prompt "$(cat "$MCP/AGENTS.md")" "$text"
