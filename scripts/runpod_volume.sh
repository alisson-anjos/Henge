#!/usr/bin/env bash
# Create a RunPod network volume and fill it with the Henge models for serverless workers
# (they mount it at /runpod-volume and read /runpod-volume/henge/models).
# Usage: scripts/runpod_volume.sh                      # new volume in $DATACENTER
#        VOLUME_ID=<id> scripts/runpod_volume.sh       # fill (or top up) an existing one
#        PROFILES=character,solar VOLUME_ID=<id> scripts/runpod_volume.sh   # choose the model profiles
# Needs: runpodctl configured. Every default model is public; gated ones (klein3 = FLUX.3 [image klein]) need
# HF_TOKEN=<token> with the license accepted on Hugging Face (it only reaches the temporary fill pod's env).
# How: a temporary pod from the Henge image mounts the volume at /workspace, downloads the PROFILES models
# exactly as a normal pod does, and is deleted once its setup screen (/api/backend/health) reports every
# model installed. Already present files are skipped. Serverless workers never download: they only read.
set -euo pipefail
DATACENTER=${DATACENTER:-EU-RO-1}
VOLUME_GB=${VOLUME_GB:-180}
IMAGE=${IMAGE:-ghcr.io/alisson-anjos/henge:latest}
PROFILES=${PROFILES:-character,motion,headswap,sharpness,omniref,klein,sam2d,sam3d,audio}
# REMOVE: optional comma-separated model paths (relative to models/) to delete from the volume, e.g. retired files.
# OVERRIDES: JSON for HENGE_MODEL_OVERRIDES (e.g. a link newer than the image's manifest).
ENV_JSON=$(PROFILES=$PROFILES REMOVE=${REMOVE:-} OVERRIDES=${OVERRIDES:-} python3 -c 'import json,os;e={"HENGE_MODEL_PROFILES":os.environ["PROFILES"]};e.update({"HENGE_REMOVE_MODELS":os.environ["REMOVE"]} if os.environ["REMOVE"] else {});e.update({"HENGE_MODEL_OVERRIDES":os.environ["OVERRIDES"]} if os.environ["OVERRIDES"] else {});e.update({"HF_TOKEN":os.environ["HF_TOKEN"]} if os.environ.get("HF_TOKEN") else {});print(json.dumps(e))')
# Any GPU with a CUDA 13 driver will do (it only downloads); the first one in stock is used.
FILL_GPUS=${FILL_GPUS:-NVIDIA RTX PRO 6000 Blackwell Server Edition,NVIDIA A100-SXM4-80GB,NVIDIA L40S,NVIDIA RTX A6000,NVIDIA GeForce RTX 5090,NVIDIA GeForce RTX 4090}
id() { python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])'; }

if [ -z "${VOLUME_ID:-}" ]; then
  VOLUME_ID=$(runpodctl network-volume create --name henge-models --data-center-id "$DATACENTER" --size "$VOLUME_GB" | id)
  echo "network volume $VOLUME_ID ($VOLUME_GB GB, $DATACENTER)"
fi
POD=
IFS=, read -ra gpus <<< "$FILL_GPUS"
for gpu in "${gpus[@]}"; do
  if out=$(runpodctl pod create --image "$IMAGE" --env "$ENV_JSON" --ports 8188/http --container-disk-in-gb 30 \
      --network-volume-id "$VOLUME_ID" --data-center-ids "$DATACENTER" \
      --gpu-id "$gpu" --min-cuda-version 13.0 --name henge-fill-volume 2>&1) && POD=$(printf '%s' "$out" | id 2>/dev/null); then
    echo "fill pod on $gpu";break
  fi
  echo "no $gpu in $DATACENTER: ${out:0:160}"
done
[ -n "$POD" ] || { echo "no GPU available in $DATACENTER for the fill pod; retry later or set FILL_GPUS"; exit 1; }
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
  # The checklist covers the modes only; optional files (e.g. the omniref base) finish when the downloader exits.
  # The downloader ends with 'model downloads finished', or with a warning when a file has no link (it never retries).
  if [ "$state" = ready ] && ! runpodctl pod logs "$POD" --source container --tail 5000 --max-wait 10s 2>/dev/null | grep -Eq 'model downloads finished|some models failed to download'; then
    state='checklist ready, downloader still running'
    echo "$(date +%H:%M) $state";continue
  fi
  case $state in ready) break ;; failed*) echo "some downloads failed; pod $POD kept for inspection"; exit 1 ;; esac
done
runpodctl pod delete "$POD" >/dev/null
echo "volume $VOLUME_ID is ready; create the endpoint with: VOLUME_ID=$VOLUME_ID scripts/runpod_serverless.sh"
