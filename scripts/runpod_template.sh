#!/usr/bin/env bash
# Create the RunPod pod template with runpodctl, or update it when TEMPLATE_ID is set.
# Needs: runpodctl configured (runpodctl doctor, or RUNPOD_API_KEY).
# Optional: REGISTRY_AUTH_ID for a private GHCR image (runpodctl registry list).
set -euo pipefail
cd "$(dirname "$0")/.."
NAME=${TEMPLATE_NAME:-Henge}
IMAGE=${IMAGE:-ghcr.io/alisson-anjos/henge:runpod-template}

ENV_JSON=$(python3 - <<'EOF'
import json
print(json.dumps({
  "HF_TOKEN": "{{ RUNPOD_SECRET_hf_token }}",
  "HENGE_MODEL_PROFILES": "character,motion10500,motion4500,solar,headswap,sharpness,omniref,fibo",
  "HENGE_COMFY_ARGS": "--lowvram",
}))
EOF
)

common=(--name "$NAME" --image "$IMAGE" --container-disk-in-gb 30
  --ports "8188/http,8189/http,22/tcp" --port-labels "8188=Henge UI,8189=ComfyUI,22=SSH"
  --env "$ENV_JSON" --readme "$(cat docker/runpod-template-readme.md)")
if [ -n "${TEMPLATE_ID:-}" ];then args=(template update "$TEMPLATE_ID" "${common[@]}")
else args=(template create "${common[@]}" --volume-in-gb 150 --volume-mount-path /workspace);fi
[ -n "${REGISTRY_AUTH_ID:-}" ] && args+=(--registry-auth-id "$REGISTRY_AUTH_ID")
runpodctl "${args[@]}"
