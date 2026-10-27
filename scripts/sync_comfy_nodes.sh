#!/usr/bin/env bash
# Publish backend/comfy_nodes/henge to github.com/alisson-anjos/ComfyUI-Henge (nodes at the repository root, as the
# Comfy Registry requires). That repository's workflow publishes to registry.comfy.org when pyproject.toml changes.
# Usage: VERSION=1.0.1 scripts/sync_comfy_nodes.sh   (VERSION bumps pyproject.toml and so triggers a registry release)
set -euo pipefail
cd "$(dirname "$0")/.."
DEST=${DEST:-../ComfyUI-Henge}
[ -d "$DEST/.git" ] || git clone -q https://github.com/alisson-anjos/ComfyUI-Henge.git "$DEST"
rsync -a --delete --exclude __pycache__ --exclude .git --exclude pyproject.toml --exclude README.md --exclude LICENSE \
  --exclude .github --exclude requirements.txt backend/comfy_nodes/henge/ "$DEST/"
if [ -n "${VERSION:-}" ]; then sed -i "s/^version = \".*\"/version = \"$VERSION\"/" "$DEST/pyproject.toml"; fi
cd "$DEST" && git add -A && { git diff --cached --quiet && echo "nothing to sync"; } || { git commit -q -m "Sync from Henge $(git -C "$OLDPWD" rev-parse --short HEAD)"; git push -q; echo "pushed"; }
