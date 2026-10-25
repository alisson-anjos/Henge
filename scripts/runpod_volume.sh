#!/usr/bin/env bash
# Create a RunPod network volume and fill it with the Henge models for serverless workers
# (they mount it at /runpod-volume and read /runpod-volume/henge/models).
# Usage: scripts/runpod_volume.sh                      # new volume in $DATACENTER
#        VOLUME_ID=<id> scripts/runpod_volume.sh       # fill (or top up) an existing one
# Needs: runpodctl configured; the pod template's HF_TOKEN secret for the private LoRAs.
# How: a temporary pod from the Henge pod template mounts the volume at /workspace, downloads the
# HENGE_MODEL_PROFILES models exactly as a normal pod does, and is deleted once its setup screen
# (/api/backend/health) reports every model installed. Already present files are skipped.
set -euo pipefail
DATACENTER=${DATACENTER:-EU-RO-1}
VOLUME_GB=${VOLUME_GB:-150}
TEMPLATE_ID=${TEMPLATE_ID:-mnxax277c8}
FILL_GPU=${FILL_GPU:-NVIDIA A100-SXM4-80GB}
id() { python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])'; }

if [ -z "${VOLUME_ID:-}" ]; then
  VOLUME_ID=$(runpodctl network-volume create --name henge-models --data-center-id "$DATACENTER" --size "$VOLUME_GB" | id)
  echo "network volume $VOLUME_ID ($VOLUME_GB GB, $DATACENTER)"
fi
POD=$(runpodctl pod create --template-id "$TEMPLATE_ID" --network-volume-id "$VOLUME_ID" --data-center-ids "$DATACENTER" \
  --gpu-id "$FILL_GPU" --name henge-fill-volume | id)
echo "fill pod $POD; following https://$POD-8188.proxy.runpod.net"
trap 'echo "fill pod $POD left running; delete it with: runpodctl pod delete $POD"' ERR INT
while :; do
  sleep 60
  health=$(curl -s -m 20 "https://$POD-8188.proxy.runpod.net/api/backend/health" || true)
  state=$(printf '%s' "$health" | python3 -c '
import json,sys
try:d=json.load(sys.stdin)
except ValueError:print("starting");sys.exit()
rows=d["requirements"];done=sum(r["state"]=="installed" for r in rows);failed=[r["file"] for r in rows if r["state"]=="failed"]
busy=d["setup"]["downloading"]
print("failed "+",".join(failed) if failed and not busy else "ready" if not busy and done==len(rows) else f"{done}/{len(rows)} installed")' 2>/dev/null || echo starting)
  echo "$(date +%H:%M) $state"
  case $state in ready) break ;; failed*) echo "some downloads failed (HF_TOKEN?); pod $POD kept for inspection"; exit 1 ;; esac
done
runpodctl pod delete "$POD" >/dev/null
echo "volume $VOLUME_ID is ready; create the endpoint with: VOLUME_ID=$VOLUME_ID scripts/runpod_serverless.sh"
