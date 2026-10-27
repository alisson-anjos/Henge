#!/usr/bin/env bash
# Create (or update) the Henge RunPod Serverless worker template and endpoint.
# Usage: VOLUME_ID=<filled network volume> scripts/runpod_serverless.sh
#        ENDPOINT_ID=<id> TEMPLATE_ID=<id> IMAGE=<image:tag> scripts/runpod_serverless.sh   # new image; drains old workers
# The worker is the full image with HENGE_ROLE=worker (ComfyUI + docker/worker_handler.py); models come
# from the volume (scripts/runpod_volume.sh). Then run the UI anywhere:
#   docker run -p 8188:8188 -v henge-state:/state -e HENGE_BACKEND=runpod \
#     -e RUNPOD_ENDPOINT_ID=<endpoint> -e RUNPOD_API_KEY=<key> ghcr.io/alisson-anjos/henge-ui:latest
set -euo pipefail
cd "$(dirname "$0")/.."
NAME=${ENDPOINT_NAME:-henge-worker}
# Serverless templates can't be public on RunPod: without TEMPLATE_ID a worker template is created in your account
# from the public Henge image.
IMAGE=${IMAGE:-ghcr.io/alisson-anjos/henge:latest}
# runpodctl creates the endpoint with one GPU type; it must exist in the volume's datacenter and have a CUDA 13 driver.
# The live endpoint lists RTX 5090 first (priority, ~half the price) with RTX PRO 6000 only as fallback when no 5090 is
# free; set that order in the RunPod console or with the REST API (PATCH /v1/endpoints/<id> {"gpuTypeIds": [...]}).
GPU=${GPU:-NVIDIA GeForce RTX 5090}
WORKERS_MAX=${WORKERS_MAX:-2}
# Idle workers are billed: 15 s covers back-to-back requests of one job (planning, FIBO, shots, downloads) without
# paying minutes after it ends. 120 s was a large part of the bill.
IDLE_TIMEOUT=${IDLE_TIMEOUT:-15}
id() { python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])'; }
# --fast-disk: weights stay disk-backed (page cache) instead of pinned RAM. Workers can have ~56 GB RAM (RTX 5090), and
# the H3 text encoder + model + VAE alone are ~51 GB: without it a second conditioning (Sharpness H3 upscale) is OOM-killed.
ENV_JSON='{"HENGE_ROLE":"worker","HENGE_COMFY_ARGS":"--fast-disk"}'

if [ -n "${TEMPLATE_ID:-}" ]; then
  runpodctl template update "$TEMPLATE_ID" --image "$IMAGE" --env "$ENV_JSON" >/dev/null
else
  TEMPLATE_ID=$(runpodctl template create --serverless --name "$NAME" --image "$IMAGE" --env "$ENV_JSON" --container-disk-in-gb 40 | id)
fi
echo "worker template $TEMPLATE_ID ($IMAGE)"

if [ -n "${ENDPOINT_ID:-}" ]; then
  # Running workers keep the image they started with: scale to zero until they are gone, then back up.
  KEY=${RUNPOD_API_KEY:-$(python3 -c 'import pathlib,tomllib;print(tomllib.loads((pathlib.Path.home()/".runpod/config.toml").read_text())["apikey"])')}
  runpodctl serverless update "$ENDPOINT_ID" --template-id "$TEMPLATE_ID" --workers-max 0 >/dev/null
  for _ in $(seq 1 60); do
    running=$(curl -s "https://api.runpod.ai/v2/$ENDPOINT_ID/health" -H "Authorization: Bearer $KEY" \
      | python3 -c 'import json,sys;print(sum(json.load(sys.stdin)["workers"].values()))' 2>/dev/null || echo 0)
    [ "$running" = 0 ] && break; sleep 5
  done
  runpodctl serverless update "$ENDPOINT_ID" --workers-max "$WORKERS_MAX" --idle-timeout "$IDLE_TIMEOUT" >/dev/null
  sleep 15  # the endpoint keeps answering "paused" for a few seconds after scaling back up
else
  : "${VOLUME_ID:?set VOLUME_ID to the network volume filled by scripts/runpod_volume.sh}"
  ENDPOINT_ID=$(runpodctl serverless create --name "$NAME" --template-id "$TEMPLATE_ID" --gpu-id "$GPU" \
    --network-volume-id "$VOLUME_ID" --workers-min 0 --workers-max "$WORKERS_MAX" --execution-timeout 3600 \
    --min-cuda-version 13.0 | id)
  runpodctl serverless update "$ENDPOINT_ID" --idle-timeout "$IDLE_TIMEOUT" >/dev/null
fi
echo "endpoint $ENDPOINT_ID (workers 0-$WORKERS_MAX, idle ${IDLE_TIMEOUT}s)"
echo "UI: HENGE_BACKEND=runpod RUNPOD_ENDPOINT_ID=$ENDPOINT_ID RUNPOD_API_KEY=<your key>"
