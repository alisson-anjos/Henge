#!/usr/bin/env bash
# Create (or update) the Henge RunPod Serverless worker template and endpoint.
# Usage: VOLUME_ID=<filled network volume> scripts/runpod_serverless.sh
#        ENDPOINT_ID=<id> TEMPLATE_ID=<id> scripts/runpod_serverless.sh   # update both
# The worker is the full image with HENGE_ROLE=worker (ComfyUI + docker/worker_handler.py); models come
# from the volume (scripts/runpod_volume.sh). Then run the UI anywhere:
#   docker run -p 8188:8188 -v henge-state:/state -e HENGE_BACKEND=runpod \
#     -e RUNPOD_ENDPOINT_ID=<endpoint> -e RUNPOD_API_KEY=<key> ghcr.io/alisson-anjos/henge-ui:runpod-template
set -euo pipefail
cd "$(dirname "$0")/.."
NAME=${ENDPOINT_NAME:-henge-worker}
IMAGE=${IMAGE:-ghcr.io/alisson-anjos/henge:runpod-template}
# 80-96 GB GPUs first; RunPod falls back along the list. All need a CUDA 13 driver.
GPUS=${GPUS:-NVIDIA A100-SXM4-80GB,NVIDIA RTX PRO 6000 Blackwell Server Edition,NVIDIA H100 80GB HBM3}
WORKERS_MAX=${WORKERS_MAX:-2}
IDLE_TIMEOUT=${IDLE_TIMEOUT:-120}
id() { python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])'; }
ENV_JSON='{"HENGE_ROLE":"worker"}'

if [ -n "${TEMPLATE_ID:-}" ]; then
  runpodctl template update "$TEMPLATE_ID" --image "$IMAGE" --env "$ENV_JSON" >/dev/null
else
  TEMPLATE_ID=$(runpodctl template create --serverless --name "$NAME" --image "$IMAGE" --env "$ENV_JSON" --container-disk-in-gb 40 | id)
fi
echo "worker template $TEMPLATE_ID ($IMAGE)"

if [ -n "${ENDPOINT_ID:-}" ]; then
  runpodctl serverless update "$ENDPOINT_ID" --template-id "$TEMPLATE_ID" --workers-max "$WORKERS_MAX" --idle-timeout "$IDLE_TIMEOUT" >/dev/null
else
  : "${VOLUME_ID:?set VOLUME_ID to the network volume filled by scripts/runpod_volume.sh}"
  ENDPOINT_ID=$(runpodctl serverless create --name "$NAME" --template-id "$TEMPLATE_ID" --gpu-id "$GPUS" \
    --network-volume-id "$VOLUME_ID" --workers-min 0 --workers-max "$WORKERS_MAX" --execution-timeout 3600 \
    --min-cuda-version 13.0 | id)
  runpodctl serverless update "$ENDPOINT_ID" --idle-timeout "$IDLE_TIMEOUT" >/dev/null
fi
echo "endpoint $ENDPOINT_ID (workers 0-$WORKERS_MAX, idle ${IDLE_TIMEOUT}s)"
echo "UI: HENGE_BACKEND=runpod RUNPOD_ENDPOINT_ID=$ENDPOINT_ID RUNPOD_API_KEY=<your key>"
